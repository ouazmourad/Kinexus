"""Main Control Loop — runs at ~10Hz, orchestrates brain + voice + sim."""

import time
import asyncio
import sys
from pathlib import Path

import numpy as np

from .state_machine import GearStateMachine, RobotAction, Gear, OrchestrationAction
from .command_fusion import CommandFusion
from .sim_bridge import SimBridge
from .eeg_source import EEGReplaySource, TestEEGSource
from .autopilot import Autopilot
from .robot_manager import RobotManager
from .gesture import GestureType, GestureEvent
from voice.command_parser import CommandParser, CommandSequence
from voice.tts_feedback import VoiceFeedback
from .config import (
    EEG_DATA_DIR,
    TICK_INTERVAL,
    MODEL_PATH,
    MODEL_CONFIG_PATH,
    BRAIN_LABEL_TO_COMMAND,
    LABEL_MAP,
    LABEL_NAMES,
    CONFIDENCE_THRESHOLD,
)

# Try to import Joshua's BrainDecoder
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from training.predict import BrainDecoder
    DECODER_AVAILABLE = True
except ImportError:
    DECODER_AVAILABLE = False
    print("[ControlLoop] BrainDecoder not available — using demo mode")


CANCEL_CONFIRM_TIMEOUT_S = 5.0

# Map CommandParser action names to CommandFusion action names
_VOICE_ACTION_MAP = {
    "FORWARD": "MOVE_FORWARD",
    "BACKWARD": "MOVE_BACKWARD",
    "LEFT": "ROTATE_LEFT",
    "RIGHT": "ROTATE_RIGHT",
    "STOP_ALL": "STOP",
}


class ControlLoop:
    def __init__(self, broadcast_fn):
        self.broadcast = broadcast_fn

        # Multi-robot manager (contains per-robot state machines)
        self.robot_manager = RobotManager()

        # Fusion uses the selected robot's state machine
        self.fusion = CommandFusion(self.robot_manager.selected_sm)

        # Sim bridge (multi-robot aware)
        self.sim = SimBridge()

        self._voice_parser = CommandParser()

        # Voice feedback (ElevenLabs TTS with cooldowns)
        self.tts = VoiceFeedback()

        # Initialize EEG source
        try:
            self.eeg_source = EEGReplaySource(EEG_DATA_DIR)
            if not self.eeg_source.ready:
                self.eeg_source = None
        except Exception:
            self.eeg_source = None

        # Input enable flags
        self.brain_enabled = True
        self.voice_enabled = True
        self.eeg_stream_enabled = True

        # Test mode
        self._test_mode = False
        self._test_eeg_source = None

        # Brain simulator (bypasses EEG + classifier entirely)
        self._sim_brain_class = None  # None = off, 0-4 = simulated class index

        # Voice command queue
        self._voice_queue: list[dict] = []
        self._voice_lock = asyncio.Lock()

        # Action queue for multi-step voice commands (e.g. "go to shelf A and grab")
        self._action_queue: list[dict] = []
        self._action_queue_label: str = ""       # human-readable description
        self._action_queue_total: int = 0        # total steps in current sequence
        self._waiting_for_arrival: bool = False   # True while autopilot is navigating

        # Per-robot autopilots
        self._autopilots: dict[str, Autopilot] = {}

        # Sequential task queue (for logistics tasks on multiple robots)
        self._sequential_tasks: list[dict] = []

        # Cancel confirmation state
        self._cancel_confirm_pending = False
        self._cancel_confirm_time = 0.0

        # Set robot IDs on all state machines for orchestration
        robot_ids = [r.id for r in self.robot_manager.robots]
        for sm in self.robot_manager.state_machines.values():
            sm.set_robot_ids(robot_ids)

        # Metrics
        self.tick_count = 0
        self.latencies: list[float] = []
        self.running = False

        # Brain decoder
        self._brain_decoder = None
        if DECODER_AVAILABLE:
            model_path = Path(MODEL_PATH)
            config_path = Path(MODEL_CONFIG_PATH)
            if model_path.exists():
                try:
                    self._brain_decoder = BrainDecoder(str(model_path), str(config_path))
                    print(f"[ControlLoop] Loaded BrainDecoder from {model_path}")
                except Exception as e:
                    print(f"[ControlLoop] Failed to load BrainDecoder: {e}")

    @property
    def state_machine(self):
        """Backward-compat: selected robot's state machine."""
        return self.robot_manager.selected_sm

    async def start(self):
        """Start the simulation and begin the control loop."""
        self.sim.start()
        self.running = True
        print("[ControlLoop] Started")

    async def stop(self):
        """Stop the control loop and simulation."""
        self.running = False
        self.sim.stop()
        print("[ControlLoop] Stopped")

    async def push_voice_command(self, transcript: str, confidence: float = 1.0):
        """Queue a voice transcript for processing on next tick.

        Multi-step commands (e.g. "go to shelf A and grab the box") are
        parsed into a CommandSequence and fed into the action queue so
        steps execute one after another.
        """
        seq = self._voice_parser.parse_sequence(transcript, confidence)
        if not seq:
            return

        if len(seq.steps) > 1:
            # Multi-step: load the action queue
            await self._load_action_queue(seq)
        else:
            # Single step: use the existing voice queue for backward compat
            cmd = seq.steps[0]
            action = _VOICE_ACTION_MAP.get(cmd.action, cmd.action)
            async with self._voice_lock:
                self._voice_queue.append({
                    "command_type": cmd.command_type,
                    "action": action,
                    "raw_text": seq.raw_text,
                    "target": cmd.target,
                })
            # Acknowledge navigation commands with TTS
            if cmd.action == "NAVIGATE" and cmd.target:
                await self._speak(
                    f"Navigating to {cmd.target}", "voice_ack", priority=1
                )
            elif cmd.action in ("GRAB", "RELEASE", "STOP_ALL", "EMERGENCY_STOP"):
                await self._speak(
                    f"Command received: {cmd.action.replace('_', ' ').lower()}",
                    "voice_ack", priority=1
                )

    async def _load_action_queue(self, seq: CommandSequence):
        """Load a multi-step command sequence into the action queue."""
        self._action_queue.clear()
        self._waiting_for_arrival = False
        self._action_queue_label = seq.raw_text
        steps = []
        for cmd in seq.steps:
            action = _VOICE_ACTION_MAP.get(cmd.action, cmd.action)
            steps.append({
                "action": action,
                "target": cmd.target,
                "command_type": cmd.command_type,
            })
        self._action_queue = steps
        self._action_queue_total = len(steps)

        await self.broadcast({
            "type": "command_log",
            "source": "voice",
            "action": f"SEQUENCE ({len(steps)} steps)",
            "text": seq.raw_text,
            "timestamp": time.time(),
        })
        print(f"[ControlLoop] Loaded {len(steps)}-step voice sequence: {seq.raw_text}")
        await self._speak(
            f"Executing {len(steps)} step sequence: {seq.raw_text}",
            "voice_ack", priority=1
        )
        # Kick off the first step immediately
        await self._advance_action_queue()

    async def push_manual_command(self, action_str: str):
        """Inject a manual command. BCI-mapped actions route through the gesture/toggle
        pipeline so the brain simulator and manual controls follow the same rules."""
        selected = self.robot_manager.selected_robot
        sm = self.robot_manager.selected_sm

        # BCI-mapped actions → create synthetic gesture events
        _BCI_MAP = {
            "ROTATE_LEFT": ("Left Fist", GestureType.QUICK_CLENCH),
            "ROTATE_RIGHT": ("Right Fist", GestureType.QUICK_CLENCH),
            "BOTH_FISTS": ("Both Fists", GestureType.QUICK_CLENCH),
            "SHIFT_GEAR": ("Tongue Tapping", GestureType.QUICK_CLENCH),
            "ORCH_CONFIRM": ("Both Fists", GestureType.HOLD_MEDIUM),
            "ORCH_CANCEL": ("Both Fists", GestureType.DOUBLE_CLENCH),
        }

        if action_str in _BCI_MAP:
            brain_class, gesture_type = _BCI_MAP[action_str]
            has_active_nav = any(ap.active for ap in self._autopilots.values())

            # Double-clench Both during active nav → cancel confirmation flow
            if (gesture_type == GestureType.DOUBLE_CLENCH and
                    brain_class == "Both Fists" and
                    (has_active_nav or self._cancel_confirm_pending)):
                if self._cancel_confirm_pending:
                    self._cancel_active_tasks()
                    self._cancel_confirm_pending = False
                    await self.broadcast({
                        "type": "cancel_confirmed",
                        "timestamp": time.time(),
                    })
                else:
                    self._cancel_confirm_pending = True
                    self._cancel_confirm_time = time.time()
                    nav_descs = []
                    for rid, ap in self._autopilots.items():
                        if ap.active:
                            nav_descs.append(f"NAV to {ap.target_name}")
                    await self.broadcast({
                        "type": "cancel_confirm_prompt",
                        "description": "; ".join(nav_descs) if nav_descs else "active task",
                        "timestamp": time.time(),
                    })
                return

            duration = 2.5 if gesture_type == GestureType.HOLD_MEDIUM else 0.5
            gesture = GestureEvent(gesture_type, brain_class, duration)
            result = sm.handle_gesture(gesture)
            action = result["action"]

            # Handle orchestration dispatch from manual controls
            if result.get("orchestration_task"):
                await self._dispatch_orchestration_task(result["orchestration_task"])

            # Handle orchestration cancel from manual controls (no active nav)
            if result.get("orchestration_event") == "cancel":
                self._cancel_active_tasks()

            self.sim.execute(action, selected.id)
            sm.state.current_action = action
            return

        # STOP / RELAX → clear toggled action and stop
        if action_str in ("STOP", "RELAX"):
            sm.state.toggled_action = None
            sm.state.toggled_class = None
            action = RobotAction.IDLE
            self.sim.execute(action, selected.id)
            sm.state.current_action = action
            return

        # Direct actions (GRAB, RELEASE, MOVE_FORWARD, BACKFLIP, etc.) → execute directly
        action_map = {
            "MOVE_FORWARD": RobotAction.MOVE_FORWARD,
            "MOVE_BACKWARD": RobotAction.MOVE_BACKWARD,
            "GRAB": RobotAction.GRAB,
            "RELEASE": RobotAction.RELEASE,
            "BACKFLIP": RobotAction.BACKFLIP,
        }
        action = action_map.get(action_str, RobotAction.IDLE)
        self.sim.execute(action, selected.id)
        sm.state.current_action = action
        if action == RobotAction.BACKFLIP:
            asyncio.ensure_future(self._speak("Backflip!", "general", priority=0))

    def set_test_mode(self, enabled: bool):
        """Enable/disable test EEG mode. Requires ONNX model loaded."""
        if enabled and not self._brain_decoder:
            print("[ControlLoop] Cannot enable test mode — no ONNX model loaded")
            return
        self._test_mode = enabled
        if enabled:
            self._test_eeg_source = TestEEGSource()
            print("[ControlLoop] Test mode ON — synthetic EEG through real classifier")
        else:
            self._test_eeg_source = None
            print("[ControlLoop] Test mode OFF")

    def set_sim_brain(self, class_index: int | None):
        """Set simulated brain class (0-4) or None to disable.
        Bypasses EEG source + classifier entirely."""
        if class_index is not None and not (0 <= class_index < len(LABEL_NAMES)):
            print(f"[ControlLoop] Invalid sim brain class: {class_index}")
            return
        self._sim_brain_class = class_index
        if class_index is not None:
            print(f"[ControlLoop] Brain sim: {LABEL_NAMES[class_index]} (class {class_index})")
        else:
            print("[ControlLoop] Brain sim OFF")

    def start_nav(self, target_name: str, robot_id: str | None = None) -> dict:
        """Start autopilot navigation to a named waypoint."""
        if robot_id is None:
            robot_id = self.robot_manager.selected_robot.id

        result = Autopilot.resolve_target(target_name)
        if result is None:
            print(f"[ControlLoop] Unknown nav target: {target_name}")
            return {"ok": False, "error": f"Unknown landmark: {target_name}"}
        canonical_name, (tx, ty) = result
        # Get robot's current position for pathfinding
        robot_state = self.sim.get_state(robot_id)
        rpos = robot_state.get("position", [0, 0, 0])
        self._autopilots[robot_id] = Autopilot(canonical_name, (tx, ty), start_xy=(rpos[0], rpos[1]))

        # Set gear to forward for walking
        sm = self.robot_manager.state_machines.get(robot_id, self.robot_manager.selected_sm)
        sm.set_gear(Gear.FORWARD)
        print(f"[ControlLoop] {robot_id} navigating to {canonical_name} ({tx}, {ty})")
        return {"ok": True, "target": canonical_name, "x": tx, "y": ty}

    def cancel_nav(self, robot_id: str | None = None):
        """Cancel any active autopilot navigation and stop the robot."""
        if robot_id is None:
            robot_id = self.robot_manager.selected_robot.id
        ap = self._autopilots.get(robot_id)
        if ap and ap.active:
            ap.cancel()
            print(f"[ControlLoop] Navigation cancelled for {robot_id}")
        self._autopilots.pop(robot_id, None)
        # Stop the robot and clear toggled action
        self.sim.execute(RobotAction.IDLE, robot_id)
        sm = self.robot_manager.state_machines.get(robot_id)
        if sm:
            sm.state.toggled_action = None
            sm.state.toggled_class = None
            sm.state.current_action = RobotAction.IDLE

    def _cancel_active_tasks(self):
        """Cancel all active autopilots and stop all affected robots."""
        cancelled_ids = []
        for robot_id in list(self._autopilots.keys()):
            ap = self._autopilots[robot_id]
            if ap.active:
                ap.cancel()
                cancelled_ids.append(robot_id)
                print(f"[ControlLoop] Cancelled task for {robot_id}")
            self._autopilots.pop(robot_id, None)
        if cancelled_ids:
            asyncio.ensure_future(self._speak(
                f"Tasks cancelled for {', '.join(cancelled_ids)}", "nav_cancel", priority=0
            ))
        self._sequential_tasks.clear()
        # Stop robots and clear state
        for r in self.robot_manager.robots:
            r.task = None
        for robot_id in cancelled_ids:
            self.sim.execute(RobotAction.IDLE, robot_id)
            sm = self.robot_manager.state_machines.get(robot_id)
            if sm:
                sm.state.toggled_action = None
                sm.state.toggled_class = None
                sm.state.current_action = RobotAction.IDLE
        # Reset fusion state so no stale gesture re-triggers movement
        self.fusion.reset()

    async def _dispatch_orchestration_task(self, task: dict):
        """Dispatch an orchestration task to active robots."""
        task_action = task.get("action", "")

        # SELECT_ROBOT → update active robot IDs
        if task_action == "SELECT_ROBOT":
            selected_ids = task.get("selected_robot_ids", [])
            self.robot_manager.set_active_robots(selected_ids)
            names = ", ".join(selected_ids) if selected_ids else "none"
            print(f"[ControlLoop] Active robots: {names}")
            await self.broadcast({
                "type": "command_log",
                "source": "system",
                "action": f"ROBOTS: {names}",
                "timestamp": time.time(),
            })
            return

        # BACKFLIP → execute immediately on all active robots
        if task_action == "BACKFLIP":
            active_ids = list(self.robot_manager.active_robot_ids)
            for rid in active_ids:
                self.sim.execute(RobotAction.BACKFLIP, rid)
            await self.broadcast({
                "type": "command_log",
                "source": "system",
                "action": f"ORCH: BACKFLIP ({len(active_ids)} robots)",
                "timestamp": time.time(),
            })
            await self._speak("Backflip!", "general", priority=0)
            return

        # Navigation/logistics tasks → dispatch to all active robots
        landmark = task.get("landmark", "")
        active_ids = list(self.robot_manager.active_robot_ids)
        is_logistics = task_action in ("CARRY_TO", "STACK_TO")

        if is_logistics and len(active_ids) > 1:
            # Sequential execution: start first, queue rest
            first_id = active_ids[0]
            nav_result = self.start_nav(landmark, first_id)
            if nav_result.get("ok"):
                robot = next((r for r in self.robot_manager.robots if r.id == first_id), None)
                if robot:
                    robot.task = task
            # Queue remaining
            for rid in active_ids[1:]:
                self._sequential_tasks.append({
                    "robot_id": rid,
                    "landmark": landmark,
                    "task": task,
                })
            await self.broadcast({
                "type": "command_log",
                "source": "system",
                "action": f"ORCH: {task_action} → {landmark} ({len(active_ids)} robots, sequential)",
                "timestamp": time.time(),
            })
            await self._speak(
                f"Dispatching {task_action.replace('_', ' ').lower()} to {landmark}, {len(active_ids)} robots sequentially",
                "orch_dispatch", priority=1
            )
        else:
            # Simultaneous: start all at once
            for rid in active_ids:
                nav_result = self.start_nav(landmark, rid)
                if nav_result.get("ok"):
                    robot = next((r for r in self.robot_manager.robots if r.id == rid), None)
                    if robot:
                        robot.task = task
            await self.broadcast({
                "type": "command_log",
                "source": "system",
                "action": f"ORCH: {task_action} → {landmark} ({len(active_ids)} robots)",
                "timestamp": time.time(),
            })
            await self._speak(
                f"Dispatching {task_action.replace('_', ' ').lower()} to {landmark}, {len(active_ids)} robots",
                "orch_dispatch", priority=1
            )

    async def _advance_action_queue(self):
        """Execute the next step in the action queue."""
        if not self._action_queue:
            self._waiting_for_arrival = False
            self._action_queue_label = ""
            return

        step = self._action_queue[0]
        action_str = step["action"]
        target = step.get("target")
        step_num = self._action_queue_total - len(self._action_queue) + 1

        if action_str == "NAVIGATE" and target:
            result = self.start_nav(target)
            if result.get("ok"):
                self._waiting_for_arrival = True
                await self.broadcast({
                    "type": "command_log",
                    "source": "system",
                    "action": f"SEQ {step_num}/{self._action_queue_total}: NAV -> {result['target']}",
                    "timestamp": time.time(),
                })
            else:
                # Skip bad nav target, advance to next
                self._action_queue.pop(0)
                await self._advance_action_queue()
        elif action_str in ("GRAB", "RELEASE", "STOP"):
            # Execute immediately, then advance
            action_map = {
                "GRAB": RobotAction.GRAB,
                "RELEASE": RobotAction.RELEASE,
                "STOP": RobotAction.STOP,
            }
            robot_action = action_map.get(action_str, RobotAction.IDLE)
            selected = self.robot_manager.selected_robot
            self.sim.execute(robot_action, selected.id)
            self.robot_manager.selected_sm.state.current_action = robot_action
            await self.broadcast({
                "type": "command_log",
                "source": "system",
                "action": f"SEQ {step_num}/{self._action_queue_total}: {action_str}",
                "timestamp": time.time(),
            })
            self._action_queue.pop(0)
            # Small delay before next step so grab/release has time to take effect
            if self._action_queue:
                # Will be advanced on next tick check
                self._waiting_for_arrival = False
        else:
            # Unknown action, skip
            self._action_queue.pop(0)
            await self._advance_action_queue()

    def full_reset(self):
        """Reset all subsystems to initial state."""
        self.robot_manager.reset()
        self.fusion = CommandFusion(self.robot_manager.selected_sm)
        self.sim.reset()
        self._voice_queue.clear()
        self._action_queue.clear()
        self._action_queue_label = ""
        self._action_queue_total = 0
        self._waiting_for_arrival = False
        self._autopilots.clear()
        self._sequential_tasks.clear()
        self._cancel_confirm_pending = False
        if self.eeg_source:
            self.eeg_source.reset()
        if self._test_eeg_source:
            self._test_eeg_source.reset()
        if self._brain_decoder:
            self._brain_decoder.reset()
        self._sim_brain_class = None
        self.eeg_stream_enabled = True
        self.latencies.clear()
        self.tick_count = 0
        # Re-set robot IDs on all state machines
        robot_ids = [r.id for r in self.robot_manager.robots]
        for sm in self.robot_manager.state_machines.values():
            sm.set_robot_ids(robot_ids)
        print("[ControlLoop] Full reset complete")

    async def _speak(self, text: str, event_type: str = "general", priority: int = 1):
        """Synthesize TTS and broadcast to frontend.

        Runs ElevenLabs synthesis in a thread so the async loop isn't blocked.
        Falls back to browser speechSynthesis via the tts_request message.
        """
        try:
            feedback = await asyncio.to_thread(self.tts.speak, text, event_type, priority)
        except Exception:
            feedback = None

        if feedback is None:
            return

        msg = {
            "type": "tts_request",
            "text": feedback["text"],
            "event_type": feedback["event_type"],
            "timestamp": feedback["timestamp"],
        }
        if feedback.get("audio_base64"):
            msg["audio_base64"] = feedback["audio_base64"]
        await self.broadcast(msg)

    async def tick(self):
        """Single tick of the control loop."""
        tick_start = time.time()

        # Ensure fusion points to the currently selected robot's state machine
        selected = self.robot_manager.selected_robot
        selected_sm = self.robot_manager.selected_sm
        self.fusion.sm = selected_sm

        # 1. Get EEG prediction (or use brain simulator)
        eeg_window = None
        brain_result = None

        if not self.eeg_stream_enabled:
            # EEG stream disabled — no brain predictions, no waveform data
            pass
        elif self._sim_brain_class is not None and self.brain_enabled:
            # Brain simulator: bypass EEG + classifier, inject directly
            sim_cls = self._sim_brain_class
            brain_result = {
                "class": sim_cls,
                "label": LABEL_NAMES[sim_cls],
                "command": BRAIN_LABEL_TO_COMMAND.get(sim_cls, "STOP"),
                "confidence": 0.95,
                "probabilities": {LABEL_NAMES[i]: (0.95 if i == sim_cls else 0.01)
                                  for i in range(len(LABEL_NAMES))},
                "latency_ms": 0,
                "stable_command": BRAIN_LABEL_TO_COMMAND.get(sim_cls, "STOP"),
                "gated": False,
                "switched": False,
            }
            # Still get EEG window for waveform display
            source = self._test_eeg_source if self._test_mode else self.eeg_source
            eeg_window = source.get_latest_window() if source else None
        else:
            source = self._test_eeg_source if self._test_mode else self.eeg_source
            eeg_window = source.get_latest_window() if source else None

            if eeg_window is not None and self._brain_decoder:
                try:
                    brain_result = self._brain_decoder.predict(eeg_window)
                except Exception as e:
                    print(f"[ControlLoop] Brain decoder error: {e}")

            # Gate brain result if brain input is disabled
            if not self.brain_enabled:
                brain_result = None

        # 2. Get voice command (non-blocking)
        voice_command = None
        async with self._voice_lock:
            if not self.voice_enabled:
                self._voice_queue.clear()
            elif self._voice_queue:
                voice_command = self._voice_queue.pop(0)

        # 2b. Check if voice command starts/cancels navigation
        nav_started = False
        if voice_command:
            action_str = voice_command.get("action", "")
            if action_str == "NAVIGATE" and voice_command.get("command_type") == "automated":
                target = voice_command.get("target", "")
                result = self.start_nav(target)
                nav_started = result.get("ok", False)
                if nav_started:
                    await self.broadcast({
                        "type": "command_log",
                        "source": "voice",
                        "action": f"NAV → {result['target']}",
                        "text": voice_command.get("raw_text", ""),
                        "timestamp": time.time(),
                    })
                # Don't pass NAVIGATE to fusion — autopilot handles it
                voice_command = None
            elif action_str in ("CANCEL_NAV", "STOP", "EMERGENCY_STOP", "STOP_ALL"):
                # Cancel active navigation on stop commands
                ap = self._autopilots.get(selected.id)
                if ap and ap.active:
                    self.cancel_nav()
                    await self.broadcast({
                        "type": "command_log",
                        "source": "voice",
                        "action": "NAV CANCELLED",
                        "text": voice_command.get("raw_text", ""),
                        "timestamp": time.time(),
                    })
                # Clear any pending action queue
                if self._action_queue:
                    self._action_queue.clear()
                    self._waiting_for_arrival = False
                    self._action_queue_label = ""

        # 2c. Advance action queue for non-navigation steps (GRAB, RELEASE)
        if self._action_queue and not self._waiting_for_arrival:
            await self._advance_action_queue()

        # 3. Always run fusion (gesture recognition must process brain signals even during autopilot)
        fused = self.fusion.update(brain_result, voice_command)
        selected_autopilot = self._autopilots.get(selected.id)
        has_active_nav = any(ap.active for ap in self._autopilots.values())

        # Handle SELECT_SEQUENCE for robot selection (any time)
        if (fused["source"] == "brain_gesture" and
                fused.get("gesture_type") == "SELECT_SEQUENCE"):
            direction = fused.get("select_direction")
            if direction:
                self.robot_manager.select_by_direction(direction)
                self.fusion.sm = self.robot_manager.selected_sm

        # 3b. Cancel confirmation flow (double-clench Both Fists during active nav)
        is_double_clench_both = (
            fused["source"] == "brain_gesture" and
            fused.get("gesture_type") == "DOUBLE_CLENCH" and
            fused.get("brain_class") in ("Both Fists", "Both Firsts")
        )

        cancel_handled = False
        if is_double_clench_both and (has_active_nav or self._cancel_confirm_pending):
            cancel_handled = True
            if self._cancel_confirm_pending:
                # Second double-clench → confirm cancellation
                self._cancel_active_tasks()
                self._cancel_confirm_pending = False
                await self.broadcast({
                    "type": "cancel_confirmed",
                    "timestamp": time.time(),
                })
                await self.broadcast({
                    "type": "command_log",
                    "source": "system",
                    "action": "NAV CANCELLED (brain)",
                    "timestamp": time.time(),
                })
            else:
                # First double-clench → show confirmation prompt
                self._cancel_confirm_pending = True
                self._cancel_confirm_time = time.time()
                nav_descs = []
                for rid, ap in self._autopilots.items():
                    if ap.active:
                        nav_descs.append(f"NAV to {ap.target_name}")
                await self.broadcast({
                    "type": "cancel_confirm_prompt",
                    "description": "; ".join(nav_descs) if nav_descs else "active task",
                    "timestamp": time.time(),
                })

        # Auto-dismiss cancel confirmation after timeout
        if self._cancel_confirm_pending and (time.time() - self._cancel_confirm_time > CANCEL_CONFIRM_TIMEOUT_S):
            self._cancel_confirm_pending = False
            await self.broadcast({
                "type": "cancel_confirm_dismiss",
                "timestamp": time.time(),
            })

        # 3c. Determine action
        if selected_autopilot and selected_autopilot.active:
            # Autopilot controls the robot
            robot_state_now = self.sim.get_state(selected.id)
            pos = robot_state_now.get("position", [0, 0, 0])
            yaw = robot_state_now.get("orientation", 0)
            action = selected_autopilot.update((pos[0], pos[1]), yaw)
            action_source = "autopilot"

            if selected_autopilot.arrived:
                self._cancel_confirm_pending = False
                await self.broadcast({
                    "type": "command_log",
                    "source": "system",
                    "action": f"ARRIVED at {selected_autopilot.target_name}",
                    "timestamp": time.time(),
                })
                await self._speak(
                    f"{selected.id} arrived at {selected_autopilot.target_name}",
                    "nav_arrive", priority=1
                )
                # Advance the action queue if we were waiting for this arrival
                if self._waiting_for_arrival and self._action_queue:
                    self._action_queue.pop(0)  # remove completed NAVIGATE step
                    self._waiting_for_arrival = False
                    await self._advance_action_queue()
        else:
            # Normal: use fusion action
            action = fused["action"]
            action_source = fused["source"]

            # Handle orchestration cancel (only if not already handled by cancel confirm)
            if not cancel_handled and fused.get("orchestration_event") == "cancel":
                self._cancel_active_tasks()
                await self.broadcast({
                    "type": "command_log",
                    "source": "system",
                    "action": "ORCH CANCEL",
                    "timestamp": time.time(),
                })

            # Handle orchestration task dispatch
            if fused.get("orchestration_task"):
                await self._dispatch_orchestration_task(fused["orchestration_task"])

        # 4. Execute on selected robot
        robot_state = self.sim.execute(action, selected.id)

        # Sync holding state from simulation
        if "holding" in robot_state:
            selected_sm.state.holding_item = robot_state["holding"]

        # Sync robot manager state from sim
        self.robot_manager.update_robot_state(
            selected.id,
            robot_state.get("position", [0, 0, 0]),
            robot_state.get("orientation", 0),
        )

        # 5. Calculate latency
        latency_ms = (time.time() - tick_start) * 1000
        self.latencies.append(latency_ms)
        if len(self.latencies) > 100:
            self.latencies = self.latencies[-100:]

        # 6. Broadcast state to frontend
        await self.broadcast({
            "type": "state_update",
            "gear": selected_sm.state.gear.value,
            "action": action.value,
            "action_source": action_source,
            "brain_class": brain_result.get("label") if brain_result else None,
            "brain_confidence": brain_result.get("confidence", 0) if brain_result else 0,
            "brain_gated": brain_result.get("gated", True) if brain_result else True,
            "holding_item": selected_sm.state.holding_item,
            "robot_state": robot_state,
            "latency_ms": round(latency_ms, 1),
            "timestamp": time.time(),
            # New multi-robot / toggle / orchestration fields
            "toggled_action": selected_sm.state.toggled_action.value if selected_sm.state.toggled_action else None,
            "selected_robot": selected.id,
            "robots": self.robot_manager.get_all_states(),
            "orchestration": selected_sm.get_orchestration_state(),
            # Voice action queue progress
            "action_queue": {
                "active": bool(self._action_queue),
                "label": self._action_queue_label,
                "remaining": len(self._action_queue),
                "total": self._action_queue_total,
                "step": self._action_queue_total - len(self._action_queue),
            } if self._action_queue_total > 0 else None,
        })

        # 6b. Broadcast autopilot navigation status
        if selected_autopilot:
            await self.broadcast({
                "type": "nav_update",
                **selected_autopilot.get_status(),
            })
            if not selected_autopilot.active:
                self._autopilots.pop(selected.id, None)

        # 6c. Process sequential task queue (logistics tasks one-by-one)
        if self._sequential_tasks:
            # Check if the current sequential robot has finished
            next_task = self._sequential_tasks[0]
            next_rid = next_task["robot_id"]
            ap = self._autopilots.get(next_rid)
            if not ap or not ap.active:
                # Start next sequential task
                self._sequential_tasks.pop(0)
                nav_result = self.start_nav(next_task["landmark"], next_rid)
                if nav_result.get("ok"):
                    robot = next((r for r in self.robot_manager.robots if r.id == next_rid), None)
                    if robot:
                        robot.task = next_task.get("task")
                    await self.broadcast({
                        "type": "command_log",
                        "source": "system",
                        "action": f"SEQ: {next_rid} → {next_task['landmark']}",
                        "timestamp": time.time(),
                    })

        # 7. Broadcast EEG visualization data (every 10th tick = 1Hz)
        if self.tick_count % 10 == 0 and eeg_window is not None:
            try:
                decimated = eeg_window[::10].T.tolist()
                await self.broadcast({
                    "type": "eeg_data",
                    "channels": decimated,
                    "sample_rate": 50,
                })
            except Exception:
                pass

        # 8. Log to command log (only for fusion events, not autopilot)
        if action_source in ("brain_gesture", "brain_toggle", "voice"):
            log_entry = {
                "type": "command_log",
                "source": "brain" if action_source.startswith("brain") else action_source,
                "action": action.value,
                "timestamp": time.time(),
            }
            if action_source.startswith("brain") and brain_result:
                log_entry["brain_class"] = brain_result.get("class")
                log_entry["confidence"] = brain_result.get("confidence", 0)
            if action_source == "voice" and voice_command:
                log_entry["text"] = voice_command.get("raw_text", "")
            await self.broadcast(log_entry)

        self.tick_count += 1

    async def run(self):
        """Main loop — runs at ~10Hz."""
        await self.start()
        while self.running:
            try:
                await self.tick()
            except Exception as e:
                print(f"[ControlLoop] Tick error: {e}")
            await asyncio.sleep(TICK_INTERVAL)

    def get_metrics(self) -> dict:
        """Return current performance metrics."""
        avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0
        return {
            "avg_latency_ms": round(avg_latency, 1),
            "tick_count": self.tick_count,
            "loop_rate_hz": 10,
            "sim_running": self.sim.is_running(),
        }
