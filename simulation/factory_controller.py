"""
ThoughtLink Factory Controller
All factory-robot features: waypoint nav, patrol, pick & place, push,
obstacle safety, HUD overlay, status light, trail, task sequencer, geofencing, e-stop.
"""

from __future__ import annotations

import math
import sys
import time
import threading
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from constants import (
    FACTORY_WAYPOINTS,
    FACTORY_WAYPOINT_ORDER,
    FACTORY_PATROL_ROUTE,
    FACTORY_GRABBABLE_BOXES,
    FACTORY_PUSHABLE_BOXES,
    FACTORY_OBSTACLE_GEOMS,
    FACTORY_GEOFENCE_ZONES,
    OBSTACLE_WARNING_DIST,
    OBSTACLE_DANGER_DIST,
    GRAB_REACH_DIST,
    WAYPOINT_ARRIVAL_DIST,
    WAYPOINT_ALIGN_THRESHOLD,
    ESTOP_HOLD_SECONDS,
    TRAIL_MIN_DISTANCE,
    NUM_TRAIL_DOTS,
    STATUS_COLORS,
)


# ---------------------------------------------------------------------------
# MuJoCoAccess — safe wrapper around model / data / viewer
# ---------------------------------------------------------------------------
class MuJoCoAccess:
    """Cached name→id lookups + convenience helpers for MuJoCo objects."""

    def __init__(self, model, data, viewer):
        import mujoco
        self._mj = mujoco
        self.model = model
        self.data = data
        self.viewer = viewer
        self._geom_ids: dict[str, int] = {}
        self._body_ids: dict[str, int] = {}
        self._site_ids: dict[str, int] = {}

    # -- id caches --
    def geom_id(self, name: str) -> int:
        if name not in self._geom_ids:
            gid = self._mj.mj_name2id(self.model, self._mj.mjtObj.mjOBJ_GEOM, name)
            if gid < 0:
                raise KeyError(f"geom '{name}' not found in MuJoCo model")
            self._geom_ids[name] = gid
        return self._geom_ids[name]

    def body_id(self, name: str) -> int:
        if name not in self._body_ids:
            bid = self._mj.mj_name2id(self.model, self._mj.mjtObj.mjOBJ_BODY, name)
            if bid < 0:
                raise KeyError(f"body '{name}' not found in MuJoCo model")
            self._body_ids[name] = bid
        return self._body_ids[name]

    def site_id(self, name: str) -> int:
        if name not in self._site_ids:
            sid = self._mj.mj_name2id(self.model, self._mj.mjtObj.mjOBJ_SITE, name)
            if sid < 0:
                raise KeyError(f"site '{name}' not found in MuJoCo model")
            self._site_ids[name] = sid
        return self._site_ids[name]

    # -- helpers --
    def get_body_pos(self, name: str) -> np.ndarray:
        return self.data.xpos[self.body_id(name)].copy()

    def get_body_quat(self, name: str) -> np.ndarray:
        return self.data.xquat[self.body_id(name)].copy()

    def get_site_pos(self, name: str) -> np.ndarray:
        return self.data.site_xpos[self.site_id(name)].copy()

    def get_geom_pos(self, name: str) -> np.ndarray:
        return self.model.geom_pos[self.geom_id(name)].copy()

    def set_geom_pos(self, name: str, pos) -> None:
        self.model.geom_pos[self.geom_id(name)] = pos

    def set_geom_rgba(self, name: str, rgba) -> None:
        self.model.geom_rgba[self.geom_id(name)] = rgba

    def get_geom_rgba(self, name: str) -> np.ndarray:
        return self.model.geom_rgba[self.geom_id(name)].copy()

    def set_texts(self, texts: list) -> None:
        """Set viewer overlay texts. Each entry: (font, gridpos, text1, text2)."""
        if self.viewer is not None:
            try:
                self.viewer.set_texts(texts)
            except Exception:
                pass

    def get_robot_xy(self) -> np.ndarray:
        pos = self.get_body_pos("pelvis")
        return np.array([pos[0], pos[1]])

    def get_robot_yaw(self) -> float:
        q = self.get_body_quat("pelvis")
        w, x, y, z = q[0], q[1], q[2], q[3]
        siny = 2.0 * (w * z + x * y)
        cosy = 1.0 - 2.0 * (y * y + z * z)
        return float(np.arctan2(siny, cosy))


# ---------------------------------------------------------------------------
# Helper: angle diff in [-pi, pi]
# ---------------------------------------------------------------------------
def _angle_diff(a: float, b: float) -> float:
    d = a - b
    while d > math.pi:
        d -= 2 * math.pi
    while d < -math.pi:
        d += 2 * math.pi
    return d


# ---------------------------------------------------------------------------
# WaypointNavigator
# ---------------------------------------------------------------------------
class WaypointNavigator:
    """Cycle through waypoints, auto-steer toward the selected target."""

    def __init__(self):
        self._names = list(FACTORY_WAYPOINT_ORDER)
        self._coords = {n: FACTORY_WAYPOINTS[n] for n in self._names}
        self._index = 0
        self._target: str | None = None  # currently navigating to

    @property
    def selected_name(self) -> str:
        return self._names[self._index]

    @property
    def selected_coord(self) -> tuple[float, float]:
        return self._coords[self.selected_name]

    @property
    def target_name(self) -> str | None:
        return self._target

    @property
    def is_navigating(self) -> bool:
        return self._target is not None

    def select_index(self, idx: int) -> None:
        self._index = idx % len(self._names)

    def cycle_next(self) -> str:
        self._index = (self._index + 1) % len(self._names)
        return self.selected_name

    def cycle_prev(self) -> str:
        self._index = (self._index - 1) % len(self._names)
        return self.selected_name

    def start_navigation(self, name: str | None = None) -> None:
        self._target = name or self.selected_name

    def cancel_navigation(self) -> None:
        self._target = None

    def compute_steering(self, robot_xy: np.ndarray, robot_yaw: float) -> str:
        """Return FORWARD / LEFT / RIGHT / STOP based on target."""
        if self._target is None:
            return "STOP"
        tx, ty = self._coords[self._target]
        dx = tx - robot_xy[0]
        dy = ty - robot_xy[1]
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < WAYPOINT_ARRIVAL_DIST:
            self._target = None
            return "STOP"
        desired_yaw = math.atan2(dy, dx)
        diff = _angle_diff(desired_yaw, robot_yaw)
        if abs(diff) > WAYPOINT_ALIGN_THRESHOLD:
            return "LEFT" if diff > 0 else "RIGHT"
        return "FORWARD"

    def distance_to_target(self, robot_xy: np.ndarray) -> float | None:
        if self._target is None:
            return None
        tx, ty = self._coords[self._target]
        return float(np.linalg.norm(robot_xy - np.array([tx, ty])))


# ---------------------------------------------------------------------------
# PatrolManager
# ---------------------------------------------------------------------------
class PatrolManager:
    """Sequentially follow a route using WaypointNavigator."""

    def __init__(self, navigator: WaypointNavigator):
        self._nav = navigator
        self._route = list(FACTORY_PATROL_ROUTE)
        self._route_idx = 0
        self._active = False
        self._paused = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def current_stop(self) -> str | None:
        if not self._active:
            return None
        return self._route[self._route_idx]

    def start(self) -> None:
        self._active = True
        self._paused = False
        self._route_idx = 0
        self._nav.start_navigation(self._route[0])

    def stop(self) -> None:
        self._active = False
        self._paused = False
        self._nav.cancel_navigation()

    def toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self._nav.cancel_navigation()
        else:
            self._nav.start_navigation(self._route[self._route_idx])

    def skip(self) -> None:
        self._advance()

    def on_arrival(self) -> None:
        """Called when the navigator reports arrival at the current target."""
        if self._active and not self._paused:
            self._advance()

    def _advance(self) -> None:
        self._route_idx = (self._route_idx + 1) % len(self._route)
        self._nav.start_navigation(self._route[self._route_idx])


# ---------------------------------------------------------------------------
# PickPlaceManager
# ---------------------------------------------------------------------------
class PickPlaceManager:
    """Grab / release boxes by moving geom_pos to track hand site."""

    def __init__(self, mj: MuJoCoAccess):
        self._mj = mj
        self._held_geom: str | None = None
        self._original_rgba: np.ndarray | None = None

    @property
    def is_holding(self) -> bool:
        return self._held_geom is not None

    @property
    def held_name(self) -> str | None:
        return self._held_geom

    def grab(self, robot_xy: np.ndarray) -> str | None:
        """Grab nearest box within reach. Returns box name or None."""
        if self._held_geom is not None:
            return self._held_geom
        best_name = None
        best_dist = GRAB_REACH_DIST
        for name in FACTORY_GRABBABLE_BOXES:
            try:
                gpos = self._mj.get_geom_pos(name)
                d = float(np.linalg.norm(robot_xy - np.array([gpos[0], gpos[1]])))
                if d < best_dist:
                    best_dist = d
                    best_name = name
            except KeyError:
                continue
        if best_name is None:
            return None
        self._held_geom = best_name
        self._original_rgba = self._mj.get_geom_rgba(best_name)
        self._mj.set_geom_rgba(best_name, STATUS_COLORS["GRAB"])
        return best_name

    def release(self) -> None:
        if self._held_geom is not None and self._original_rgba is not None:
            self._mj.set_geom_rgba(self._held_geom, self._original_rgba)
        self._held_geom = None
        self._original_rgba = None

    def update_held_position(self) -> None:
        """Move held box to right_palm site position."""
        if self._held_geom is None:
            return
        try:
            palm_pos = self._mj.get_site_pos("right_palm")
            self._mj.set_geom_pos(self._held_geom, palm_pos)
        except KeyError:
            pass

    def nearest_box_info(self, robot_xy: np.ndarray) -> tuple[str | None, float]:
        """Return (name, distance) of nearest grabbable box."""
        best_name = None
        best_dist = 999.0
        for name in FACTORY_GRABBABLE_BOXES:
            try:
                gpos = self._mj.get_geom_pos(name)
                d = float(np.linalg.norm(robot_xy - np.array([gpos[0], gpos[1]])))
                if d < best_dist:
                    best_dist = d
                    best_name = name
            except KeyError:
                continue
        return best_name, best_dist


# ---------------------------------------------------------------------------
# PushManager
# ---------------------------------------------------------------------------
class PushManager:
    """Push boxes when the robot collides with them."""

    PUSH_RADIUS = 0.5
    PUSH_INCREMENT = 0.02

    def __init__(self, mj: MuJoCoAccess):
        self._mj = mj

    def update(self, robot_xy: np.ndarray, robot_yaw: float) -> None:
        dx = math.cos(robot_yaw) * self.PUSH_INCREMENT
        dy = math.sin(robot_yaw) * self.PUSH_INCREMENT
        for name in FACTORY_PUSHABLE_BOXES:
            try:
                gpos = self._mj.get_geom_pos(name)
                bxy = np.array([gpos[0], gpos[1]])
                if float(np.linalg.norm(robot_xy - bxy)) < self.PUSH_RADIUS:
                    gpos[0] += dx
                    gpos[1] += dy
                    self._mj.set_geom_pos(name, gpos)
            except KeyError:
                continue


# ---------------------------------------------------------------------------
# ObstacleSafety
# ---------------------------------------------------------------------------
class ObstacleSafety:
    """Proximity alerts, geofencing, emergency stop."""

    def __init__(self, mj: MuJoCoAccess):
        self._mj = mj
        self._estop_active = False
        self._estop_start: float | None = None  # when Both Fists started

    @property
    def estop_active(self) -> bool:
        return self._estop_active

    def toggle_estop(self) -> None:
        self._estop_active = not self._estop_active
        self._estop_start = None

    def reset_estop(self) -> None:
        self._estop_active = False
        self._estop_start = None

    def update_estop_hold(self, both_fists: bool) -> None:
        """Track Both Fists duration for auto e-stop."""
        if both_fists:
            if self._estop_start is None:
                self._estop_start = time.time()
            elif time.time() - self._estop_start >= ESTOP_HOLD_SECONDS:
                self._estop_active = True
        else:
            self._estop_start = None

    @property
    def estop_countdown(self) -> float | None:
        if self._estop_start is None:
            return None
        elapsed = time.time() - self._estop_start
        remaining = ESTOP_HOLD_SECONDS - elapsed
        return max(0.0, remaining)

    def check_obstacles(self, robot_xy: np.ndarray) -> tuple[str | None, float, bool, bool]:
        """Return (nearest_name, nearest_dist, warning, danger)."""
        nearest_name = None
        nearest_dist = 999.0
        for name in FACTORY_OBSTACLE_GEOMS:
            try:
                gpos = self._mj.get_geom_pos(name)
                d = float(np.linalg.norm(robot_xy - np.array([gpos[0], gpos[1]])))
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_name = name
            except KeyError:
                continue
        warning = nearest_dist < OBSTACLE_WARNING_DIST
        danger = nearest_dist < OBSTACLE_DANGER_DIST
        return nearest_name, nearest_dist, warning, danger

    def check_geofence(self, robot_xy: np.ndarray) -> str | None:
        """Return zone name if robot is inside a geofence, else None."""
        x, y = robot_xy
        for zone_name, (x0, x1, y0, y1) in FACTORY_GEOFENCE_ZONES.items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return zone_name
        return None

    def should_override_stop(self, robot_xy: np.ndarray, both_fists: bool) -> tuple[bool, str]:
        """Return (should_stop, reason)."""
        if self._estop_active:
            return True, "E-STOP ACTIVE"
        self.update_estop_hold(both_fists)
        _, _, _, danger = self.check_obstacles(robot_xy)
        if danger:
            return True, "OBSTACLE TOO CLOSE"
        zone = self.check_geofence(robot_xy)
        if zone is not None:
            return True, f"GEOFENCE: {zone}"
        return False, ""


# ---------------------------------------------------------------------------
# HUDOverlay
# ---------------------------------------------------------------------------
class HUDOverlay:
    """Four-corner text overlay on the MuJoCo viewer."""

    # mujoco font/grid constants (mjtFont, mjtGridPos)
    FONT_NORMAL = 0   # mjFONT_NORMAL
    FONT_BIG = 2      # mjFONT_BIG
    GRID_TOPLEFT = 0
    GRID_TOPRIGHT = 1
    GRID_BOTTOMLEFT = 2
    GRID_BOTTOMRIGHT = 3

    def __init__(self, mj: MuJoCoAccess):
        self._mj = mj
        self._texts: dict[int, tuple[str, str]] = {
            self.GRID_TOPLEFT: ("", ""),
            self.GRID_TOPRIGHT: ("", ""),
            self.GRID_BOTTOMLEFT: ("", ""),
            self.GRID_BOTTOMRIGHT: ("", ""),
        }

    def set_top_left(self, label: str, value: str) -> None:
        self._texts[self.GRID_TOPLEFT] = (label, value)

    def set_top_right(self, label: str, value: str) -> None:
        self._texts[self.GRID_TOPRIGHT] = (label, value)

    def set_bottom_left(self, label: str, value: str) -> None:
        self._texts[self.GRID_BOTTOMLEFT] = (label, value)

    def set_bottom_right(self, label: str, value: str) -> None:
        self._texts[self.GRID_BOTTOMRIGHT] = (label, value)

    def flush(self) -> None:
        """Push all text entries to the viewer."""
        entries = []
        for gridpos, (t1, t2) in self._texts.items():
            if t1 or t2:
                entries.append((self.FONT_NORMAL, gridpos, t1, t2))
        self._mj.set_texts(entries)


# ---------------------------------------------------------------------------
# StatusLight
# ---------------------------------------------------------------------------
class StatusLight:
    """Color-coded sphere floating above the robot."""

    def __init__(self, mj: MuJoCoAccess):
        self._mj = mj

    def update(self, robot_pos_3d: np.ndarray, action: str) -> None:
        light_pos = robot_pos_3d.copy()
        light_pos[2] = robot_pos_3d[2] + 1.5
        try:
            self._mj.set_geom_pos("status_light", light_pos)
            rgba = STATUS_COLORS.get(action, STATUS_COLORS["STOP"])
            self._mj.set_geom_rgba("status_light", rgba)
        except KeyError:
            pass


# ---------------------------------------------------------------------------
# TrailVisualizer
# ---------------------------------------------------------------------------
class TrailVisualizer:
    """Circular buffer of floor dots marking the robot's path."""

    def __init__(self, mj: MuJoCoAccess):
        self._mj = mj
        self._count = NUM_TRAIL_DOTS
        self._index = 0
        self._last_pos: np.ndarray | None = None

    def update(self, robot_xy: np.ndarray) -> None:
        if self._last_pos is not None:
            dist = float(np.linalg.norm(robot_xy - self._last_pos))
            if dist < TRAIL_MIN_DISTANCE:
                return
        self._last_pos = robot_xy.copy()
        name = f"trail_{self._index}"
        try:
            self._mj.set_geom_pos(name, [robot_xy[0], robot_xy[1], 0.002])
        except KeyError:
            pass
        self._index = (self._index + 1) % self._count


# ---------------------------------------------------------------------------
# TaskSequencer
# ---------------------------------------------------------------------------
class TaskSequencer:
    """Macro task templates: sequences of navigate / grab / release steps."""

    MACROS = {
        "Fetch to Pallet 2": [
            ("navigate", "Conveyor"),
            ("grab", None),
            ("navigate", "Pallet 2"),
            ("release", None),
        ],
        "Shelf A to Table": [
            ("navigate", "Pallet 1"),
            ("grab", None),
            ("navigate", "Table"),
            ("release", None),
        ],
    }

    def __init__(self, navigator: WaypointNavigator, picker: PickPlaceManager):
        self._nav = navigator
        self._picker = picker
        self._steps: list[tuple[str, str | None]] = []
        self._step_idx = 0
        self._active = False
        self._waiting_confirm = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def current_step(self) -> tuple[str, str | None] | None:
        if not self._active or self._step_idx >= len(self._steps):
            return None
        return self._steps[self._step_idx]

    @property
    def progress(self) -> str:
        if not self._active:
            return ""
        return f"{self._step_idx + 1}/{len(self._steps)}"

    @property
    def waiting_confirm(self) -> bool:
        return self._waiting_confirm

    def start_macro(self, name: str) -> bool:
        if name not in self.MACROS:
            return False
        self._steps = list(self.MACROS[name])
        self._step_idx = 0
        self._active = True
        self._waiting_confirm = False
        self._begin_step()
        return True

    def abort(self) -> None:
        self._active = False
        self._steps = []
        self._step_idx = 0
        self._nav.cancel_navigation()

    def confirm_step(self) -> None:
        """User confirms current step is done (e.g. manual grab)."""
        if self._waiting_confirm:
            self._waiting_confirm = False
            self._step_idx += 1
            if self._step_idx >= len(self._steps):
                self._active = False
            else:
                self._begin_step()

    def update(self, robot_xy: np.ndarray) -> None:
        """Check if current step is complete, auto-advance."""
        if not self._active or self._waiting_confirm:
            return
        step = self.current_step
        if step is None:
            self._active = False
            return
        action, param = step
        if action == "navigate":
            if not self._nav.is_navigating:
                # arrived
                self._step_idx += 1
                if self._step_idx >= len(self._steps):
                    self._active = False
                else:
                    self._begin_step()
        elif action == "grab":
            self._picker.grab(robot_xy)
            if self._picker.is_holding:
                self._step_idx += 1
                if self._step_idx >= len(self._steps):
                    self._active = False
                else:
                    self._begin_step()
            else:
                self._waiting_confirm = True
        elif action == "release":
            self._picker.release()
            self._step_idx += 1
            if self._step_idx >= len(self._steps):
                self._active = False
            else:
                self._begin_step()

    def _begin_step(self) -> None:
        if self._step_idx >= len(self._steps):
            self._active = False
            return
        action, param = self._steps[self._step_idx]
        if action == "navigate" and param:
            self._nav.start_navigation(param)


# ---------------------------------------------------------------------------
# FactoryController — main orchestrator
# ---------------------------------------------------------------------------
class FactoryController:
    """
    Main factory controller. Runs update loop at 20Hz.
    Modes: MANUAL, WAYPOINT, PATROL, PICK_PLACE, MACRO
    """

    MODES = ["MANUAL", "WAYPOINT", "PATROL", "PICK_PLACE", "MACRO"]

    def __init__(self, bridge):
        self._bridge = bridge
        model, data, viewer = bridge.get_mujoco_access()
        self._mj = MuJoCoAccess(model, data, viewer)

        # Sub-systems
        self._navigator = WaypointNavigator()
        self._patrol = PatrolManager(self._navigator)
        self._picker = PickPlaceManager(self._mj)
        self._pusher = PushManager(self._mj)
        self._safety = ObstacleSafety(self._mj)
        self._hud = HUDOverlay(self._mj)
        self._status_light = StatusLight(self._mj)
        self._trail = TrailVisualizer(self._mj)
        self._sequencer = TaskSequencer(self._navigator, self._picker)

        self._mode = "MANUAL"
        self._current_action = "STOP"
        self._last_brain_label = "Relax"
        self._last_confidence = 0.0
        self._last_latency_ms = 0.0
        self._safety_reason = ""

        self._running = False
        self._thread: threading.Thread | None = None

        # Highlight selected waypoint marker
        self._last_highlighted_wp: int | None = None

    # -- mode switching --
    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        if mode not in self.MODES:
            return
        # Clean up previous mode
        if self._mode == "PATROL":
            self._patrol.stop()
        if self._mode == "MACRO":
            self._sequencer.abort()
        self._mode = mode

    # -- brain signal input --
    def process_brain_signal(self, label: str, confidence: float, latency_ms: float = 0.0) -> None:
        self._last_brain_label = label
        self._last_confidence = confidence
        self._last_latency_ms = latency_ms

    # -- keyboard / direct commands --
    def select_waypoint(self, index: int) -> str:
        self._navigator.select_index(index)
        return self._navigator.selected_name

    def go_to_selected(self) -> None:
        self.set_mode("WAYPOINT")
        self._navigator.start_navigation()

    def start_patrol(self) -> None:
        self.set_mode("PATROL")
        self._patrol.start()

    def stop_patrol(self) -> None:
        self._patrol.stop()
        self.set_mode("MANUAL")

    def toggle_patrol_pause(self) -> None:
        self._patrol.toggle_pause()

    def skip_patrol_stop(self) -> None:
        self._patrol.skip()

    def grab(self) -> str | None:
        self.set_mode("PICK_PLACE")
        robot_xy = self._mj.get_robot_xy()
        return self._picker.grab(robot_xy)

    def release(self) -> None:
        self._picker.release()
        if self._mode == "PICK_PLACE":
            self.set_mode("MANUAL")

    def toggle_estop(self) -> None:
        self._safety.toggle_estop()

    def start_macro(self, name: str) -> bool:
        ok = self._sequencer.start_macro(name)
        if ok:
            self.set_mode("MACRO")
        return ok

    def abort_macro(self) -> None:
        self._sequencer.abort()
        self.set_mode("MANUAL")

    # -- manual action (keyboard testing) --
    def send_manual_action(self, action: str) -> None:
        """Set the manual action; the update tick will keep sending it."""
        if self._mode in ("MANUAL", "PICK_PLACE"):
            self._current_action = action

    # -- main update loop --
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[FactoryCtrl] Started at 20Hz.")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        print("[FactoryCtrl] Stopped.")

    def _run_loop(self) -> None:
        interval = 1.0 / 20.0  # 20Hz
        while self._running and self._bridge.is_running():
            t0 = time.perf_counter()
            try:
                self._update_tick()
            except Exception as e:
                print(f"[FactoryCtrl] tick error: {e}")
            elapsed = time.perf_counter() - t0
            sleep_s = interval - elapsed
            if sleep_s > 0:
                time.sleep(sleep_s)

    def _update_tick(self) -> None:
        robot_xy = self._mj.get_robot_xy()
        robot_yaw = self._mj.get_robot_yaw()
        robot_pos_3d = self._mj.get_body_pos("pelvis")

        # --- Safety check (always runs) ---
        both_fists = self._last_brain_label == "Both Fists"
        should_stop, reason = self._safety.should_override_stop(robot_xy, both_fists)
        self._safety_reason = reason

        # --- Determine action based on mode ---
        action = "STOP"

        if should_stop:
            action = "STOP"
        elif self._mode == "WAYPOINT":
            action = self._navigator.compute_steering(robot_xy, robot_yaw)
            if not self._navigator.is_navigating:
                self.set_mode("MANUAL")
        elif self._mode == "PATROL":
            if self._patrol.active and not self._patrol.paused:
                action = self._navigator.compute_steering(robot_xy, robot_yaw)
                if not self._navigator.is_navigating:
                    self._patrol.on_arrival()
                    # Re-compute for next waypoint
                    action = self._navigator.compute_steering(robot_xy, robot_yaw)
            else:
                action = "STOP"
        elif self._mode == "MACRO":
            if self._sequencer.active:
                self._sequencer.update(robot_xy)
                if self._navigator.is_navigating:
                    action = self._navigator.compute_steering(robot_xy, robot_yaw)
                else:
                    action = "STOP"
            else:
                self.set_mode("MANUAL")
        elif self._mode == "PICK_PLACE":
            action = self._current_action  # user steers manually
        elif self._mode == "MANUAL":
            action = self._current_action

        # --- Send action to robot (every tick, all modes) ---
        self._bridge.send_action(action)

        self._current_action = action

        # --- Update subsystems ---
        self._picker.update_held_position()
        self._pusher.update(robot_xy, robot_yaw)
        self._trail.update(robot_xy)
        self._status_light.update(robot_pos_3d, action)
        self._update_waypoint_markers()
        self._update_hud(robot_xy)

    def _update_waypoint_markers(self) -> None:
        """Highlight the currently selected waypoint marker."""
        idx = self._navigator._index
        if idx != self._last_highlighted_wp:
            # Dim the old one
            if self._last_highlighted_wp is not None:
                old_name = f"wp_marker_{self._last_highlighted_wp}"
                try:
                    self._mj.set_geom_rgba(old_name, [0.1, 0.8, 0.2, 0.35])
                except KeyError:
                    pass
            # Brighten new one
            new_name = f"wp_marker_{idx}"
            try:
                self._mj.set_geom_rgba(new_name, [0.0, 1.0, 0.3, 0.8])
            except KeyError:
                pass
            self._last_highlighted_wp = idx

    def _update_hud(self, robot_xy: np.ndarray) -> None:
        # Top-left: mode, brain label, confidence
        tl_label = f"Mode: {self._mode}"
        tl_value = f"Brain: {self._last_brain_label}  Conf: {self._last_confidence:.2f}"
        if self._last_latency_ms > 0:
            tl_value += f"  Lat: {self._last_latency_ms:.0f}ms"
        self._hud.set_top_left(tl_label, tl_value)

        # Top-right: waypoint info
        wp_name = self._navigator.selected_name
        nav_target = self._navigator.target_name or "—"
        dist = self._navigator.distance_to_target(robot_xy)
        dist_str = f"{dist:.2f}m" if dist is not None else "—"
        tr_label = f"Waypoint: [{self._navigator._index + 1}] {wp_name}"
        tr_value = f"Nav: {nav_target}  Dist: {dist_str}"
        if self._patrol.active:
            tr_value += f"  Patrol: {self._patrol.current_stop}"
            if self._patrol.paused:
                tr_value += " (PAUSED)"
        if self._sequencer.active:
            step = self._sequencer.current_step
            step_str = f"{step[0]}({step[1]})" if step else "done"
            tr_value += f"  Macro: {self._sequencer.progress} {step_str}"
        self._hud.set_top_right(tr_label, tr_value)

        # Bottom-left: pick & place
        if self._picker.is_holding:
            bl_label = f"Holding: {self._picker.held_name}"
        else:
            bl_label = "Pick & Place: IDLE"
        near_name, near_dist = self._picker.nearest_box_info(robot_xy)
        bl_value = f"Nearest box: {near_name} ({near_dist:.2f}m)" if near_name else "No boxes nearby"
        self._hud.set_bottom_left(bl_label, bl_value)

        # Bottom-right: safety
        obs_name, obs_dist, warning, danger = self._safety.check_obstacles(robot_xy)
        br_label = f"Action: {self._current_action}"
        br_parts = []
        if self._safety.estop_active:
            br_parts.append("!! E-STOP !!")
        elif self._safety_reason:
            br_parts.append(self._safety_reason)
        if danger:
            br_parts.append(f"DANGER: {obs_name} {obs_dist:.2f}m")
        elif warning:
            br_parts.append(f"Warning: {obs_name} {obs_dist:.2f}m")
        countdown = self._safety.estop_countdown
        if countdown is not None and countdown > 0:
            br_parts.append(f"E-stop in {countdown:.1f}s")
        zone = self._safety.check_geofence(robot_xy)
        if zone:
            br_parts.append(f"ZONE: {zone}")
        br_value = "  |  ".join(br_parts) if br_parts else "All clear"
        self._hud.set_bottom_right(br_label, br_value)

        self._hud.flush()
