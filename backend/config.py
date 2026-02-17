"""ThoughtLink configuration — integrates with shared constants.py."""

import os
import sys
from pathlib import Path

# Add project root to path so we can import constants
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from constants import (
    DATA_DIR,
    CHECKPOINT_DIR,
    EEG_SAMPLE_RATE,
    WINDOW_SIZE_SAMPLES,
    WINDOW_STRIDE_SAMPLES,
    CONFIDENCE_THRESHOLD,
    BRAIN_LABEL_TO_COMMAND,
    LABEL_NAMES,
    LABEL_MAP,
    NUM_CLASSES,
)

# Server
HOST = "0.0.0.0"
PORT = 8000

# Paths
BRI_SRC_PATH = str(PROJECT_ROOT.parent / "brain-robot-interface" / "src")
BRI_BUNDLE_DIR = str(PROJECT_ROOT.parent / "brain-robot-interface" / "bundles" / "g1_mjlab")
# DATA_DIR from constants defaults to ~/robot_control/data — override if data lives next to project
_actual_data_dir = PROJECT_ROOT.parent / "robot_control" / "data"
EEG_DATA_DIR = str(_actual_data_dir) if _actual_data_dir.exists() else str(DATA_DIR)
MODEL_PATH = str(CHECKPOINT_DIR / "best_5class.onnx")
MODEL_CONFIG_PATH = str(PROJECT_ROOT / "training" / "config.json")

# Control loop
CONTROL_HZ = 10
TICK_INTERVAL = 1.0 / CONTROL_HZ

# Voice
VOICE_OVERRIDE_HOLD_S = 2.0

# TTS PROVIDER
# Hackathon: ElevenLabs cloud API (requires internet)
# Production: Swap to local TTS (Piper/Coqui) running on edge server — same interface, no cloud dependency
TTS_PROVIDER = "elevenlabs"  # or "local_piper" in production
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
