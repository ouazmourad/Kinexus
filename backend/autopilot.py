"""Autopilot — waypoint navigation for voice-commanded autonomous movement."""

import math
from .state_machine import RobotAction
from .pathfinding import PathPlanner

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from constants import FACTORY_WAYPOINTS, WAYPOINT_ARRIVAL_DIST, WAYPOINT_ALIGN_THRESHOLD


_planner: PathPlanner | None = None

def _get_planner() -> PathPlanner:
    global _planner
    if _planner is None:
        _planner = PathPlanner()
    return _planner


# Aliases for fuzzy matching spoken landmark names
_LANDMARK_ALIASES = {
    "shelf a": "Shelf A",
    "shelf 1": "Shelf A",
    "shelve a": "Shelf A",
    "shelf b": "Shelf B",
    "shelf 2": "Shelf B",
    "shelve b": "Shelf B",
    "conveyor": "Conveyor",
    "conveyor belt": "Conveyor",
    "the conveyor": "Conveyor",
    "belt": "Conveyor",
    "table": "Table",
    "the table": "Table",
    "work table": "Table",
    "pallet 1": "Pallet 1",
    "pallet one": "Pallet 1",
    "source pallet": "Pallet 1",
    "first pallet": "Pallet 1",
    "palette 1": "Pallet 1",
    "palette one": "Pallet 1",
    "pallet 2": "Pallet 2",
    "pallet two": "Pallet 2",
    "destination pallet": "Pallet 2",
    "second pallet": "Pallet 2",
    "palette 2": "Pallet 2",
    "palette two": "Pallet 2",
    "pallet": "Pallet 2",
    "palette": "Pallet 2",
    "the pallet": "Pallet 2",
    "the palette": "Pallet 2",
    "pallet to": "Pallet 2",
    "palette to": "Pallet 2",
    "shelf to": "Shelf B",
    "shelve to": "Shelf B",
    "charging station": "Charging Station",
    "charging": "Charging Station",
    "charger": "Charging Station",
    "charge": "Charging Station",
    "tool cabinet": "Tool Cabinet",
    "tools": "Tool Cabinet",
    "cabinet": "Tool Cabinet",
    "tool box": "Tool Cabinet",
    "storage area": "Storage Area",
    "storage": "Storage Area",
    "storage rack": "Storage Area",
    "inspection zone": "Inspection Zone",
    "inspection": "Inspection Zone",
    "inspect": "Inspection Zone",
    "qc": "Inspection Zone",
}


class Autopilot:
    """Steers the robot toward a named waypoint using turn-then-walk control."""

    def __init__(self, target_name: str, target_xy: tuple[float, float], start_xy: tuple[float, float] = (0, 0)):
        self.target_name = target_name
        self.target_x, self.target_y = target_xy
        self.active = True
        self.arrived = False
        self.distance = float("inf")

        # Compute path with obstacle avoidance
        planner = _get_planner()
        self._waypoints = planner.find_path(start_xy, target_xy)
        self._wp_index = 0
        if not self._waypoints:
            # Fallback: direct path
            self._waypoints = [target_xy]

    def update(self, robot_xy, robot_yaw: float) -> RobotAction:
        """Compute next action given current robot pose. Called each tick."""
        if not self.active:
            return RobotAction.IDLE

        rx, ry = float(robot_xy[0]), float(robot_xy[1])

        # Current waypoint
        if self._wp_index >= len(self._waypoints):
            self.active = False
            self.arrived = True
            return RobotAction.STOP

        wx, wy = self._waypoints[self._wp_index]
        dx = wx - rx
        dy = wy - ry
        wp_dist = math.sqrt(dx * dx + dy * dy)

        # Check overall distance to final target
        fdx = self.target_x - rx
        fdy = self.target_y - ry
        self.distance = math.sqrt(fdx * fdx + fdy * fdy)

        # If close to current waypoint, advance to next
        if wp_dist < WAYPOINT_ARRIVAL_DIST:
            self._wp_index += 1
            if self._wp_index >= len(self._waypoints):
                self.active = False
                self.arrived = True
                return RobotAction.STOP
            wx, wy = self._waypoints[self._wp_index]
            dx = wx - rx
            dy = wy - ry

        # Desired heading to current waypoint
        desired_yaw = math.atan2(dy, dx)

        # Angle difference normalized to [-pi, pi]
        angle_diff = desired_yaw - robot_yaw
        while angle_diff > math.pi:
            angle_diff -= 2 * math.pi
        while angle_diff < -math.pi:
            angle_diff += 2 * math.pi

        # Turn to face waypoint, then walk forward
        if abs(angle_diff) > WAYPOINT_ALIGN_THRESHOLD:
            return RobotAction.ROTATE_LEFT if angle_diff > 0 else RobotAction.ROTATE_RIGHT
        else:
            return RobotAction.MOVE_FORWARD

    def cancel(self):
        """Cancel navigation."""
        self.active = False

    def get_status(self) -> dict:
        return {
            "active": self.active,
            "target_name": self.target_name,
            "target_x": self.target_x,
            "target_y": self.target_y,
            "distance": round(self.distance, 2),
            "arrived": self.arrived,
            "waypoints_total": len(self._waypoints),
            "waypoints_remaining": max(0, len(self._waypoints) - self._wp_index),
        }

    @staticmethod
    def resolve_target(name: str) -> tuple[str, tuple[float, float]] | None:
        """Resolve a spoken landmark name to (canonical_name, (x, y)) or None."""
        name_lower = name.lower().strip()

        # Try alias table first (exact match)
        if name_lower in _LANDMARK_ALIASES:
            canonical = _LANDMARK_ALIASES[name_lower]
            return canonical, FACTORY_WAYPOINTS[canonical]

        # Try substring match against waypoint names
        for wp_name, coords in FACTORY_WAYPOINTS.items():
            if wp_name.lower() in name_lower or name_lower in wp_name.lower():
                return wp_name, coords

        return None
