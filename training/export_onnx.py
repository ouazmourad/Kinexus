"""
ThoughtLink — ONNX Export & Benchmarking
Export trained EEGNet to ONNX, verify correctness, benchmark latency.
"""
import os
import sys
import json
import time
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import CHECKPOINT_DIR, RESULTS_DIR
from training.model import EEGNet
from training.train_eegnet import load_config


def export_to_onnx(task_name="5class"):
    """Export a trained model to ONNX format."""
    config = load_config()
    binary = task_name == "binary"
    num_classes = 2 if binary else 5

    model_cfg = config["model"]
    model = EEGNet(
        num_classes=num_classes,
        channels=model_cfg["channels"],
        samples=model_cfg["samples"],
        temporal_filters=model_cfg["temporal_filters"],
        spatial_multiplier=model_cfg["spatial_multiplier"],
        dropout_rate=model_cfg["dropout_rate"],
    )

    # Load trained weights
    pt_path = os.path.join(CHECKPOINT_DIR, f"best_{task_name}.pt")
    checkpoint = torch.load(pt_path, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    print(f"Loaded {task_name} model from epoch {checkpoint['epoch']} "
          f"(val_acc={checkpoint['val_acc']:.4f})")

    # Export
    onnx_path = os.path.join(CHECKPOINT_DIR, f"best_{task_name}.onnx")
    dummy_input = torch.randn(1, 1, 500, 6)

    torch.onnx.export(
        model,
        dummy_input,
        onnx_path,
        opset_version=config["inference"]["onnx_opset"],
        input_names=["eeg_input"],
        output_names=["logits"],
        dynamic_axes={
            "eeg_input": {0: "batch_size"},
            "logits": {0: "batch_size"},
        },
    )
    print(f"Exported to {onnx_path}")
    return onnx_path


def verify_onnx(task_name="5class"):
    """Verify ONNX output matches PyTorch output."""
    import onnxruntime as ort

    config = load_config()
    binary = task_name == "binary"
    num_classes = 2 if binary else 5

    model_cfg = config["model"]
    model = EEGNet(
        num_classes=num_classes,
        channels=model_cfg["channels"],
        samples=model_cfg["samples"],
        temporal_filters=model_cfg["temporal_filters"],
        spatial_multiplier=model_cfg["spatial_multiplier"],
        dropout_rate=model_cfg["dropout_rate"],
    )

    pt_path = os.path.join(CHECKPOINT_DIR, f"best_{task_name}.pt")
    checkpoint = torch.load(pt_path, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    onnx_path = os.path.join(CHECKPOINT_DIR, f"best_{task_name}.onnx")
    session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])

    # Test with random inputs
    test_inputs = [torch.randn(1, 1, 500, 6) for _ in range(10)]
    max_diff = 0.0

    for inp in test_inputs:
        # PyTorch
        with torch.no_grad():
            pt_out = model(inp).numpy()

        # ONNX
        ort_out = session.run(None, {"eeg_input": inp.numpy()})[0]

        diff = np.abs(pt_out - ort_out).max()
        max_diff = max(max_diff, diff)

    print(f"Verification: max absolute difference = {max_diff:.8f}")
    assert max_diff < 1e-5, f"ONNX output differs from PyTorch: {max_diff}"
    print("ONNX verification PASSED")
    return max_diff


def benchmark_onnx(task_name="5class", n_runs=1000):
    """Benchmark ONNX inference latency."""
    import onnxruntime as ort

    onnx_path = os.path.join(CHECKPOINT_DIR, f"best_{task_name}.onnx")
    results = {}

    # Test with available providers
    providers_to_test = ["CPUExecutionProvider"]
    available = ort.get_available_providers()
    if "CUDAExecutionProvider" in available:
        providers_to_test.append("CUDAExecutionProvider")

    dummy_input = np.random.randn(1, 1, 500, 6).astype(np.float32)

    for provider in providers_to_test:
        print(f"\nBenchmarking with {provider}...")
        try:
            session = ort.InferenceSession(onnx_path, providers=[provider])

            # Warmup
            for _ in range(50):
                session.run(None, {"eeg_input": dummy_input})

            # Benchmark
            latencies = []
            for _ in range(n_runs):
                t0 = time.perf_counter()
                session.run(None, {"eeg_input": dummy_input})
                latencies.append((time.perf_counter() - t0) * 1000)  # ms

            latencies = np.array(latencies)
            stats = {
                "mean_ms": round(float(latencies.mean()), 4),
                "median_ms": round(float(np.median(latencies)), 4),
                "p95_ms": round(float(np.percentile(latencies, 95)), 4),
                "p99_ms": round(float(np.percentile(latencies, 99)), 4),
                "min_ms": round(float(latencies.min()), 4),
                "max_ms": round(float(latencies.max()), 4),
            }
            results[provider] = stats
            print(f"  Mean: {stats['mean_ms']:.4f}ms | "
                  f"P50: {stats['median_ms']:.4f}ms | "
                  f"P95: {stats['p95_ms']:.4f}ms | "
                  f"P99: {stats['p99_ms']:.4f}ms")
        except Exception as e:
            print(f"  Skipped {provider}: {e}")
            results[provider] = {"error": str(e)}

    return results


def main():
    print("=" * 60)
    print("ThoughtLink — ONNX Export & Benchmarking")
    print("=" * 60)

    all_results = {}

    for task_name in ["binary", "5class"]:
        print(f"\n{'─' * 40}")
        print(f"Processing {task_name}...")
        print(f"{'─' * 40}")

        pt_path = os.path.join(CHECKPOINT_DIR, f"best_{task_name}.pt")
        if not os.path.exists(pt_path):
            print(f"  Checkpoint not found: {pt_path}, skipping...")
            continue

        onnx_path = export_to_onnx(task_name)
        max_diff = verify_onnx(task_name)
        bench = benchmark_onnx(task_name)

        all_results[task_name] = {
            "onnx_path": onnx_path,
            "verification_max_diff": float(max_diff),
            "benchmarks": bench,
        }

    # Save results
    out_path = os.path.join(RESULTS_DIR, "onnx_benchmarks.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nBenchmark results saved to {out_path}")


if __name__ == "__main__":
    main()
