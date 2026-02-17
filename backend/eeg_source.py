"""EEG Data Source — replays .npz files at real-time speed for demo."""

import os
import sys
from pathlib import Path
import numpy as np
from glob import glob

# Import shared constants
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from constants import (
    WINDOW_SIZE_SAMPLES,
    WINDOW_STRIDE_SAMPLES,
    STIMULUS_START_SAMPLE,
    EEG_SAMPLE_RATE,
    EEG_NUM_CHANNELS,
    LABEL_MAP,
    LABEL_NAMES,
)


class EEGReplaySource:
    """Replays .npz files at real-time speed for demo purposes."""

    def __init__(self, data_dir: str):
        self.files = sorted(glob(os.path.join(data_dir, "**", "*.npz"), recursive=True))
        self.current_file_idx = 0
        self.current_eeg = None
        self.current_label = None
        self.current_sample = 0
        self.window_size = WINDOW_SIZE_SAMPLES
        self.stride = WINDOW_STRIDE_SAMPLES
        self.ready = False

        if self.files:
            self._load_next_file()
            self.ready = True
            print(f"[EEGSource] Loaded {len(self.files)} .npz files from {data_dir}")
        else:
            print(f"[EEGSource] WARNING: No .npz files found in {data_dir}")

    def _load_next_file(self):
        if not self.files:
            return
        if self.current_file_idx >= len(self.files):
            self.current_file_idx = 0  # loop
        f = self.files[self.current_file_idx]
        try:
            arr = np.load(f, allow_pickle=True)
            eeg = arr["feature_eeg"]
            label_data = arr["label"]
            if label_data.ndim == 0:
                self.current_label = label_data.item()
            else:
                self.current_label = {"label": str(label_data)}

            # Start from stimulus period (t=3s)
            self.current_eeg = eeg[STIMULUS_START_SAMPLE:]
            self.current_sample = 0
            self.current_file_idx += 1
        except Exception as e:
            print(f"[EEGSource] Error loading {f}: {e}")
            self.current_file_idx += 1
            if self.current_file_idx < len(self.files):
                self._load_next_file()

    def get_latest_window(self) -> np.ndarray | None:
        """Returns a (500, 6) window or None if not ready yet."""
        if not self.ready or self.current_eeg is None:
            return None

        if self.current_sample + self.window_size > len(self.current_eeg):
            self._load_next_file()
            if self.current_eeg is None:
                return None

        window = self.current_eeg[self.current_sample : self.current_sample + self.window_size]
        self.current_sample += self.stride

        if window.shape[0] < self.window_size:
            return None

        return window

    def get_current_label(self) -> str:
        """For debugging: what class is this chunk?"""
        if self.current_label and isinstance(self.current_label, dict):
            return self.current_label.get("label", "unknown")
        return str(self.current_label) if self.current_label else "unknown"

    def reset(self):
        self.current_file_idx = 0
        self.current_sample = 0
        if self.files:
            self._load_next_file()


class TestEEGSource:
    """Generates class-specific synthetic EEG that goes through the real ONNX classifier."""

    def __init__(self):
        self.window_size = WINDOW_SIZE_SAMPLES
        self.n_channels = EEG_NUM_CHANNELS
        self.tick = 0
        self.classes = LABEL_NAMES
        self.current_class_idx = 0
        self.ticks_per_class = 50  # switch class every 5 seconds at 10Hz
        self.ready = True
        # Class-specific base frequencies per channel
        self._class_freqs = [
            [8, 10, 12, 14, 16, 18],   # class 0: Right Fist
            [9, 11, 13, 15, 17, 19],   # class 1: Left Fist
            [10, 14, 18, 22, 26, 30],  # class 2: Both Fists
            [12, 16, 20, 24, 28, 32],  # class 3: Tongue Tapping
            [6, 8, 10, 12, 14, 16],    # class 4: Relax
        ]
        print("[EEGSource] TestEEGSource active — synthetic data through real classifier")

    def get_latest_window(self) -> np.ndarray:
        """Generate a (500, 6) EEG window with class-specific frequency patterns."""
        t = np.linspace(0, 1, self.window_size)
        freqs = self._class_freqs[self.current_class_idx]
        channels = []
        for ch in range(self.n_channels):
            amplitude = 0.5 + self.current_class_idx * 0.2
            signal = amplitude * np.sin(2 * np.pi * freqs[ch] * t)
            signal += 0.1 * np.random.randn(self.window_size)
            channels.append(signal)

        self.tick += 1
        if self.tick % self.ticks_per_class == 0:
            self.current_class_idx = (self.current_class_idx + 1) % len(self.classes)

        return np.column_stack(channels)

    def get_current_label(self) -> str:
        return self.classes[self.current_class_idx]

    def reset(self):
        self.tick = 0
        self.current_class_idx = 0
