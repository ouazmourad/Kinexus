"""Gear State Machine — core control logic for ThoughtLink.

Supports toggle-based control via handle_gesture() and orchestration gear.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

from constants import FACTORY_WAYPOINT_ORDER


class Gear(Enum):
    NEUTRAL = "NEUTRAL"
    FORWARD = "FORWARD"
    REVERSE = "REVERSE"
    ORCHESTRATE = "ORCHESTRATE"


class RobotAction(Enum):
    IDLE = "IDLE"
    ROTATE_LEFT = "ROTATE_LEFT"
    ROTATE_RIGHT = "ROTATE_RIGHT"
    MOVE_FORWARD = "MOVE_FORWARD"
    MOVE_BACKWARD = "MOVE_BACKWARD"
    GRAB = "GRAB"
    RELEASE = "RELEASE"
    HOLD = "HOLD"
    STOP = "STOP"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    BACKFLIP = "BACKFLIP"


class OrchestrationPhase(Enum):
    SELECTING_ACTION = "SELECTING_ACTION"
    SELECTING_LANDMARK = "SELECTING_LANDMARK"
    SELECTING_ROBOT = "SELECTING_ROBOT"


class OrchestrationAction(Enum):
    SELECT_ROBOT = "SELECT_ROBOT"
    MOVE_TO = "MOVE_TO"
    CARRY_TO = "CARRY_TO"
    STACK_TO = "STACK_TO"
    BACKFLIP = "BACKFLIP"


ORCHESTRATION_ACTIONS = list(OrchestrationAction)
GEAR_CYCLE = [Gear.NEUTRAL, Gear.FORWARD, Gear.REVERSE, Gear.ORCHESTRATE]


@dataclass
class OrchestrationState:
    phase: OrchestrationPhase = OrchestrationPhase.SELECTING_ACTION
    action_index: int = 0
    landmark_index: int = 0
    # Robot selection
    robot_ids: list = field(default_factory=list)
    robot_cycle_index: int = 0
    selected_robot_ids: set = field(default_factory=set)


@dataclass
class RobotState:
    gear: Gear = Gear.NEUTRAL
    holding_item: bool = False
    current_action: RobotAction = RobotAction.IDLE
    last_action_time: float = 0.0
    override_active: bool = False
    override_robot_id: Optional[str] = None
    # Toggle state
    toggled_action: Optional[RobotAction] = None
    toggled_class: Optional[str] = None


class GearStateMachine:
    def __init__(self):
        self.state = RobotState()
        self._gear_index = 0
        self._orch = OrchestrationState()
        self._landmarks = list(FACTORY_WAYPOINT_ORDER)

    def shift_gear(self) -> Gear:
        """Cycle to next gear. Called on Tongue Tap."""
        old_gear = self.state.gear
        self._gear_index = (self._gear_index + 1) % len(GEAR_CYCLE)
        self.state.gear = GEAR_CYCLE[self._gear_index]
        new_gear = self.state.gear

        # Handle transitions to/from orchestrate
        if old_gear != Gear.ORCHESTRATE and new_gear == Gear.ORCHESTRATE:
            self._enter_orchestration()
        elif old_gear == Gear.ORCHESTRATE and new_gear != Gear.ORCHESTRATE:
            self._exit_orchestration()

        return self.state.gear

    def set_gear(self, gear: Gear) -> Gear:
        """Directly set gear (voice command or API)."""
        old_gear = self.state.gear
        self.state.gear = gear
        try:
            self._gear_index = GEAR_CYCLE.index(gear)
        except ValueError:
            self._gear_index = 0

        if old_gear != Gear.ORCHESTRATE and gear == Gear.ORCHESTRATE:
            self._enter_orchestration()
        elif old_gear == Gear.ORCHESTRATE and gear != Gear.ORCHESTRATE:
            self._exit_orchestration()

        return gear

    def handle_gesture(self, gesture) -> dict:
        """Handle a GestureEvent, return result dict.

        Returns: {
            "action": RobotAction,
            "toggle_changed": bool,
            "orchestration_event": str | None,  # "confirm", "cancel", "cycle_action", "cycle_landmark", "dispatch"
            "orchestration_task": dict | None,   # dispatched task details
        }
        """
        from .gesture import GestureType

        result = {
            "action": RobotAction.IDLE,
            "toggle_changed": False,
            "orchestration_event": None,
            "orchestration_task": None,
        }

        gt = gesture.gesture_type
        bc = gesture.brain_class

        # SELECT_SEQUENCE is handled by control loop for robot selection (any gear)
        if gt == GestureType.SELECT_SEQUENCE:
            result["action"] = self.state.toggled_action or RobotAction.IDLE
            return result

        # Tongue Tapping quick clench -> shift gear (no toggle change)
        if bc == "Tongue Tapping" and gt == GestureType.QUICK_CLENCH:
            self.shift_gear()
            result["action"] = self.state.toggled_action or RobotAction.IDLE
            return result

        # Orchestrate gear has its own logic
        if self.state.gear == Gear.ORCHESTRATE:
            return self._handle_orchestrate_gesture(gesture, result)

        # Normal gears: toggle-based control
        if gt == GestureType.QUICK_CLENCH:
            action = self._resolve_class_to_action(bc)
            if action == RobotAction.IDLE:
                result["action"] = self.state.toggled_action or RobotAction.IDLE
                return result

            # Toggle logic
            if self.state.toggled_action == action and self.state.toggled_class == bc:
                # Same action -> toggle OFF
                self.state.toggled_action = None
                self.state.toggled_class = None
                # When toggling HOLD off, send RELEASE to drop the item
                if action == RobotAction.HOLD:
                    result["action"] = RobotAction.RELEASE
                else:
                    result["action"] = RobotAction.IDLE
            else:
                # Different action or new -> auto-cancel previous, toggle ON
                # If we had HOLD toggled and are switching, release first
                if self.state.toggled_action == RobotAction.HOLD:
                    # Will be handled by sim as a one-shot release
                    pass
                self.state.toggled_action = action
                self.state.toggled_class = bc
                result["action"] = action
            result["toggle_changed"] = True
            return result

        # Other gesture types in normal gears: no toggle change
        result["action"] = self.state.toggled_action or RobotAction.IDLE
        return result

    def _handle_orchestrate_gesture(self, gesture, result: dict) -> dict:
        """Handle gestures when in ORCHESTRATE gear."""
        from .gesture import GestureType

        gt = gesture.gesture_type
        bc = gesture.brain_class

        # SELECTING_ROBOT phase has special Both-Fists quick-clench behavior
        if self._orch.phase == OrchestrationPhase.SELECTING_ROBOT:
            return self._handle_robot_selection_gesture(gesture, result)

        # SELECTING_ACTION / SELECTING_LANDMARK phases
        # L/R fist quick clench -> cycle options
        if gt == GestureType.QUICK_CLENCH:
            if bc == "Right Fist":
                self._orch_cycle(1)
                result["orchestration_event"] = "cycle"
            elif bc in ("Left Fist", "Left First"):
                self._orch_cycle(-1)
                result["orchestration_event"] = "cycle"

        # Both Fists medium hold -> confirm selection
        elif gt == GestureType.HOLD_MEDIUM:
            if bc in ("Both Fists", "Both Firsts"):
                task = self._orch_confirm()
                if task:
                    result["orchestration_event"] = "dispatch"
                    result["orchestration_task"] = task
                else:
                    result["orchestration_event"] = "confirm"

        # Both Fists double clench -> cancel (also cancels active tasks)
        elif gt == GestureType.DOUBLE_CLENCH:
            if bc in ("Both Fists", "Both Firsts"):
                self._orch_cancel()
                result["orchestration_event"] = "cancel"

        result["action"] = self.state.toggled_action or RobotAction.IDLE
        return result

    def _handle_robot_selection_gesture(self, gesture, result: dict) -> dict:
        """Handle gestures in SELECTING_ROBOT phase."""
        from .gesture import GestureType

        gt = gesture.gesture_type
        bc = gesture.brain_class

        if gt == GestureType.QUICK_CLENCH:
            if bc == "Right Fist":
                n = max(len(self._orch.robot_ids), 1)
                self._orch.robot_cycle_index = (self._orch.robot_cycle_index + 1) % n
                result["orchestration_event"] = "cycle"
            elif bc in ("Left Fist", "Left First"):
                n = max(len(self._orch.robot_ids), 1)
                self._orch.robot_cycle_index = (self._orch.robot_cycle_index - 1) % n
                result["orchestration_event"] = "cycle"
            elif bc in ("Both Fists", "Both Firsts"):
                # Toggle selection for currently highlighted robot
                if self._orch.robot_ids:
                    rid = self._orch.robot_ids[self._orch.robot_cycle_index]
                    if rid in self._orch.selected_robot_ids:
                        self._orch.selected_robot_ids.discard(rid)
                    else:
                        self._orch.selected_robot_ids.add(rid)
                result["orchestration_event"] = "toggle_robot"

        elif gt == GestureType.HOLD_MEDIUM:
            if bc in ("Both Fists", "Both Firsts"):
                task = self._orch_confirm()
                if task:
                    result["orchestration_event"] = "dispatch"
                    result["orchestration_task"] = task
                else:
                    result["orchestration_event"] = "confirm"

        elif gt == GestureType.DOUBLE_CLENCH:
            if bc in ("Both Fists", "Both Firsts"):
                self._orch_cancel()
                result["orchestration_event"] = "cancel"

        result["action"] = self.state.toggled_action or RobotAction.IDLE
        return result

    def _resolve_class_to_action(self, brain_class: str) -> RobotAction:
        """Map a brain class + current gear -> robot action (without side effects like gear shift)."""
        if brain_class == "Right Fist":
            return RobotAction.ROTATE_RIGHT
        elif brain_class in ("Left Fist", "Left First"):
            return RobotAction.ROTATE_LEFT
        elif brain_class in ("Both Fists", "Both Firsts"):
            if self.state.gear == Gear.FORWARD:
                return RobotAction.MOVE_FORWARD
            elif self.state.gear == Gear.REVERSE:
                return RobotAction.MOVE_BACKWARD
            else:  # NEUTRAL
                return self._peek_grab()
        elif brain_class == "Relax":
            return RobotAction.IDLE
        return RobotAction.IDLE

    def _peek_grab(self) -> RobotAction:
        """Return HOLD — a toggle action that grabs on activate and releases on deactivate."""
        return RobotAction.HOLD

    def resolve_brain_command(self, brain_class: str) -> RobotAction:
        """Legacy: map a brain signal class + current gear state -> robot action.
        Used for manual commands (backward compat).
        """
        if brain_class == "Right Fist":
            return RobotAction.ROTATE_RIGHT
        elif brain_class == "Left Fist" or brain_class == "Left First":
            return RobotAction.ROTATE_LEFT
        elif brain_class == "Tongue Tapping":
            self.shift_gear()
            return RobotAction.IDLE
        elif brain_class == "Both Fists" or brain_class == "Both Firsts":
            if self.state.gear == Gear.FORWARD:
                return RobotAction.MOVE_FORWARD
            elif self.state.gear == Gear.REVERSE:
                return RobotAction.MOVE_BACKWARD
            else:  # NEUTRAL
                return self._toggle_grab()
        elif brain_class == "Relax":
            return RobotAction.IDLE
        return RobotAction.IDLE

    def _toggle_grab(self) -> RobotAction:
        """Toggle hold in neutral gear (legacy path)."""
        if self.state.holding_item:
            self.state.holding_item = False
            return RobotAction.RELEASE
        else:
            self.state.holding_item = True
            return RobotAction.HOLD

    # --- Orchestration sub-methods ---

    def _enter_orchestration(self):
        """Reset orchestration state when entering ORCHESTRATE gear."""
        robot_ids = self._orch.robot_ids
        selected_robot_ids = self._orch.selected_robot_ids
        self._orch = OrchestrationState(robot_ids=robot_ids, selected_robot_ids=selected_robot_ids)

    def _exit_orchestration(self):
        """Clean up when leaving ORCHESTRATE gear."""
        robot_ids = self._orch.robot_ids
        selected_robot_ids = self._orch.selected_robot_ids
        self._orch = OrchestrationState(robot_ids=robot_ids, selected_robot_ids=selected_robot_ids)

    def _orch_cycle(self, direction: int):
        """Cycle current selection in orchestration by direction (-1 or +1)."""
        if self._orch.phase == OrchestrationPhase.SELECTING_ACTION:
            self._orch.action_index = (self._orch.action_index + direction) % len(ORCHESTRATION_ACTIONS)
        else:
            self._orch.landmark_index = (self._orch.landmark_index + direction) % len(self._landmarks)

    def _orch_confirm(self) -> Optional[dict]:
        """Confirm current orchestration selection. Returns task dict if dispatching.
        Stays in ORCHESTRATE gear after dispatch (resets to SELECTING_ACTION).
        """
        if self._orch.phase == OrchestrationPhase.SELECTING_ACTION:
            action = ORCHESTRATION_ACTIONS[self._orch.action_index]
            if action == OrchestrationAction.SELECT_ROBOT:
                self._orch.phase = OrchestrationPhase.SELECTING_ROBOT
                self._orch.robot_cycle_index = 0
                return None
            else:
                self._orch.phase = OrchestrationPhase.SELECTING_LANDMARK
                self._orch.landmark_index = 0
                return None
        elif self._orch.phase == OrchestrationPhase.SELECTING_ROBOT:
            # Confirm robot selection
            task = {
                "action": "SELECT_ROBOT",
                "selected_robot_ids": list(self._orch.selected_robot_ids),
            }
            # Back to action selection (stay in ORCHESTRATE)
            self._orch.phase = OrchestrationPhase.SELECTING_ACTION
            return task
        else:
            # SELECTING_LANDMARK → dispatch task (stay in ORCHESTRATE)
            action = ORCHESTRATION_ACTIONS[self._orch.action_index]
            landmark = self._landmarks[self._orch.landmark_index]
            task = {
                "action": action.value,
                "landmark": landmark,
                "action_index": self._orch.action_index,
                "landmark_index": self._orch.landmark_index,
            }
            # Reset to action selection (keep gear on ORCHESTRATE)
            self._orch.phase = OrchestrationPhase.SELECTING_ACTION
            self._orch.landmark_index = 0
            return task

    def _orch_cancel(self):
        """Cancel current orchestration selection — go back or reset.
        In SELECTING_ACTION phase, emits cancel event for control loop to cancel active tasks.
        """
        if self._orch.phase == OrchestrationPhase.SELECTING_LANDMARK:
            self._orch.phase = OrchestrationPhase.SELECTING_ACTION
        elif self._orch.phase == OrchestrationPhase.SELECTING_ROBOT:
            self._orch.phase = OrchestrationPhase.SELECTING_ACTION
        else:
            # Already in SELECTING_ACTION — preserve robot selection state
            self._orch.action_index = 0
            self._orch.landmark_index = 0

    def set_robot_ids(self, robot_ids: list[str]):
        """Set available robot IDs for orchestration robot selection."""
        self._orch.robot_ids = robot_ids

    def get_orchestration_state(self) -> Optional[dict]:
        """Return orchestration state for frontend. None if not in ORCHESTRATE gear."""
        if self.state.gear != Gear.ORCHESTRATE:
            return None
        state = {
            "phase": self._orch.phase.value,
            "action_name": ORCHESTRATION_ACTIONS[self._orch.action_index].value,
            "action_index": self._orch.action_index,
            "landmark_name": self._landmarks[self._orch.landmark_index],
            "landmark_index": self._orch.landmark_index,
            "actions": [a.value for a in ORCHESTRATION_ACTIONS],
            "landmarks": self._landmarks,
        }
        if self._orch.phase == OrchestrationPhase.SELECTING_ROBOT:
            state["robot_ids"] = self._orch.robot_ids
            state["robot_cycle_index"] = self._orch.robot_cycle_index
            state["selected_robot_ids"] = list(self._orch.selected_robot_ids)
        return state

    def reset(self):
        """Reset state machine to defaults."""
        self.state = RobotState()
        self._gear_index = 0
        self._orch = OrchestrationState()

    def get_state_snapshot(self) -> dict:
        """Return current state for frontend broadcast."""
        return {
            "gear": self.state.gear.value,
            "holding_item": self.state.holding_item,
            "current_action": self.state.current_action.value,
            "override_active": self.state.override_active,
            "override_robot_id": self.state.override_robot_id,
            "toggled_action": self.state.toggled_action.value if self.state.toggled_action else None,
            "toggled_class": self.state.toggled_class,
        }
