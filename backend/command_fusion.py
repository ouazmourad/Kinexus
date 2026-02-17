"""Command Fusion — merges brain + voice commands into a single action.

Uses GestureRecognizer for edge-triggered toggle control from brain signals.
"""

import time
from .state_machine import GearStateMachine, RobotAction, Gear
from .gesture import GestureRecognizer, GestureType
from .config import VOICE_OVERRIDE_HOLD_S


class CommandFusion:
    def __init__(self, state_machine: GearStateMachine):
        self.sm = state_machine
        self.gesture = GestureRecognizer()
        self.last_emitted_action = RobotAction.IDLE
        self.voice_override_until = 0.0
        self.last_gesture_result = None  # last handle_gesture() output

    def update(self, brain_result: dict | None, voice_command: dict | None) -> dict:
        """
        Called every tick (~10Hz).

        brain_result: from BrainDecoder.predict()
            {"class": "Right Fist", "command": "...", "confidence": 0.84,
             "stable_command": "ROTATE_RIGHT", "gated": False, "label": "Right Fist"}

        voice_command: parsed voice command dict or None
            {"command_type": "direct_override", "action": "MOVE_FORWARD", ...}

        Returns: {"action": RobotAction, "source": "brain_gesture"|"brain_toggle"|"voice"|"idle", ...}
        """
        now = time.time()

        # Priority 1: Voice commands (always trusted)
        if voice_command is not None:
            action = self._handle_voice_command(voice_command)
            if action is not None:
                self.voice_override_until = now + VOICE_OVERRIDE_HOLD_S
                self.last_emitted_action = action
                self.sm.state.current_action = action
                return {
                    "action": action,
                    "source": "voice",
                    "voice_command": voice_command,
                    "timestamp": now,
                }

        # If voice recently gave a command, hold it
        if now < self.voice_override_until:
            return {
                "action": self.last_emitted_action,
                "source": "voice_hold",
                "timestamp": now,
            }

        # Priority 2: Brain signals → gesture recognition → toggle control
        brain_label = None
        if brain_result and not brain_result.get("gated", True):
            brain_label = brain_result.get("label")

        # Feed brain label into gesture recognizer every tick
        gesture_event = self.gesture.update(brain_label)

        if gesture_event is not None:
            # Gesture completed — process through state machine
            result = self.sm.handle_gesture(gesture_event)
            self.last_gesture_result = result
            action = result["action"]
            self.sm.state.current_action = action
            self.last_emitted_action = action

            return {
                "action": action,
                "source": "brain_gesture",
                "gesture_type": gesture_event.gesture_type.value,
                "brain_class": gesture_event.brain_class,
                "duration_s": gesture_event.duration_s,
                "toggle_changed": result.get("toggle_changed", False),
                "select_direction": gesture_event.select_direction,
                "orchestration_event": result.get("orchestration_event"),
                "orchestration_task": result.get("orchestration_task"),
                "confidence": brain_result.get("confidence", 0) if brain_result else 0,
                "gear": self.sm.state.gear.value,
                "timestamp": now,
            }

        # No gesture this tick — sustain toggled action if one is active
        if self.sm.state.toggled_action is not None:
            action = self.sm.state.toggled_action
            self.sm.state.current_action = action
            self.last_emitted_action = action
            return {
                "action": action,
                "source": "brain_toggle",
                "confidence": brain_result.get("confidence", 0) if brain_result else 0,
                "gear": self.sm.state.gear.value,
                "timestamp": now,
            }

        # Priority 3: No input -> IDLE
        if self.last_emitted_action != RobotAction.IDLE:
            self.last_emitted_action = RobotAction.IDLE
            self.sm.state.current_action = RobotAction.IDLE

        return {
            "action": RobotAction.IDLE,
            "source": "idle",
            "timestamp": now,
        }

    def _handle_voice_command(self, cmd: dict) -> RobotAction | None:
        """Convert a parsed voice command to a robot action.

        Returns RobotAction for direct commands.
        For NAVIGATE commands, returns None (handled by control_loop autopilot).
        For CANCEL_NAV, returns STOP and signals cancellation.
        """
        command_type = cmd.get("command_type", "")
        action_str = cmd.get("action", "")

        if command_type == "direct_override":
            action_map = {
                "STOP": RobotAction.STOP,
                "EMERGENCY_STOP": RobotAction.EMERGENCY_STOP,
                "MOVE_FORWARD": RobotAction.MOVE_FORWARD,
                "MOVE_BACKWARD": RobotAction.MOVE_BACKWARD,
                "ROTATE_LEFT": RobotAction.ROTATE_LEFT,
                "ROTATE_RIGHT": RobotAction.ROTATE_RIGHT,
                "GRAB": RobotAction.GRAB,
                "RELEASE": RobotAction.RELEASE,
                "BACKFLIP": RobotAction.BACKFLIP,
            }

            if action_str == "SHIFT_GEAR":
                self.sm.shift_gear()
                return RobotAction.IDLE
            elif action_str == "SET_GEAR_FORWARD":
                self.sm.set_gear(Gear.FORWARD)
                return RobotAction.IDLE
            elif action_str == "SET_GEAR_REVERSE":
                self.sm.set_gear(Gear.REVERSE)
                return RobotAction.IDLE
            elif action_str == "SET_GEAR_NEUTRAL":
                self.sm.set_gear(Gear.NEUTRAL)
                return RobotAction.IDLE
            elif action_str == "SET_GEAR_ORCHESTRATE":
                self.sm.set_gear(Gear.ORCHESTRATE)
                return RobotAction.IDLE
            elif action_str == "CANCEL_NAV":
                return RobotAction.STOP

            return action_map.get(action_str)

        # Automated NAVIGATE commands are handled by the control loop's autopilot
        if command_type == "automated" and action_str == "NAVIGATE":
            return None

        return None

    def reset(self):
        """Reset fusion state."""
        self.gesture.reset()
        self.last_emitted_action = RobotAction.IDLE
        self.voice_override_until = 0.0
        self.last_gesture_result = None
