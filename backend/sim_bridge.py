"""
Simulation Bridge — wraps Mourad's SimulationBridge for the control loop.

Supports multi-robot: primary robot uses real SimulationBridge,
secondary robots use dead-reckoning position updates.
"""

import json
import math
import sys
from pathlib import Path
from .state_machine import RobotAction

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Add bri source to path so simulation/bridge.py can find `from bri import ...`
BRI_SRC = PROJECT_ROOT.parent / "brain-robot-interface" / "src"
BRI_BUNDLE_DIR = PROJECT_ROOT.parent / "brain-robot-interface" / "bundles" / "g1_mjlab"
if str(BRI_SRC) not in sys.path:
    sys.path.insert(0, str(BRI_SRC))

try:
    from simulation.bridge import SimulationBridge
    SIM_AVAILABLE = True
except ImportError as e:
    SIM_AVAILABLE = False
    print(f"[SimBridge] WARNING: Cannot import SimulationBridge: {e}")
    print("[SimBridge] Running in stub mode (no actual simulation)")

# Map our gear-aware RobotAction -> bri action names
ACTION_TO_BRI_NAME = {
    RobotAction.MOVE_FORWARD: "FORWARD",
    RobotAction.MOVE_BACKWARD: "BACKWARD",    # was STOP, now has real backward
    RobotAction.ROTATE_LEFT: "LEFT",
    RobotAction.ROTATE_RIGHT: "RIGHT",
    RobotAction.STOP: "STOP",
    RobotAction.EMERGENCY_STOP: "STOP",
    RobotAction.GRAB: "GRAB",                 # direct grab (voice/manual)
    RobotAction.RELEASE: "RELEASE",            # direct release (voice/manual)
    RobotAction.HOLD: "HOLD",                 # toggle hold: grab once, sustain
    RobotAction.IDLE: "STOP",
    RobotAction.BACKFLIP: "BACKFLIP",          # new
}

_CONFIG_PATH = PROJECT_ROOT / "robot_config.json"

def _load_map_boundaries():
    """Load map boundaries from robot_config.json, fall back to defaults."""
    defaults = {"min_x": -7.5, "max_x": 7.5, "min_y": -5.5, "max_y": 7.5}
    try:
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)
        return cfg.get("map_boundaries", defaults)
    except (FileNotFoundError, json.JSONDecodeError):
        return defaults

_MAP_BOUNDS = _load_map_boundaries()

# Dead-reckoning constants (per tick at 10Hz)
_DR_MOVE_SPEED = 0.06   # meters per tick
_DR_TURN_SPEED = 0.06   # radians per tick
_DR_FLOOR_LIMIT = 7.5  # keep for backward compat


class SimBridge:
    """Adapter that wraps SimulationBridge for the gear-based control loop.

    Multi-robot interface: attempts to connect each configured robot to its own
    SimulationBridge instance.  Robots that fail to connect fall back to
    dead-reckoning.  The ``_bridges`` dict is keyed by robot_id so future
    backends (headless sim, hardware drivers, remote ROS nodes) can be
    plugged in per-robot without changing the routing logic.
    """

    def __init__(self):
        self._bridges: dict[str, "SimulationBridge"] = {}  # robot_id -> SimulationBridge
        self.running = False
        self.last_action = RobotAction.IDLE
        self._holding = {}  # robot_id -> bool
        self._robot_states = self._load_robot_states()

    def _load_robot_states(self) -> dict:
        """Load initial robot states from config file."""
        try:
            with open(_CONFIG_PATH) as f:
                cfg = json.load(f)
            robots = cfg.get("robots", [])
            if not robots:
                raise ValueError("No robots in config")
            states = {}
            for r in robots:
                states[r["id"]] = {
                    "position": [r.get("x", 0), r.get("y", 0), 0],
                    "orientation": r.get("orientation", 0),
                    "status": "idle",
                }
            return states
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            return {
                "robot_0": {"position": [0, 0, 0], "orientation": 0, "status": "idle"},
            }

    @property
    def bridge(self):
        """Primary bridge (robot_0) for backward compatibility."""
        return self._bridges.get("robot_0")

    def start(self):
        """Initialize simulation bridges for all configured robots.

        Each robot in robot_config.json gets an initialization attempt.
        Successful connections are stored in ``_bridges``; failures are
        logged with actionable diagnostics and those robots fall back to
        dead-reckoning.
        """
        if not SIM_AVAILABLE:
            print("[SimBridge] Stub mode — SimulationBridge not importable")
            for rid in self._robot_states:
                print(f"  [{rid}] SKIP  — simulation library unavailable, using dead-reckoning")
            self.running = True
            return

        robot_ids = list(self._robot_states.keys())
        print(f"[SimBridge] Initializing simulation for {len(robot_ids)} robot(s)...")

        for rid in robot_ids:
            try:
                bridge = SimulationBridge(
                    decoder=None,
                    robot="g1",
                    bundle_dir=str(BRI_BUNDLE_DIR),
                    scene="factory",
                )
                bridge.start()
                self._bridges[rid] = bridge
                print(f"  [{rid}] OK    — MuJoCo simulation connected")
            except Exception as e:
                print(f"  [{rid}] FAIL  — could not connect to simulation backend: {e}")
                print(f"           Possible causes: unable to connect to robot, "
                      f"viewer already running, missing model assets")
                print(f"           Falling back to dead-reckoning for {rid}")
                # Only the first successful bridge should keep a viewer;
                # break after the first so we don't try to open duplicate viewers.
                # Future: add headless sim support to allow parallel instances.
                if self._bridges:
                    break

            # After the first successful bridge, remaining robots cannot open
            # another MuJoCo viewer in the same process — stop trying.
            if self._bridges:
                remaining = [r for r in robot_ids if r != rid and r not in self._bridges]
                for other_id in remaining:
                    print(f"  [{other_id}] SKIP  — single-viewer limitation, "
                          f"using dead-reckoning (future: headless sim backend)")
                break

        if self._bridges:
            connected = ", ".join(self._bridges.keys())
            dr_ids = [r for r in robot_ids if r not in self._bridges]
            dr_list = ", ".join(dr_ids) if dr_ids else "none"
            print(f"[SimBridge] Sim connected: [{connected}]  |  Dead-reckoning: [{dr_list}]")
        else:
            print("[SimBridge] No simulation bridges connected — all robots using dead-reckoning")

        self.running = True

    def reset(self):
        self.last_action = RobotAction.IDLE
        self._holding = {}
        for rid, bridge in self._bridges.items():
            try:
                bridge.reset_position()
            except Exception as e:
                print(f"[SimBridge] Failed to reset sim position for {rid}: {e}")
        self._robot_states = self._load_robot_states()

    def execute(self, action: RobotAction, robot_id: str = "robot_0") -> dict:
        """Send action to simulation/dead-reckoning for a specific robot, return robot state."""
        self.last_action = action
        bri_name = ACTION_TO_BRI_NAME.get(action, "STOP")

        robot_bridge = self._bridges.get(robot_id)
        if robot_bridge:
            # Robot has a live simulation bridge
            try:
                if action == RobotAction.HOLD:
                    if not self._holding.get(robot_id, False):
                        result = robot_bridge.grab_nearest()
                        if result:
                            self._holding[robot_id] = True
                elif action == RobotAction.GRAB:
                    result = robot_bridge.grab_nearest()
                    if result:
                        self._holding[robot_id] = True
                elif action == RobotAction.RELEASE:
                    result = robot_bridge.release()
                    if result:
                        self._holding[robot_id] = False
                elif action == RobotAction.BACKFLIP:
                    robot_bridge.send_backflip()
                elif action == RobotAction.MOVE_BACKWARD:
                    robot_bridge.send_action("BACKWARD")
                else:
                    robot_bridge.send_action(bri_name)
            except Exception as e:
                print(f"[SimBridge] Error sending action to {robot_id}: {e}")

            # Update held object position every tick (position-lock)
            try:
                robot_bridge.update_held_position()
            except Exception:
                pass

            # Check for fall recovery
            try:
                if robot_bridge.check_and_recover():
                    print(f"[SimBridge] {robot_id} fell — auto-recovery triggered")
            except Exception:
                pass

            try:
                robot_xy, yaw = robot_bridge.get_robot_state()
                self._robot_states[robot_id]["position"] = [float(robot_xy[0]), float(robot_xy[1]), 0]
                self._robot_states[robot_id]["orientation"] = float(yaw)
            except Exception:
                pass
        else:
            # No sim bridge — dead-reckoning fallback
            self._dead_reckon(robot_id, action)

        state = self._robot_states.get(robot_id, self._robot_states["robot_0"])
        state["status"] = action.value.lower()
        state["holding"] = self._holding.get(robot_id, False)
        return state

    def _dead_reckon(self, robot_id: str, action: RobotAction):
        """Update robot position using simple dead-reckoning."""
        state = self._robot_states.get(robot_id)
        if not state:
            return

        pos = state["position"]
        yaw = state["orientation"]

        if action == RobotAction.MOVE_FORWARD:
            pos[0] += math.cos(yaw) * _DR_MOVE_SPEED
            pos[1] += math.sin(yaw) * _DR_MOVE_SPEED
        elif action == RobotAction.MOVE_BACKWARD:
            pos[0] -= math.cos(yaw) * _DR_MOVE_SPEED
            pos[1] -= math.sin(yaw) * _DR_MOVE_SPEED
        elif action == RobotAction.ROTATE_LEFT:
            yaw += _DR_TURN_SPEED
        elif action == RobotAction.ROTATE_RIGHT:
            yaw -= _DR_TURN_SPEED
        elif action == RobotAction.HOLD:
            # HOLD toggle: grab once, sustain while active
            if not self._holding.get(robot_id, False):
                self._holding[robot_id] = True
        elif action == RobotAction.GRAB:
            self._holding[robot_id] = True
        elif action == RobotAction.RELEASE:
            self._holding[robot_id] = False

        # Clamp to map boundaries
        pos[0] = max(_MAP_BOUNDS["min_x"], min(_MAP_BOUNDS["max_x"], pos[0]))
        pos[1] = max(_MAP_BOUNDS["min_y"], min(_MAP_BOUNDS["max_y"], pos[1]))

        state["position"] = pos
        state["orientation"] = yaw

    def stop(self):
        """Stop all simulation bridges."""
        for rid, bridge in self._bridges.items():
            try:
                bridge.stop()
            except Exception:
                pass
        self._bridges.clear()
        self.running = False

    def get_state(self, robot_id: str = "robot_0") -> dict:
        robot_bridge = self._bridges.get(robot_id)
        if robot_bridge:
            try:
                robot_xy, yaw = robot_bridge.get_robot_state()
                self._robot_states[robot_id]["position"] = [float(robot_xy[0]), float(robot_xy[1]), 0]
                self._robot_states[robot_id]["orientation"] = float(yaw)
            except Exception:
                pass
        return self._robot_states.get(robot_id, self._robot_states.get("robot_0", {}))

    def get_all_states(self) -> dict[str, dict]:
        """Return states for all robots."""
        # Sync all sim-connected robots
        for rid in self._bridges:
            self.get_state(rid)
        return dict(self._robot_states)

    def is_running(self) -> bool:
        if self._bridges:
            return any(b.is_running() for b in self._bridges.values())
        return self.running

    def get_action_log(self) -> list[dict]:
        """Get the action log from the primary bridge."""
        primary = self._bridges.get("robot_0")
        if primary:
            return primary.get_action_log()
        return []
