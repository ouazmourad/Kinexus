"""
Voice layer configuration.
ElevenLabs API settings, cooldowns, and voice feedback templates.
"""

import os

# === ElevenLabs TTS ===
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # "Rachel" default
ELEVENLABS_MODEL_ID = "eleven_turbo_v2"

TTS_VOICE_SETTINGS = {
    "stability": 0.7,
    "similarity_boost": 0.8,
    "speed": 1.15,
}

# === Cooldowns (seconds) — prevent spamming the same feedback ===
COOLDOWNS = {
    "gear_shift": 0.5,
    "brain_command": 2.0,
    "voice_ack": 0.0,
    "auto_ack": 0.5,
    "brain_uncertain": 5.0,
    "command_unclear": 3.0,
    "robot_error": 1.0,
    "general": 1.0,
    "nav_start": 1.0,
    "nav_arrive": 0.5,
    "nav_cancel": 0.5,
    "orch_dispatch": 1.0,
    "emergency_stop": 0.0,
}

# === Feedback templates ===
FEEDBACK_EVENTS = {
    "gear_shift": {
        "NEUTRAL": "Gear neutral",
        "FORWARD": "Forward gear",
        "REVERSE": "Reverse gear",
    },
    "brain_command": {
        "ROTATE_LEFT": "Rotating left",
        "ROTATE_RIGHT": "Rotating right",
        "LEFT": "Turning left",
        "RIGHT": "Turning right",
        "MOVE_FORWARD": "Moving forward",
        "FORWARD": "Moving forward",
        "MOVE_BACKWARD": "Reversing",
        "GRAB": "Grabbing",
        "RELEASE": "Releasing",
        "STOP": None,
        "IDLE": None,
    },
    "command_unclear": "Didn't catch that. Please repeat.",
    "brain_uncertain": "Brain signal unclear. Holding position.",
    "emergency_stop": "Emergency stop. All robots halted.",
}