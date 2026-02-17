"""Robot Manager — multi-robot selection and per-robot state machines."""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .state_machine import GearStateMachine, RobotAction


_CONFIG_PATH = Path(__file__).resolve().parent.parent / "robot_config.json"

def _load_robot_config() -> list[dict]:
    """Load robot configurations from robot_config.json, fall back to single robot."""
    try:
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)
        robots = cfg.get("robots", [])
        if robots:
            return robots
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    # Default: single robot at origin
    return [{"id": "robot_0", "x": 0.0, "y": 0.0, "orientation": 0.0, "color": "#3b82f6"}]


@dataclass
class Robot:
    id: str
    position: list  # [x, y, z]
    orientation: float
    holding_item: bool = False
    task: Optional[dict] = None
    color: str = "#3b82f6"


class RobotManager:
    """Manages multiple robots with per-robot state machines."""

    def __init__(self):
        self.robots: list[Robot] = []
        self.state_machines: dict[str, GearStateMachine] = {}
        self.selected_index: int = 0
        self.active_robot_ids: set[str] = set()  # robots targeted by orchestration tasks
        self._init_robots()

    def _init_robots(self):
        """Initialize robots from config file."""
        self.robots = []
        self.state_machines = {}
        robot_configs = _load_robot_config()
        for cfg in robot_configs:
            robot = Robot(
                id=cfg["id"],
                position=[cfg.get("x", 0.0), cfg.get("y", 0.0), 0.0],
                orientation=cfg.get("orientation", 0.0),
                color=cfg.get("color", "#3b82f6"),
            )
            self.robots.append(robot)
            self.state_machines[cfg["id"]] = GearStateMachine()
        self.selected_index = 0
        self.active_robot_ids = {robot_configs[0]["id"]}

    def set_active_robots(self, robot_ids: list[str]):
        """Set which robots are targeted by orchestration tasks."""
        if robot_ids:
            self.active_robot_ids = set(robot_ids)
        else:
            self.active_robot_ids = {self.selected_robot.id}

    @property
    def selected_robot(self) -> Robot:
        return self.robots[self.selected_index]

    @property
    def selected_sm(self) -> GearStateMachine:
        return self.state_machines[self.selected_robot.id]

    def select_by_direction(self, direction: str):
        """Select robot by direction from current selection.
        'right' -> next index, 'left' -> previous index.
        """
        n = len(self.robots)
        if direction == "right":
            self.selected_index = (self.selected_index + 1) % n
        else:
            self.selected_index = (self.selected_index - 1) % n
        print(f"[RobotManager] Selected {self.selected_robot.id}")

    def select_by_id(self, robot_id: str):
        """Select a specific robot by ID."""
        for i, r in enumerate(self.robots):
            if r.id == robot_id:
                self.selected_index = i
                print(f"[RobotManager] Selected {robot_id}")
                return
        print(f"[RobotManager] Unknown robot: {robot_id}")

    def update_robot_state(self, robot_id: str, position: list, orientation: float):
        """Update a robot's position from simulation."""
        for r in self.robots:
            if r.id == robot_id:
                r.position = position
                r.orientation = orientation
                return

    def get_all_states(self) -> list[dict]:
        """Serialized robot list for frontend broadcast."""
        result = []
        for i, robot in enumerate(self.robots):
            sm = self.state_machines[robot.id]
            result.append({
                "id": robot.id,
                "position": robot.position,
                "orientation": robot.orientation,
                "gear": sm.state.gear.value,
                "holding_item": robot.holding_item,
                "selected": i == self.selected_index,
                "active": robot.id in self.active_robot_ids,
                "task": robot.task,
                "color": robot.color,
                "toggled_action": sm.state.toggled_action.value if sm.state.toggled_action else None,
            })
        return result

    def reset(self):
        """Reset all robots and state machines."""
        self._init_robots()
