"""
ThoughtLink — BrainDecoder
Public inference API class. Other modules only need this class.
"""
import os
import sys
import time
import json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import (
    CHECKPOINT_DIR, LABEL_NAMES, LABEL_NAMES_BINARY,
    BRAIN_LABEL_TO_COMMAND,
)
from training.preprocessing import EEGPreprocessor
from training.realtime import TemporalStabilizer


class BrainDecoder:
    """High-level inference API for brain-to-command decoding.

    Wraps ONNX model + preprocessing + temporal stabilization into
    a single predict() call.

    Usage:
        decoder = BrainDecoder("checkpoints/best_5class.onnx")
        result = decoder.predict(eeg_window)  # (500, 6) raw EEG
        print(result["command"])  # "FORWARD", "LEFT", "RIGHT", "STOP"
    """

    def __init__(self, model_path: str = None, config_path: str = None, binary: bool = False):
        import onnxruntime as ort

        if model_path is None:
            task = "binary" if binary else "5class"
            model_path = os.path.join(CHECKPOINT_DIR, f"best_{task}.onnx")

        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "config.json")

        # Load config
        with open(config_path) as f:
            self.config = json.load(f)

        self.binary = binary
        self.label_names = LABEL_NAMES_BINARY if binary else LABEL_NAMES
        self.num_classes = len(self.label_names)

        # Initialize ONNX session — only request CUDA if its DLLs are actually loadable
        available = ort.get_available_providers()
        if "CUDAExecutionProvider" in available:
            use_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        else:
            use_providers = ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(model_path, providers=use_providers)
        self.input_name = self.session.get_inputs()[0].name

        print(f"BrainDecoder loaded: {model_path}")
        print(f"  Provider: {self.session.get_providers()[0]}")
        print(f"  Classes: {self.num_classes} ({'binary' if binary else '5-class'})")

        # Initialize preprocessor
        pre_cfg = self.config["preprocessing"]
        self.preprocessor = EEGPreprocessor(
            low_freq=pre_cfg["low_freq"],
            high_freq=pre_cfg["high_freq"],
            filter_order=pre_cfg["filter_order"],
            sample_rate=pre_cfg["sample_rate"],
        )

        # Initialize temporal stabilizer
        inf_cfg = self.config["inference"]
        self.stabilizer = TemporalStabilizer(
            confidence_threshold=inf_cfg["confidence_threshold"],
            smoothing_window=inf_cfg["smoothing_window"],
            hysteresis_count=inf_cfg["hysteresis_count"],
            label_names=self.label_names,
        )

    def predict(self, eeg_window: np.ndarray) -> dict:
        """Full prediction pipeline with temporal stabilization.

        Args:
            eeg_window: Raw EEG data, shape (500, 6)

        Returns:
            dict with:
                - class: Predicted class index
                - label: Human-readable label
                - command: Robot command string
                - confidence: Max softmax probability
                - latency_ms: Inference time in milliseconds
                - stable_command: Temporally stabilized command
                - gated: Whether prediction was confidence-gated
        """
        t0 = time.perf_counter()

        # Preprocess
        eeg_proc = self.preprocessor.preprocess(eeg_window)

        # Reshape: (500, 6) → (1, 1, 500, 6)
        input_tensor = eeg_proc.astype(np.float32)[np.newaxis, np.newaxis, :, :]

        # Run inference
        logits = self.session.run(None, {self.input_name: input_tensor})[0]

        # Softmax
        exp_logits = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)
        probs = probs[0]

        predicted_class = int(np.argmax(probs))
        confidence = float(probs[predicted_class])

        # Temporal stabilization
        stable_result = self.stabilizer.update(predicted_class, confidence)

        latency_ms = (time.perf_counter() - t0) * 1000

        return {
            "class": predicted_class,
            "label": self.label_names[predicted_class],
            "command": BRAIN_LABEL_TO_COMMAND.get(predicted_class, "STOP"),
            "confidence": round(confidence, 4),
            "probabilities": {self.label_names[i]: round(float(probs[i]), 4)
                              for i in range(self.num_classes)},
            "latency_ms": round(latency_ms, 3),
            "stable_command": stable_result["stable_command"],
            "gated": stable_result["gated"],
            "switched": stable_result["switched"],
        }

    def predict_raw(self, eeg_window: np.ndarray) -> dict:
        """Prediction without temporal stabilization.

        Args:
            eeg_window: Raw EEG data, shape (500, 6)

        Returns:
            dict with class, label, command, confidence, latency_ms
        """
        t0 = time.perf_counter()

        eeg_proc = self.preprocessor.preprocess(eeg_window)
        input_tensor = eeg_proc.astype(np.float32)[np.newaxis, np.newaxis, :, :]
        logits = self.session.run(None, {self.input_name: input_tensor})[0]

        exp_logits = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)
        probs = probs[0]

        predicted_class = int(np.argmax(probs))
        confidence = float(probs[predicted_class])
        latency_ms = (time.perf_counter() - t0) * 1000

        return {
            "class": predicted_class,
            "label": self.label_names[predicted_class],
            "command": BRAIN_LABEL_TO_COMMAND.get(predicted_class, "STOP"),
            "confidence": round(confidence, 4),
            "probabilities": {self.label_names[i]: round(float(probs[i]), 4)
                              for i in range(self.num_classes)},
            "latency_ms": round(latency_ms, 3),
        }

    def reset(self):
        """Clear temporal stabilizer state between sessions."""
        self.stabilizer.reset()


if __name__ == "__main__":
    print("=" * 60)
    print("ThoughtLink — BrainDecoder Test")
    print("=" * 60)

    import glob
    from constants import DATA_DIR

    # Try to load 5-class model, fall back to binary
    onnx_5 = os.path.join(CHECKPOINT_DIR, "best_5class.onnx")
    onnx_bin = os.path.join(CHECKPOINT_DIR, "best_binary.onnx")

    if os.path.exists(onnx_5):
        decoder = BrainDecoder(onnx_5, binary=False)
    elif os.path.exists(onnx_bin):
        decoder = BrainDecoder(onnx_bin, binary=True)
    else:
        print("No ONNX model found. Train and export first.")
        sys.exit(1)

    # Test with a real .npz file
    npz_files = sorted(glob.glob(os.path.join(DATA_DIR, "*.npz")))
    if npz_files:
        data = np.load(npz_files[0], allow_pickle=True)
        eeg = data["feature_eeg"]
        label_info = data["label"].item()

        print(f"\nTest file: {os.path.basename(npz_files[0])}")
        print(f"True label: {label_info['label']}")

        # Extract a 1-second window from stimulus region
        window = eeg[1500:2000]  # (500, 6)
        result = decoder.predict(window)

        print(f"\nPrediction:")
        for k, v in result.items():
            print(f"  {k}: {v}")
