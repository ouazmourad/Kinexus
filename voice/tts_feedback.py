"""
Voice feedback via ElevenLabs TTS.
Queued, priority-based, with cooldowns to prevent chatter.
"""

from __future__ import annotations

import base64
import io
import logging
import queue
import threading
import time
from dataclasses import dataclass

import requests

from voice.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    ELEVENLABS_MODEL_ID,
    TTS_VOICE_SETTINGS,
    COOLDOWNS,
    FEEDBACK_EVENTS,
)

logger = logging.getLogger(__name__)


@dataclass
class TTSRequest:
    text: str
    event_type: str
    priority: int  # 0=urgent (interrupts), 1=normal, 2=low (dropped if busy)
    timestamp: float


class VoiceFeedback:
    """
    ElevenLabs TTS with queuing, priority, and cooldown management.

    Modes:
      - "server": synthesize on server, return audio bytes (for WebSocket delivery)
      - "client": return text only, let the browser call ElevenLabs directly

    For the hackathon, "server" mode returns base64 audio via the API,
    and the frontend plays it through an <audio> element.
    """

    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        mode: str = "server",
    ):
        self.api_key = api_key or ELEVENLABS_API_KEY
        self.voice_id = voice_id or ELEVENLABS_VOICE_ID
        self.mode = mode
        self._speech_queue: queue.Queue[TTSRequest] = queue.Queue()
        self._last_spoken: dict[str, float] = {}
        self._is_speaking = False
        self._enabled = bool(self.api_key)
        # Callback for delivering audio to clients (set by WebSocket handler)
        self._audio_callback: callable | None = None
        self._feedback_log: list[dict] = []

        if not self._enabled:
            logger.warning(
                "ELEVENLABS_API_KEY not set. TTS disabled — text feedback only."
            )

    def set_audio_callback(self, callback: callable) -> None:
        """Set callback for delivering audio: callback(text, audio_base64, event_type)."""
        self._audio_callback = callback

    def speak(self, text: str, event_type: str = "general", priority: int = 1) -> dict | None:
        """
        Queue a TTS utterance. Returns feedback dict for immediate use.

        priority: 0=urgent (interrupts), 1=normal, 2=low (dropped if busy)
        """
        now = time.time()
        cooldown = COOLDOWNS.get(event_type, 1.0)
        last = self._last_spoken.get(event_type, 0)

        if now - last < cooldown:
            return None

        if priority == 2 and self._is_speaking:
            return None

        self._last_spoken[event_type] = now

        feedback = {
            "text": text,
            "event_type": event_type,
            "priority": priority,
            "timestamp": now,
            "audio_base64": None,
        }

        if self._enabled and self.mode == "server":
            audio_b64 = self._synthesize(text)
            feedback["audio_base64"] = audio_b64

        self._feedback_log.append(feedback)

        if self._audio_callback:
            self._audio_callback(text, feedback.get("audio_base64"), event_type)

        return feedback

    def _synthesize(self, text: str) -> str | None:
        """Call ElevenLabs API and return base64-encoded mp3."""
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
            }
            payload = {
                "text": text,
                "model_id": ELEVENLABS_MODEL_ID,
                "voice_settings": TTS_VOICE_SETTINGS,
            }
            resp = requests.post(url, json=payload, headers=headers, stream=True, timeout=10)
            if resp.status_code != 200:
                logger.error(f"ElevenLabs API error {resp.status_code}: {resp.text[:200]}")
                return None

            audio_bytes = b"".join(resp.iter_content(chunk_size=4096))
            return base64.b64encode(audio_bytes).decode("utf-8")

        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            return None

    # === Convenience methods ===

    def announce_gear_shift(self, gear: str) -> dict | None:
        templates = FEEDBACK_EVENTS.get("gear_shift", {})
        text = templates.get(gear, f"Gear {gear}")
        return self.speak(text, "gear_shift", priority=0)

    def announce_brain_command(self, command: str) -> dict | None:
        templates = FEEDBACK_EVENTS.get("brain_command", {})
        text = templates.get(command)
        if not text:
            return None
        return self.speak(text, "brain_command", priority=2)

    def acknowledge_voice_command(self, description: str) -> dict | None:
        return self.speak(f"Command received: {description}", "voice_ack", priority=1)

    def acknowledge_auto_command(self, robot_id: str, action: str) -> dict | None:
        return self.speak(f"Robot {robot_id}: {action}", "auto_ack", priority=1)

    def announce_error(self, message: str) -> dict | None:
        return self.speak(message, "robot_error", priority=0)

    def announce_unclear(self) -> dict | None:
        text = FEEDBACK_EVENTS.get("command_unclear", "Didn't catch that.")
        return self.speak(text, "command_unclear", priority=1)

    def announce_brain_uncertain(self) -> dict | None:
        text = FEEDBACK_EVENTS.get("brain_uncertain", "Brain signal unclear.")
        return self.speak(text, "brain_uncertain", priority=2)

    def announce_emergency_stop(self) -> dict | None:
        text = FEEDBACK_EVENTS.get("emergency_stop", "Emergency stop.")
        return self.speak(text, "emergency_stop", priority=0)

    def get_feedback_log(self) -> list[dict]:
        return list(self._feedback_log)