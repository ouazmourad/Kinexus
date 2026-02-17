"""
Voice input listener.
Receives STT transcripts (from browser WebSocket or local Whisper)
and queues parsed commands.
"""

from __future__ import annotations

import queue
import logging
from voice.command_parser import CommandParser, ParsedCommand

logger = logging.getLogger(__name__)


class VoiceCommandListener:
    """
    Receives speech-to-text transcripts, parses them, and queues commands.

    Usage:
        parser = CommandParser()
        listener = VoiceCommandListener(parser)

        # When STT produces a transcript (e.g. from WebSocket):
        listener.on_transcript("R15 bring box to zone B2", confidence=0.92)

        # In the main loop:
        command = listener.get_latest_command()
    """

    def __init__(self, parser: CommandParser | None = None):
        self.parser = parser or CommandParser()
        self.command_queue: queue.Queue[ParsedCommand] = queue.Queue()
        self._transcript_log: list[dict] = []

    def on_transcript(self, transcript: str, confidence: float = 1.0) -> ParsedCommand | None:
        """
        Called when STT produces a transcript.
        Parses it and queues the command if valid.
        Returns the parsed command or None.
        """
        parsed = self.parser.parse(transcript, confidence)

        self._transcript_log.append({
            "text": transcript,
            "confidence": confidence,
            "parsed": parsed is not None,
            "action": parsed.action if parsed else None,
        })

        if parsed:
            self.command_queue.put(parsed)
            logger.info(f"Voice command: {parsed.action} (from: '{transcript}')")
        else:
            logger.debug(f"Unrecognized transcript: '{transcript}'")

        return parsed

    def get_latest_command(self) -> ParsedCommand | None:
        """Non-blocking. Returns the latest parsed command or None."""
        try:
            return self.command_queue.get_nowait()
        except queue.Empty:
            return None

    def get_all_pending(self) -> list[ParsedCommand]:
        """Drain all pending commands."""
        commands = []
        while not self.command_queue.empty():
            try:
                commands.append(self.command_queue.get_nowait())
            except queue.Empty:
                break
        return commands

    def get_transcript_log(self) -> list[dict]:
        """Return log of all received transcripts."""
        return list(self._transcript_log)

    def clear(self) -> None:
        """Clear pending commands and transcript log."""
        while not self.command_queue.empty():
            try:
                self.command_queue.get_nowait()
            except queue.Empty:
                break
        self._transcript_log.clear()