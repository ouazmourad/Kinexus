"""Gesture Recognition Layer — converts continuous brain signals into discrete gesture events.

Sits between TemporalStabilizer output and the StateMachine.
Consumes the per-tick stable_command string stream, emits GestureEvent objects on edges.
"""

import time
from enum import Enum
from dataclasses import dataclass
from typing import Optional

from constants import (
    QUICK_CLENCH_MAX_S,
    MEDIUM_HOLD_THRESHOLD_S,
    LONG_HOLD_THRESHOLD_S,
    DOUBLE_CLENCH_WINDOW_S,
    SELECT_WINDOW_S,
    RECLENCH_WINDOW_S,
)


class GestureType(Enum):
    QUICK_CLENCH = "QUICK_CLENCH"         # < 1.5s hold then release
    HOLD_MEDIUM = "HOLD_MEDIUM"           # 2.0-4.0s hold
    HOLD_LONG = "HOLD_LONG"              # > 4.0s hold (Both Fists only)
    DOUBLE_CLENCH = "DOUBLE_CLENCH"       # two quick clenches within 1.0s
    SELECT_SEQUENCE = "SELECT_SEQUENCE"   # long hold Both -> release to L/R -> re-clench Both


@dataclass
class GestureEvent:
    gesture_type: GestureType
    brain_class: str       # "Right Fist", "Left Fist", "Both Fists", "Tongue Tapping"
    duration_s: float
    select_direction: Optional[str] = None  # "left" or "right" for SELECT_SEQUENCE


class _RecogState(Enum):
    IDLE = "IDLE"
    HOLDING = "HOLDING"
    AWAITING_SELECT = "AWAITING_SELECT"
    AWAITING_RECLENCH = "AWAITING_RECLENCH"


# Brain classes that are "active" (not idle/relax)
_ACTIVE_CLASSES = {"Right Fist", "Left Fist", "Left First", "Both Fists", "Both Firsts", "Tongue Tapping"}
_IDLE_CLASSES = {"Relax", "IDLE", None, ""}

# Normalize typos
_NORMALIZE = {
    "Left First": "Left Fist",
    "Both Firsts": "Both Fists",
}


def _normalize(brain_class: str | None) -> str | None:
    if brain_class is None:
        return None
    return _NORMALIZE.get(brain_class, brain_class)


def _is_active(brain_class: str | None) -> bool:
    return brain_class is not None and brain_class in _ACTIVE_CLASSES


def _is_both_fists(brain_class: str | None) -> bool:
    return brain_class in ("Both Fists", "Both Firsts")


class GestureRecognizer:
    """State machine that converts continuous brain class stream into discrete gesture events."""

    def __init__(self):
        self._state = _RecogState.IDLE
        self._hold_class: str | None = None
        self._hold_start: float = 0.0

        # For AWAITING_SELECT / AWAITING_RECLENCH
        self._select_start: float = 0.0
        self._select_direction: str | None = None

        # Double-clench detection
        self._last_quick_class: str | None = None
        self._last_quick_time: float = 0.0

    def update(self, brain_class: str | None) -> Optional[GestureEvent]:
        """Called every tick (~10Hz). Returns a GestureEvent if a gesture completes, else None."""
        now = time.time()
        brain_class = _normalize(brain_class)

        if self._state == _RecogState.IDLE:
            return self._handle_idle(brain_class, now)
        elif self._state == _RecogState.HOLDING:
            return self._handle_holding(brain_class, now)
        elif self._state == _RecogState.AWAITING_SELECT:
            return self._handle_awaiting_select(brain_class, now)
        elif self._state == _RecogState.AWAITING_RECLENCH:
            return self._handle_awaiting_reclench(brain_class, now)
        return None

    def _handle_idle(self, brain_class: str | None, now: float) -> Optional[GestureEvent]:
        """IDLE: waiting for a non-idle class to start a hold."""
        if _is_active(brain_class):
            self._state = _RecogState.HOLDING
            self._hold_class = brain_class
            self._hold_start = now
        return None

    def _handle_holding(self, brain_class: str | None, now: float) -> Optional[GestureEvent]:
        """HOLDING: tracking duration. On release, classify the gesture."""
        duration = now - self._hold_start

        # Still holding same class
        if brain_class == self._hold_class:
            return None

        # Class changed or released
        held_class = self._hold_class

        if not _is_active(brain_class):
            # Released to idle/relax
            self._state = _RecogState.IDLE
            self._hold_class = None

            if duration < QUICK_CLENCH_MAX_S:
                return self._emit_quick_or_double(held_class, duration, now)
            elif duration < LONG_HOLD_THRESHOLD_S:
                return GestureEvent(GestureType.HOLD_MEDIUM, held_class, duration)
            elif _is_both_fists(held_class):
                # Long hold of Both Fists -> enter select sequence
                self._state = _RecogState.AWAITING_SELECT
                self._select_start = now
                self._select_direction = None
                return None
            else:
                return GestureEvent(GestureType.HOLD_LONG, held_class, duration)
        else:
            # Switched to a different active class mid-hold
            # Treat previous as a release, start new hold
            self._hold_class = brain_class
            self._hold_start = now

            if duration < QUICK_CLENCH_MAX_S:
                return self._emit_quick_or_double(held_class, duration, now)
            elif duration < LONG_HOLD_THRESHOLD_S:
                return GestureEvent(GestureType.HOLD_MEDIUM, held_class, duration)
            else:
                if _is_both_fists(held_class):
                    # Check if new class is L/R fist for select sequence
                    if brain_class in ("Left Fist", "Right Fist"):
                        self._state = _RecogState.AWAITING_RECLENCH
                        self._select_start = now
                        self._select_direction = "left" if brain_class == "Left Fist" else "right"
                        return None
                return GestureEvent(GestureType.HOLD_LONG, held_class, duration)

    def _handle_awaiting_select(self, brain_class: str | None, now: float) -> Optional[GestureEvent]:
        """AWAITING_SELECT: after Both Fists long hold released, wait for L/R fist."""
        elapsed = now - self._select_start

        if elapsed > SELECT_WINDOW_S:
            # Timeout - emit HOLD_LONG
            self._state = _RecogState.IDLE
            if _is_active(brain_class):
                self._state = _RecogState.HOLDING
                self._hold_class = brain_class
                self._hold_start = now
            return GestureEvent(GestureType.HOLD_LONG, "Both Fists", LONG_HOLD_THRESHOLD_S)

        if brain_class in ("Left Fist", "Left First", "Right Fist"):
            direction = "left" if brain_class in ("Left Fist", "Left First") else "right"
            self._state = _RecogState.AWAITING_RECLENCH
            self._select_start = now
            self._select_direction = direction
            return None

        return None

    def _handle_awaiting_reclench(self, brain_class: str | None, now: float) -> Optional[GestureEvent]:
        """AWAITING_RECLENCH: after direction fist detected, wait for Both Fists re-clench."""
        elapsed = now - self._select_start

        if elapsed > RECLENCH_WINDOW_S:
            # Timeout - emit HOLD_LONG
            self._state = _RecogState.IDLE
            if _is_active(brain_class):
                self._state = _RecogState.HOLDING
                self._hold_class = brain_class
                self._hold_start = now
            return GestureEvent(GestureType.HOLD_LONG, "Both Fists", LONG_HOLD_THRESHOLD_S)

        if _is_both_fists(brain_class):
            # Re-clench detected -> SELECT_SEQUENCE
            self._state = _RecogState.HOLDING
            self._hold_class = brain_class
            self._hold_start = now
            direction = self._select_direction
            self._select_direction = None
            return GestureEvent(
                GestureType.SELECT_SEQUENCE,
                "Both Fists",
                LONG_HOLD_THRESHOLD_S,
                select_direction=direction,
            )

        return None

    def _emit_quick_or_double(self, brain_class: str, duration: float, now: float) -> GestureEvent:
        """Check if this quick clench is a double-clench with the previous one."""
        if (self._last_quick_class == brain_class and
                now - self._last_quick_time < DOUBLE_CLENCH_WINDOW_S):
            self._last_quick_class = None
            self._last_quick_time = 0.0
            return GestureEvent(GestureType.DOUBLE_CLENCH, brain_class, duration)

        self._last_quick_class = brain_class
        self._last_quick_time = now
        return GestureEvent(GestureType.QUICK_CLENCH, brain_class, duration)

    def reset(self):
        """Reset gesture recognizer state."""
        self._state = _RecogState.IDLE
        self._hold_class = None
        self._hold_start = 0.0
        self._select_start = 0.0
        self._select_direction = None
        self._last_quick_class = None
        self._last_quick_time = 0.0
