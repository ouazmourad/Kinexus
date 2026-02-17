"""
ThoughtLink — EEG Preprocessing & Dataset Building
Bandpass filtering, normalization, windowing, subject-based splits.
"""
import os
import sys
import glob
import numpy as np
from scipy.signal import butter, filtfilt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import (
    DATA_DIR, LABEL_MAP, LABEL_MAP_BINARY,
    EEG_SAMPLE_RATE, EEG_CHANNELS,
    WINDOW_SIZE_SAMPLES, WINDOW_STRIDE_SAMPLES,
    STIMULUS_START_SAMPLE, MIN_DURATION_SECONDS,
)


class EEGPreprocessor:
    """Bandpass filter and normalize EEG signals."""

    def __init__(self, low_freq=1.0, high_freq=40.0, filter_order=4, sample_rate=EEG_SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.low_freq = low_freq
        self.high_freq = high_freq
        self.filter_order = filter_order
        nyq = sample_rate / 2.0
        self.b, self.a = butter(filter_order, [low_freq / nyq, high_freq / nyq], btype='band')

    def bandpass_filter(self, eeg: np.ndarray) -> np.ndarray:
        """Apply 4th-order Butterworth bandpass filter per channel.
        Args:
            eeg: (samples, channels) array
        Returns:
            Filtered EEG array of same shape.
        """
        filtered = np.zeros_like(eeg)
        for ch in range(eeg.shape[1]):
            filtered[:, ch] = filtfilt(self.b, self.a, eeg[:, ch])
        return filtered

    def normalize(self, eeg: np.ndarray) -> np.ndarray:
        """Z-score normalization per channel. Handles std=0."""
        mean = eeg.mean(axis=0, keepdims=True)
        std = eeg.std(axis=0, keepdims=True)
        std[std == 0] = 1.0
        return (eeg - mean) / std

    def preprocess(self, eeg: np.ndarray) -> np.ndarray:
        """Full pipeline: filter then normalize, clean NaN/Inf."""
        result = self.normalize(self.bandpass_filter(eeg))
        return np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)


def extract_windows(eeg: np.ndarray, label_idx: int, duration: float,
                    window_size: int = WINDOW_SIZE_SAMPLES,
                    stride: int = WINDOW_STRIDE_SAMPLES,
                    stim_start: int = STIMULUS_START_SAMPLE) -> list:
    """Extract fixed-size windows from preprocessed EEG.

    Non-Relax classes: extract from stimulus region.
    Relax (class 4): random non-overlapping 1s windows from full signal.

    Returns:
        List of (window, label_idx) tuples where window is (window_size, channels).
    """
    windows = []

    if label_idx == 4:  # Relax
        # Random non-overlapping 1s windows from full signal
        total_samples = eeg.shape[0]
        max_windows = total_samples // window_size
        # Take up to ~20 windows to balance with active classes
        n_windows = min(max_windows, 20)
        indices = np.random.RandomState(42).choice(max_windows, size=n_windows, replace=False)
        for idx in sorted(indices):
            start = idx * window_size
            end = start + window_size
            if end <= total_samples:
                windows.append((eeg[start:end], label_idx))
    else:
        # Active classes: extract from stimulus region
        if duration < MIN_DURATION_SECONDS:
            return windows

        stim_end = stim_start + int(duration * EEG_SAMPLE_RATE)
        stim_end = min(stim_end, eeg.shape[0])

        pos = stim_start
        while pos + window_size <= stim_end:
            windows.append((eeg[pos:pos + window_size], label_idx))
            pos += stride

    return windows


class DatasetBuilder:
    """Build train/val/test splits with subject-based separation."""

    def __init__(self, data_dir: str = DATA_DIR, preprocessor: EEGPreprocessor = None, binary: bool = False):
        self.data_dir = data_dir
        self.preprocessor = preprocessor or EEGPreprocessor()
        self.binary = binary
        self.label_map = LABEL_MAP_BINARY if binary else LABEL_MAP

    def load_all(self):
        """Load and preprocess all .npz files into windowed dataset.
        Returns:
            X: (N, window_size, channels) array
            y: (N,) labels
            subject_ids: (N,) subject id per window
        """
        npz_files = sorted(glob.glob(os.path.join(self.data_dir, "*.npz")))
        all_windows = []
        all_labels = []
        all_subjects = []

        for fpath in npz_files:
            try:
                data = np.load(fpath, allow_pickle=True)
                eeg = data["feature_eeg"]
                label_info = data["label"].item()

                label_str = label_info["label"]
                subject_id = label_info["subject_id"]
                duration = label_info["duration"]

                if label_str not in self.label_map:
                    continue

                label_idx = self.label_map[label_str]

                # Preprocess
                eeg_proc = self.preprocessor.preprocess(eeg)

                # Extract windows
                windows = extract_windows(eeg_proc, label_idx, duration)
                for w, lbl in windows:
                    all_windows.append(w)
                    all_labels.append(lbl)
                    all_subjects.append(subject_id)

            except Exception:
                continue

        X = np.array(all_windows, dtype=np.float32)
        y = np.array(all_labels, dtype=np.int64)
        subject_ids = np.array(all_subjects)

        # Clean any remaining NaN/Inf
        nan_mask = np.isnan(X).any(axis=(1, 2)) | np.isinf(X).any(axis=(1, 2))
        if nan_mask.any():
            print(f"  Removing {nan_mask.sum()} windows with NaN/Inf values")
            X = X[~nan_mask]
            y = y[~nan_mask]
            subject_ids = subject_ids[~nan_mask]

        print(f"Loaded {len(X)} windows from {len(npz_files)} files "
              f"({'binary' if self.binary else '5-class'})")
        return X, y, subject_ids

    def split_by_subject(self, X, y, subject_ids, seed=42):
        """Split data by subject: 14 train / 3 val / 3 test.
        Returns:
            dict with train/val/test splits.
        """
        rng = np.random.RandomState(seed)
        unique_subjects = sorted(set(subject_ids))
        n_subjects = len(unique_subjects)

        perm = rng.permutation(n_subjects)
        subjects_arr = np.array(unique_subjects)
        shuffled = subjects_arr[perm]

        # 14 train / 3 val / 3 test
        train_subjects = set(shuffled[:14])
        val_subjects = set(shuffled[14:17])
        test_subjects = set(shuffled[17:20])

        # Handle case with fewer subjects
        if n_subjects < 20:
            n_train = max(1, int(0.7 * n_subjects))
            n_val = max(1, int(0.15 * n_subjects))
            train_subjects = set(shuffled[:n_train])
            val_subjects = set(shuffled[n_train:n_train + n_val])
            test_subjects = set(shuffled[n_train + n_val:])

        train_mask = np.array([s in train_subjects for s in subject_ids])
        val_mask = np.array([s in val_subjects for s in subject_ids])
        test_mask = np.array([s in test_subjects for s in subject_ids])

        splits = {
            "X_train": X[train_mask], "y_train": y[train_mask],
            "X_val": X[val_mask], "y_val": y[val_mask],
            "X_test": X[test_mask], "y_test": y[test_mask],
            "train_subjects": sorted(train_subjects),
            "val_subjects": sorted(val_subjects),
            "test_subjects": sorted(test_subjects),
        }

        print(f"Split: train={train_mask.sum()} ({len(train_subjects)} subj), "
              f"val={val_mask.sum()} ({len(val_subjects)} subj), "
              f"test={test_mask.sum()} ({len(test_subjects)} subj)")
        return splits

    def split_random(self, X, y, subject_ids, seed=42, train_ratio=0.8, val_ratio=0.1):
        """Random stratified split (mixed subjects in all sets).
        Better for calibrated BCI where subject data is available.
        """
        rng = np.random.RandomState(seed)
        n = len(y)
        indices = rng.permutation(n)

        n_train = int(train_ratio * n)
        n_val = int(val_ratio * n)

        train_idx = indices[:n_train]
        val_idx = indices[n_train:n_train + n_val]
        test_idx = indices[n_train + n_val:]

        splits = {
            "X_train": X[train_idx], "y_train": y[train_idx],
            "X_val": X[val_idx], "y_val": y[val_idx],
            "X_test": X[test_idx], "y_test": y[test_idx],
            "train_subjects": sorted(set(subject_ids[train_idx])),
            "val_subjects": sorted(set(subject_ids[val_idx])),
            "test_subjects": sorted(set(subject_ids[test_idx])),
        }

        print(f"Split (random): train={len(train_idx)}, "
              f"val={len(val_idx)}, test={len(test_idx)}")
        return splits

    def compute_class_weights(self, y) -> np.ndarray:
        """Compute inverse frequency class weights."""
        classes = np.unique(y)
        n_samples = len(y)
        weights = np.zeros(len(classes), dtype=np.float32)
        for c in classes:
            count = (y == c).sum()
            weights[c] = n_samples / (len(classes) * count) if count > 0 else 1.0
        return weights

    def build(self, split_mode="random"):
        """Complete pipeline: load -> split -> compute weights.
        Args:
            split_mode: "random" for mixed-subject split, "subject" for subject-based.
        """
        X, y, subject_ids = self.load_all()
        if split_mode == "subject":
            splits = self.split_by_subject(X, y, subject_ids)
        else:
            splits = self.split_random(X, y, subject_ids)
        class_weights = self.compute_class_weights(splits["y_train"])

        print(f"Class weights: {class_weights}")
        return splits, class_weights


if __name__ == "__main__":
    print("=" * 60)
    print("ThoughtLink — Preprocessing Pipeline")
    print("=" * 60)

    # Test with binary first
    print("\n--- Binary Dataset ---")
    builder_bin = DatasetBuilder(binary=True)
    splits_bin, weights_bin = builder_bin.build()
    print(f"  X_train: {splits_bin['X_train'].shape}")
    print(f"  Class weights: {weights_bin}")

    # Then 5-class
    print("\n--- 5-Class Dataset ---")
    builder_5 = DatasetBuilder(binary=False)
    splits_5, weights_5 = builder_5.build()
    print(f"  X_train: {splits_5['X_train'].shape}")
    print(f"  Class weights: {weights_5}")
