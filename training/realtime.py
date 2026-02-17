"""
ThoughtLink — TemporalStabilizer
Confidence gating, majority voting, and hysteresis for stable real-time predictions.
"""
import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import (
    CONFIDENCE_THRESHOLD, SMOOTHING_WINDOW, HYSTERESIS_COUNT,
    BRAIN_LABEL_TO_COMMAND, LABEL_NAMES,
)


class TemporalStabilizer:
    """Stabilizes real-time BCI predictions using three mechanisms:

    1. Confidence gating: Suppress predictions with softmax confidence < threshold → IDLE
    2. Majority voting: Keep deque of last N high-confidence predictions, emit if majority agrees
    3. Hysteresis: Require K consecutive same-class predictions before switching command

    This prevents flicker/jitter in the robot control output.
    """

    def __init__(self, confidence_threshold=CONFIDENCE_THRESHOLD,
                 smoothing_window=SMOOTHING_WINDOW,
                 hysteresis_count=HYSTERESIS_COUNT,
                 label_names=None):
        self.confidence_threshold = confidence_threshold
        self.smoothing_window = smoothing_window
        self.hysteresis_count = hysteresis_count
        self.label_names = label_names or LABEL_NAMES

        # State
        self.vote_buffer = deque(maxlen=smoothing_window)
        self.consecutive_count = 0
        self.last_stable_class = None
        self.current_command = "STOP"

    def update(self, predicted_class: int, confidence: float) -> dict:
        """Process a new prediction and return stabilized output.

        Args:
            predicted_class: Raw predicted class index
            confidence: Max softmax probability

        Returns:
            dict with:
                - raw_class: Original prediction
                - raw_confidence: Original confidence
                - gated: Whether prediction was suppressed
                - vote_class: Majority vote result (or None)
                - stable_command: Current stable robot command
                - label: Human-readable label for stable command
                - switched: Whether command changed this update
        """
        gated = confidence < self.confidence_threshold

        if not gated:
            self.vote_buffer.append(predicted_class)

        # Majority voting
        vote_class = None
        if len(self.vote_buffer) >= 1:
            # Count occurrences in buffer
            counts = {}
            for cls in self.vote_buffer:
                counts[cls] = counts.get(cls, 0) + 1

            # Find majority
            max_cls = max(counts, key=counts.get)
            max_count = counts[max_cls]

            # Need at least 3/5 (or majority of buffer) to declare winner
            threshold = max(1, len(self.vote_buffer) * 3 // 5)
            if max_count >= threshold:
                vote_class = max_cls

        # Hysteresis
        switched = False
        if vote_class is not None:
            if vote_class == self.last_stable_class:
                self.consecutive_count += 1
            else:
                self.consecutive_count = 1

            if self.consecutive_count >= self.hysteresis_count:
                new_command = BRAIN_LABEL_TO_COMMAND.get(vote_class, "STOP")
                if new_command != self.current_command:
                    switched = True
                    self.current_command = new_command
                self.last_stable_class = vote_class

        # Build result
        label_str = self.label_names[self.last_stable_class] if self.last_stable_class is not None else "IDLE"

        return {
            "raw_class": predicted_class,
            "raw_confidence": round(confidence, 4),
            "gated": gated,
            "vote_class": vote_class,
            "stable_command": self.current_command,
            "label": label_str,
            "switched": switched,
            "consecutive_count": self.consecutive_count,
            "buffer_size": len(self.vote_buffer),
        }

    def reset(self):
        """Clear all state between sessions."""
        self.vote_buffer.clear()
        self.consecutive_count = 0
        self.last_stable_class = None
        self.current_command = "STOP"


if __name__ == "__main__":
    print("=" * 60)
    print("ThoughtLink — TemporalStabilizer Test")
    print("=" * 60)

    stabilizer = TemporalStabilizer()

    # Simulate a sequence of noisy predictions
    test_sequence = [
        # (class, confidence) — simulating Right Fist with noise
        (0, 0.85), (0, 0.90), (1, 0.55),  # gated
        (0, 0.80), (0, 0.75), (0, 0.88),
        # Switch to Left Fist
        (1, 0.82), (1, 0.79), (1, 0.91),
        (1, 0.85), (1, 0.77),
        # Noisy / low confidence
        (3, 0.45), (2, 0.50), (1, 0.88),
    ]

    for i, (cls, conf) in enumerate(test_sequence):
        result = stabilizer.update(cls, conf)
        print(f"Step {i:2d}: class={cls} conf={conf:.2f} -> "
              f"gated={result['gated']} vote={result['vote_class']} "
              f"cmd={result['stable_command']} switch={result['switched']} "
              f"consec={result['consecutive_count']}")
