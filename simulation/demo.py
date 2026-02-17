"""
ThoughtLink Simulation Demo
Closed-loop brain-to-robot control demonstration.

Usage:
    # With mock decoder (for testing before model is trained):
    python simulation/demo.py --mock

    # With trained ONNX model:
    python simulation/demo.py --model training/checkpoints/best_5class.onnx

    # Specify a trial file:
    python simulation/demo.py --mock --trial robot_control/data/0b2dbd41-10.npz

    # Keyboard control (manual testing):
    python simulation/demo.py --keyboard

    # Factory robot mode (all features):
    python simulation/demo.py --factory --scene factory
"""

from __future__ import annotations

import argparse
import sys
import time
import threading
from pathlib import Path

import numpy as np

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from constants import (
    DATA_DIR,
    BRAIN_LABEL_TO_COMMAND,
    LABEL_MAP,
    LABEL_NAMES,
    NUM_CLASSES,
    CONFIDENCE_THRESHOLD,
    SMOOTHING_WINDOW,
    HYSTERESIS_COUNT,
    EEG_SAMPLE_RATE,
    WINDOW_SIZE_SAMPLES,
    WINDOW_STRIDE_SAMPLES,
    STIMULUS_START_SAMPLE,
)
from simulation.bridge import SimulationBridge, eeg_stream_from_npz


class MockDecoder:
    """
    Mock BrainDecoder for testing the simulation bridge before a real model is trained.
    Returns predictions based on the ground-truth label of the loaded trial.
    """

    def __init__(self, ground_truth_label: str = "Right Fist", noise_level: float = 0.1):
        self._gt_label = ground_truth_label
        self._gt_class = LABEL_MAP.get(ground_truth_label, 4)
        self._noise = noise_level
        self._call_count = 0

    def predict(self, eeg_window: np.ndarray) -> dict:
        """Simulate a prediction with some noise."""
        t_start = time.perf_counter()
        self._call_count += 1

        # Build fake softmax probabilities
        probs = np.full(NUM_CLASSES, self._noise / (NUM_CLASSES - 1))
        probs[self._gt_class] = 1.0 - self._noise

        # Add some random noise
        noise = np.random.uniform(-0.05, 0.05, NUM_CLASSES)
        probs = np.clip(probs + noise, 0.01, 1.0)
        probs /= probs.sum()

        predicted_class = int(np.argmax(probs))
        confidence = float(probs[predicted_class])
        command = BRAIN_LABEL_TO_COMMAND.get(predicted_class, "STOP")
        label = LABEL_NAMES[predicted_class] if predicted_class < len(LABEL_NAMES) else "Unknown"

        # Simulate gating
        gated = confidence < CONFIDENCE_THRESHOLD

        latency_ms = (time.perf_counter() - t_start) * 1000

        return {
            "class": predicted_class,
            "label": label,
            "confidence": confidence,
            "command": command,
            "stable_command": command if not gated else "STOP",
            "latency_ms": latency_ms,
            "gated": gated,
            "probabilities": probs.tolist(),
        }

    def reset(self):
        """Reset internal state."""
        self._call_count = 0

    def set_ground_truth(self, label: str):
        """Update the ground truth label for mock predictions."""
        self._gt_label = label
        self._gt_class = LABEL_MAP.get(label, 4)


def find_trial_files(data_dir: Path, label_filter: str | None = None) -> list[Path]:
    """Find .npz trial files, optionally filtered by label."""
    files = sorted(data_dir.glob("*.npz"))
    if label_filter is None:
        return files

    filtered = []
    for f in files:
        try:
            data = np.load(str(f), allow_pickle=True)
            lbl = data["label"].item().get("label", "")
            if lbl == label_filter:
                filtered.append(f)
        except Exception:
            continue
    return filtered


def run_keyboard_mode(bridge: SimulationBridge):
    """Manual keyboard control mode for testing the simulation."""
    from bri import Action

    print("\n[Demo] Keyboard control mode")
    print("  W = FORWARD, A = LEFT, D = RIGHT, S = STOP, Q = Quit\n")

    bridge.start()

    try:
        while bridge.is_running():
            try:
                key = input("Action> ").strip().lower()
            except EOFError:
                break

            if key in ("q", "quit", "exit"):
                break
            elif key == "w":
                bridge.send_action_sustained("FORWARD", duration_s=0.5)
                print("  -> FORWARD")
            elif key == "a":
                bridge.send_action_sustained("LEFT", duration_s=0.5)
                print("  -> LEFT")
            elif key == "d":
                bridge.send_action_sustained("RIGHT", duration_s=0.5)
                print("  -> RIGHT")
            elif key in ("s", " "):
                bridge.send_action("STOP")
                print("  -> STOP")
            else:
                print("  Unknown key. Use W/A/S/D or Q to quit.")
    except KeyboardInterrupt:
        pass
    finally:
        bridge.stop()


def run_mock_demo(bridge: SimulationBridge, trial_path: Path):
    """Run a demo with the mock decoder using ground-truth labels."""
    # Load trial to get ground truth
    data = np.load(str(trial_path), allow_pickle=True)
    label_info = data["label"].item()
    gt_label = label_info["label"]

    print(f"\n[Demo] Mock demo with ground truth: {gt_label}")
    print(f"  Expected command: {BRAIN_LABEL_TO_COMMAND[LABEL_MAP[gt_label]]}")

    # Create mock decoder with ground truth
    mock = MockDecoder(ground_truth_label=gt_label, noise_level=0.15)
    bridge._decoder = mock

    bridge.start()

    # Give MuJoCo viewer time to initialize
    time.sleep(1.0)

    try:
        log = bridge.run_trial(str(trial_path), realtime=True)
        print_summary(log, gt_label)
    except KeyboardInterrupt:
        print("\n[Demo] Interrupted.")
    finally:
        bridge.stop()


def run_real_demo(bridge: SimulationBridge, trial_path: Path):
    """Run a demo with the real BrainDecoder."""
    bridge.start()
    time.sleep(1.0)

    try:
        log = bridge.run_trial(str(trial_path), realtime=True)

        # Get ground truth
        data = np.load(str(trial_path), allow_pickle=True)
        gt_label = data["label"].item()["label"]
        print_summary(log, gt_label)
    except KeyboardInterrupt:
        print("\n[Demo] Interrupted.")
    finally:
        bridge.stop()


def run_multi_trial_demo(bridge: SimulationBridge, data_dir: Path, num_trials: int = 4):
    """
    Run demos for multiple trials (one per label) to demonstrate
    all robot behaviors.
    """
    labels_to_demo = [
        ("Right Fist", ["Right Fist"]),
        ("Left Fist", ["Left Fist", "Left First"]),
        ("Tongue Tapping", ["Tongue Tapping"]),
        ("Relax", ["Relax"]),
    ]

    bridge.start()
    time.sleep(1.0)

    try:
        for display_label, search_labels in labels_to_demo:
            # Try each variant of the label name (handles typos)
            files = []
            matched_label = display_label
            for sl in search_labels:
                files = find_trial_files(data_dir, label_filter=sl)
                if files:
                    matched_label = sl
                    break
            if not files:
                print(f"\n[Demo] No files found for label: {display_label}, skipping.")
                continue

            trial_file = files[0]
            mock = MockDecoder(ground_truth_label=matched_label, noise_level=0.15)
            bridge._decoder = mock

            cmd = BRAIN_LABEL_TO_COMMAND[LABEL_MAP[matched_label]]
            print(f"\n{'='*60}")
            print(f"  DEMO: {display_label} -> Expected robot action: {cmd}")
            print(f"{'='*60}")

            log = bridge.run_trial(str(trial_file), realtime=True)
            print_summary(log, matched_label)

            # Pause between trials
            bridge.send_action("STOP")
            time.sleep(2.0)

    except KeyboardInterrupt:
        print("\n[Demo] Interrupted.")
    finally:
        bridge.stop()


def run_factory_mode(bridge: SimulationBridge):
    """Interactive factory robot mode with all features."""
    from simulation.factory_controller import FactoryController, TaskSequencer

    print("\n[Demo] Factory Robot Mode")
    print("  Controls:")
    print("    W/A/S/D  = Forward / Left / Stop / Right")
    print("    1-6      = Select waypoint (Shelf A, Shelf B, Conveyor, Table, Pallet 1, Pallet 2)")
    print("    G        = Go to selected waypoint")
    print("    P        = Start patrol       O = Pause/resume patrol   N = Skip patrol stop")
    print("    K        = Grab nearest box   L = Release held box")
    print("    M        = Start macro (Fetch to Pallet 2)")
    print("    T        = Start macro (Shelf A to Table)")
    print("    E        = Toggle emergency stop")
    print("    C        = Cancel / abort (navigation, patrol, macro)")
    print("    Q        = Quit")
    print("  Tip: type multiple keys then Enter (e.g. 'wwwww' = 5x FORWARD)\n")

    bridge.start()
    time.sleep(1.0)

    factory = FactoryController(bridge)
    factory.start()

    def _handle_key(key: str) -> bool:
        """Handle a single-char command. Returns False to quit."""
        if key in ("q",):
            return False
        elif key == "w":
            factory.send_manual_action("FORWARD")
        elif key == "a":
            factory.send_manual_action("LEFT")
        elif key == "d":
            factory.send_manual_action("RIGHT")
        elif key == "s":
            factory.send_manual_action("STOP")
        elif key in ("1", "2", "3", "4", "5", "6"):
            idx = int(key) - 1
            name = factory.select_waypoint(idx)
            print(f"  -> Selected waypoint: {name}")
        elif key == "g":
            factory.go_to_selected()
            print(f"  -> Navigating to {factory._navigator.selected_name}")
        elif key == "p":
            factory.start_patrol()
            print("  -> Patrol started")
        elif key == "o":
            factory.toggle_patrol_pause()
            paused = factory._patrol.paused
            print(f"  -> Patrol {'PAUSED' if paused else 'RESUMED'}")
        elif key == "n":
            factory.skip_patrol_stop()
            print(f"  -> Skipped to {factory._patrol.current_stop}")
        elif key == "k":
            box = factory.grab()
            if box:
                print(f"  -> Grabbed: {box}")
            else:
                print("  -> No box in reach")
        elif key == "l":
            factory.release()
            print("  -> Released box")
        elif key == "m":
            ok = factory.start_macro("Fetch to Pallet 2")
            print(f"  -> Macro 'Fetch to Pallet 2' {'started' if ok else 'not found'}")
        elif key == "t":
            ok = factory.start_macro("Shelf A to Table")
            print(f"  -> Macro 'Shelf A to Table' {'started' if ok else 'not found'}")
        elif key == "e":
            factory.toggle_estop()
            print(f"  -> E-stop {'ACTIVE' if factory._safety.estop_active else 'CLEARED'}")
        elif key == "c":
            factory.abort_macro()
            factory.stop_patrol()
            factory._navigator.cancel_navigation()
            factory.set_mode("MANUAL")
            factory.send_manual_action("STOP")
            print("  -> Cancelled all; back to MANUAL")
        return True

    try:
        while bridge.is_running():
            try:
                line = input("Factory> ").strip().lower()
            except EOFError:
                break

            if not line:
                continue

            # Handle full-word commands
            if line in ("quit", "exit"):
                break

            # Process each character as a separate command
            last_action = None
            for ch in line:
                if not _handle_key(ch):
                    factory.stop()
                    bridge.stop()
                    return
                if ch in ("w", "a", "d", "s"):
                    last_action = {"w": "FORWARD", "a": "LEFT", "d": "RIGHT", "s": "STOP"}[ch]

            # Print summary for movement keys
            if last_action:
                print(f"  -> {last_action} (x{sum(1 for c in line if c in 'wads')})")
    except KeyboardInterrupt:
        pass
    finally:
        factory.stop()
        bridge.stop()


def print_summary(log: list, gt_label: str):
    """Print a summary of the trial results."""
    if not log:
        print("[Summary] No actions logged.")
        return

    total = len(log)
    gated_count = sum(1 for e in log if e.gated)
    avg_confidence = np.mean([e.confidence for e in log])
    avg_latency = np.mean([e.latency_ms for e in log])
    max_latency = max(e.latency_ms for e in log)

    # Count commands issued
    command_counts = {}
    for e in log:
        cmd = e.stable_command
        command_counts[cmd] = command_counts.get(cmd, 0) + 1

    expected_cmd = BRAIN_LABEL_TO_COMMAND[LABEL_MAP[gt_label]]
    correct_count = command_counts.get(expected_cmd, 0)
    accuracy = correct_count / total if total > 0 else 0

    print(f"\n--- Trial Summary ---")
    print(f"  Ground truth: {gt_label}")
    print(f"  Expected command: {expected_cmd}")
    print(f"  Windows processed: {total}")
    print(f"  Gated (low confidence): {gated_count} ({100*gated_count/total:.0f}%)")
    print(f"  Avg confidence: {avg_confidence:.3f}")
    print(f"  Command accuracy: {accuracy:.1%}")
    print(f"  Command distribution: {command_counts}")
    print(f"  Avg latency: {avg_latency:.2f}ms")
    print(f"  Max latency: {max_latency:.2f}ms")
    print(f"---------------------\n")


def main():
    parser = argparse.ArgumentParser(description="ThoughtLink Simulation Demo")
    parser.add_argument("--mock", action="store_true", help="Use mock decoder (no trained model needed)")
    parser.add_argument("--keyboard", action="store_true", help="Manual keyboard control mode")
    parser.add_argument("--factory", action="store_true", help="Factory robot mode with all features")
    parser.add_argument("--model", type=str, default=None, help="Path to ONNX model for BrainDecoder")
    parser.add_argument("--config", type=str, default=None, help="Path to config.json for BrainDecoder")
    parser.add_argument("--trial", type=str, default=None, help="Path to a specific .npz trial file")
    parser.add_argument("--multi", action="store_true", help="Run multi-trial demo (one per label)")
    parser.add_argument("--robot", type=str, default="g1", choices=["g1", "go2"], help="Robot type")
    parser.add_argument("--scene", type=str, default="factory", choices=["factory", "default"], help="Scene type (factory or default)")
    args = parser.parse_args()

    # Factory and keyboard modes don't need data dir / decoder
    if args.factory or args.keyboard:
        bridge = SimulationBridge(decoder=None, robot=args.robot, scene=args.scene)
        if args.factory:
            run_factory_mode(bridge)
            return
        else:
            run_keyboard_mode(bridge)
            return

    # Find data directory
    data_dir = DATA_DIR
    if not data_dir.exists():
        # Try alternative location
        alt = PROJECT_ROOT.parent / "robot_control" / "data"
        if alt.exists():
            data_dir = alt
        else:
            print(f"[Error] Data directory not found: {data_dir}")
            print("  Clone the dataset: git clone https://huggingface.co/datasets/KernelCo/robot_control")
            sys.exit(1)

    # Select trial file
    if args.trial:
        trial_path = Path(args.trial)
    else:
        trial_files = sorted(data_dir.glob("*.npz"))
        if not trial_files:
            print(f"[Error] No .npz files found in {data_dir}")
            sys.exit(1)
        trial_path = trial_files[0]

    # Create decoder
    decoder = None
    if args.model:
        try:
            from training.predict import BrainDecoder
            config_path = args.config or str(PROJECT_ROOT / "training" / "config.json")
            decoder = BrainDecoder(args.model, config_path)
            print(f"[Demo] Loaded BrainDecoder from {args.model}")
        except ImportError:
            print("[Error] Cannot import BrainDecoder. Is training/predict.py available?")
            sys.exit(1)
    elif not args.mock:
        print("[Demo] No model specified. Use --mock for mock decoder or --model for real decoder.")
        args.mock = True

    # Create bridge
    bridge = SimulationBridge(decoder=decoder, robot=args.robot, scene=args.scene)

    # Run selected mode
    if args.multi:
        run_multi_trial_demo(bridge, data_dir)
    elif args.mock:
        run_mock_demo(bridge, trial_path)
    else:
        run_real_demo(bridge, trial_path)


if __name__ == "__main__":
    main()
