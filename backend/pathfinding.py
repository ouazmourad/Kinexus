"""
A* Grid-Based Pathfinding for Factory Floor Navigation.

Builds a 2D occupancy grid from the known factory scene layout,
runs A* search, and returns a smoothed path suitable for robot
dead-reckoning or simulation bridge commands.

Usage:
    planner = PathPlanner(grid_resolution=0.25, robot_radius=0.3)
    path = planner.find_path((0.0, 0.0), (-3.5, -2.0))
    # path is a list of (x, y) tuples in world coordinates
"""

from __future__ import annotations

import heapq
import math
from typing import Optional

from constants import (
    FACTORY_WAYPOINTS,
    FACTORY_OBSTACLE_GEOMS,
    WAYPOINT_ARRIVAL_DIST,
)

# ---------------------------------------------------------------------------
# Map boundaries (meters) — matches the factory_scene.xml floor extents
# ---------------------------------------------------------------------------
MAP_MIN_X = -7.5
MAP_MAX_X = 7.5
MAP_MIN_Y = -5.5
MAP_MAX_Y = 7.5

# ---------------------------------------------------------------------------
# Obstacle definitions from factory_scene.xml
# Each entry: (center_x, center_y, half_width, half_height)
# These are axis-aligned bounding boxes in the XY ground plane.
# ---------------------------------------------------------------------------
_SCENE_OBSTACLES: list[tuple[float, float, float, float]] = [
    # Pillars (box 0.15 x 0.15 half-extents)
    (-4.0, -4.0, 0.15, 0.15),   # pillar_1
    (4.0, -4.0, 0.15, 0.15),    # pillar_2

    # Bollards (cylinder radius 0.06 — treat as square AABB)
    (-2.0, 0.5, 0.06, 0.06),    # bollard_1
    (-2.0, -0.5, 0.06, 0.06),   # bollard_2
    (2.0, 0.5, 0.06, 0.06),     # bollard_3
    (2.0, -0.5, 0.06, 0.06),    # bollard_4

    # --- Shelf A (left side, centered at -3.5, -2.0) ---
    # Uprights (box 0.03 x 0.03 half-extents)
    (-4.1, -1.7, 0.03, 0.03),   # sA_upright_FL
    (-2.9, -1.7, 0.03, 0.03),   # sA_upright_FR
    (-4.1, -2.3, 0.03, 0.03),   # sA_upright_BL
    (-2.9, -2.3, 0.03, 0.03),   # sA_upright_BR
    # Shelf surfaces (box 0.65 x 0.35 half-extents)
    (-3.5, -2.0, 0.65, 0.35),   # sA_shelf_bottom
    (-3.5, -2.0, 0.65, 0.35),   # sA_shelf_top (same footprint)

    # --- Shelf B (right side, centered at 3.5, -2.0) ---
    # Uprights
    (2.9, -1.7, 0.03, 0.03),    # sB_upright_FL
    (4.1, -1.7, 0.03, 0.03),    # sB_upright_FR
    (2.9, -2.3, 0.03, 0.03),    # sB_upright_BL
    (4.1, -2.3, 0.03, 0.03),    # sB_upright_BR
    # Shelf surfaces
    (3.5, -2.0, 0.65, 0.35),    # sB_shelf_bottom
    (3.5, -2.0, 0.65, 0.35),    # sB_shelf_top

    # Conveyor (centered at 0, -3.5 — box 1.6 x 0.3 half-extents)
    (0.0, -3.5, 1.6, 0.3),

    # Table (centered at 2, 1.5 — box 0.5 x 0.35 half-extents)
    (2.0, 1.5, 0.5, 0.35),

    # Pallets (box 0.5 x 0.4 half-extents)
    (-1.5, 1.0, 0.5, 0.4),      # pallet_1
    (1.5, 1.0, 0.5, 0.4),       # pallet_2

    # Boundary walls
    (0.0, 7.5, 8.0, 0.1),       # wall_north
    (0.0, -5.5, 8.0, 0.1),      # wall_south
    (7.5, 1.0, 0.1, 6.5),       # wall_east
    (-7.5, 1.0, 0.1, 6.5),      # wall_west

    # Charging station (platform at -5.5, 3.5 — box 0.6 x 0.6 half-extents)
    (-5.5, 3.5, 0.6, 0.6),
    (-5.5, 4.1, 0.04, 0.04),    # charging pole

    # Tool cabinet (at 5.5, -0.5 — box 0.4 x 0.25 half-extents)
    (5.5, -0.5, 0.4, 0.25),

    # Storage rack (at -5.0, -3.5 — box 0.8 x 0.4 half-extents)
    (-5.0, -3.5, 0.8, 0.4),

    # Inspection table (at 0.0, 4.5 — box 0.6 x 0.4 half-extents)
    (0.0, 4.5, 0.6, 0.4),
]

# A* movement directions: 8-connected grid
_DIRECTIONS = [
    (1, 0), (-1, 0), (0, 1), (0, -1),      # cardinal
    (1, 1), (1, -1), (-1, 1), (-1, -1),     # diagonal
]
_SQRT2 = math.sqrt(2.0)


class PathPlanner:
    """A* grid-based path planner for the factory floor.

    Builds a binary occupancy grid from hardcoded obstacle rectangles
    (inflated by robot_radius), then searches for the shortest collision-free
    path between arbitrary world-coordinate points.

    Parameters
    ----------
    grid_resolution : float
        Size of each grid cell in meters (default 0.25 m).
    robot_radius : float
        Inflation radius in meters applied to all obstacles (default 0.3 m).
    """

    def __init__(self, grid_resolution: float = 0.25, robot_radius: float = 0.3):
        self.resolution = grid_resolution
        self.robot_radius = robot_radius

        # Grid dimensions
        self.min_x = MAP_MIN_X
        self.max_x = MAP_MAX_X
        self.min_y = MAP_MIN_Y
        self.max_y = MAP_MAX_Y

        self.cols = int(math.ceil((self.max_x - self.min_x) / self.resolution))
        self.rows = int(math.ceil((self.max_y - self.min_y) / self.resolution))

        # Build occupancy grid: True = occupied / blocked
        self.grid: list[list[bool]] = self._build_grid()

    # ------------------------------------------------------------------
    # Grid construction
    # ------------------------------------------------------------------

    def _build_grid(self) -> list[list[bool]]:
        """Create a 2D boolean grid. True means the cell is blocked."""
        grid = [[False] * self.cols for _ in range(self.rows)]

        for cx, cy, hx, hy in _SCENE_OBSTACLES:
            # Inflate obstacle by robot radius
            inflated_hx = hx + self.robot_radius
            inflated_hy = hy + self.robot_radius

            # Obstacle world-space bounds
            obs_min_x = cx - inflated_hx
            obs_max_x = cx + inflated_hx
            obs_min_y = cy - inflated_hy
            obs_max_y = cy + inflated_hy

            # Convert to grid cell range
            col_lo = max(0, int(math.floor((obs_min_x - self.min_x) / self.resolution)))
            col_hi = min(self.cols - 1, int(math.floor((obs_max_x - self.min_x) / self.resolution)))
            row_lo = max(0, int(math.floor((obs_min_y - self.min_y) / self.resolution)))
            row_hi = min(self.rows - 1, int(math.floor((obs_max_y - self.min_y) / self.resolution)))

            for r in range(row_lo, row_hi + 1):
                for c in range(col_lo, col_hi + 1):
                    grid[r][c] = True

        return grid

    # ------------------------------------------------------------------
    # Coordinate conversion helpers
    # ------------------------------------------------------------------

    def _world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        """Convert world (x, y) to grid (row, col)."""
        col = int(math.floor((x - self.min_x) / self.resolution))
        row = int(math.floor((y - self.min_y) / self.resolution))
        col = max(0, min(self.cols - 1, col))
        row = max(0, min(self.rows - 1, row))
        return row, col

    def _grid_to_world(self, row: int, col: int) -> tuple[float, float]:
        """Convert grid (row, col) to world (x, y) at cell center."""
        x = self.min_x + (col + 0.5) * self.resolution
        y = self.min_y + (row + 0.5) * self.resolution
        return x, y

    def _in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.rows and 0 <= col < self.cols

    def is_occupied(self, x: float, y: float) -> bool:
        """Check whether a world-coordinate point lies in a blocked cell."""
        r, c = self._world_to_grid(x, y)
        return self.grid[r][c]

    # ------------------------------------------------------------------
    # A* search
    # ------------------------------------------------------------------

    def _heuristic(self, r1: int, c1: int, r2: int, c2: int) -> float:
        """Octile distance heuristic (consistent for 8-connected grids)."""
        dr = abs(r1 - r2)
        dc = abs(c1 - c2)
        return max(dr, dc) + (_SQRT2 - 1.0) * min(dr, dc)

    def _astar(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
    ) -> Optional[list[tuple[int, int]]]:
        """Run A* on the grid. Returns list of (row, col) or None."""
        sr, sc = start
        gr, gc = goal

        # If start or goal is blocked, try to find the nearest free cell
        if self.grid[sr][sc]:
            free = self._nearest_free(sr, sc)
            if free is None:
                return None
            sr, sc = free

        if self.grid[gr][gc]:
            free = self._nearest_free(gr, gc)
            if free is None:
                return None
            gr, gc = free

        # Priority queue: (f_cost, counter, row, col)
        counter = 0
        open_set: list[tuple[float, int, int, int]] = []
        heapq.heappush(open_set, (0.0, counter, sr, sc))

        g_cost: dict[tuple[int, int], float] = {(sr, sc): 0.0}
        came_from: dict[tuple[int, int], Optional[tuple[int, int]]] = {(sr, sc): None}

        while open_set:
            f, _, cr, cc = heapq.heappop(open_set)

            if cr == gr and cc == gc:
                # Reconstruct path
                path = []
                node: Optional[tuple[int, int]] = (gr, gc)
                while node is not None:
                    path.append(node)
                    node = came_from[node]
                path.reverse()
                return path

            current_g = g_cost[(cr, cc)]

            # Skip if we already found a cheaper route here
            if current_g > g_cost.get((cr, cc), float("inf")):
                continue

            for dr, dc in _DIRECTIONS:
                nr, nc = cr + dr, cc + dc
                if not self._in_bounds(nr, nc):
                    continue
                if self.grid[nr][nc]:
                    continue

                # Diagonal moves cost sqrt(2), cardinal moves cost 1
                move_cost = _SQRT2 if (dr != 0 and dc != 0) else 1.0

                # Block diagonal if both adjacent cardinal cells are occupied
                # (prevents corner-cutting through diagonal gaps)
                if dr != 0 and dc != 0:
                    if self.grid[cr + dr][cc] and self.grid[cr][cc + dc]:
                        continue

                new_g = current_g + move_cost
                if new_g < g_cost.get((nr, nc), float("inf")):
                    g_cost[(nr, nc)] = new_g
                    f_cost = new_g + self._heuristic(nr, nc, gr, gc)
                    came_from[(nr, nc)] = (cr, cc)
                    counter += 1
                    heapq.heappush(open_set, (f_cost, counter, nr, nc))

        return None  # No path found

    def _nearest_free(self, row: int, col: int, max_radius: int = 20) -> Optional[tuple[int, int]]:
        """BFS outward from (row, col) to find the nearest unoccupied cell."""
        from collections import deque

        visited: set[tuple[int, int]] = {(row, col)}
        queue: deque[tuple[int, int, int]] = deque([(row, col, 0)])

        while queue:
            r, c, dist = queue.popleft()
            if dist > max_radius:
                return None
            if not self.grid[r][c]:
                return (r, c)
            for dr, dc in _DIRECTIONS:
                nr, nc = r + dr, c + dc
                if self._in_bounds(nr, nc) and (nr, nc) not in visited:
                    visited.add((nr, nc))
                    queue.append((nr, nc, dist + 1))

        return None

    # ------------------------------------------------------------------
    # Path smoothing
    # ------------------------------------------------------------------

    def _line_of_sight(self, r1: int, c1: int, r2: int, c2: int) -> bool:
        """Bresenham-based line-of-sight check between two grid cells.

        Returns True if every cell along the line is free (not occupied).
        """
        dr = abs(r2 - r1)
        dc = abs(c2 - c1)
        sr = 1 if r2 > r1 else -1
        sc = 1 if c2 > c1 else -1

        r, c = r1, c1
        err = dr - dc

        while True:
            if self.grid[r][c]:
                return False
            if r == r2 and c == c2:
                break
            e2 = 2 * err
            if e2 > -dc:
                err -= dc
                r += sr
            if e2 < dr:
                err += dr
                c += sc

        return True

    def _smooth_path(self, grid_path: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Greedy path shortcutting using line-of-sight checks.

        Iterates through the path and skips intermediate waypoints
        whenever a direct line of sight exists to a further waypoint.
        """
        if len(grid_path) <= 2:
            return grid_path

        smoothed = [grid_path[0]]
        current_idx = 0

        while current_idx < len(grid_path) - 1:
            # Try to skip ahead as far as possible
            best_idx = current_idx + 1
            for look_ahead in range(len(grid_path) - 1, current_idx + 1, -1):
                cr, cc = grid_path[current_idx]
                lr, lc = grid_path[look_ahead]
                if self._line_of_sight(cr, cc, lr, lc):
                    best_idx = look_ahead
                    break
            smoothed.append(grid_path[best_idx])
            current_idx = best_idx

        return smoothed

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_path(
        self,
        start_xy: tuple[float, float],
        goal_xy: tuple[float, float],
    ) -> list[tuple[float, float]]:
        """Find a collision-free path from start to goal.

        Parameters
        ----------
        start_xy : tuple[float, float]
            Starting position in world coordinates (x, y).
        goal_xy : tuple[float, float]
            Goal position in world coordinates (x, y).

        Returns
        -------
        list[tuple[float, float]]
            Ordered list of (x, y) waypoints from start to goal.
            The first point is near start_xy and the last is near goal_xy.
            Returns an empty list if no path can be found.
        """
        start_rc = self._world_to_grid(start_xy[0], start_xy[1])
        goal_rc = self._world_to_grid(goal_xy[0], goal_xy[1])

        # Trivial case: already at goal
        if start_rc == goal_rc:
            return [goal_xy]

        # Run A*
        grid_path = self._astar(start_rc, goal_rc)
        if grid_path is None:
            return []

        # Smooth the grid path to remove unnecessary zigzags
        smoothed_grid = self._smooth_path(grid_path)

        # Convert grid cells back to world coordinates
        world_path = [self._grid_to_world(r, c) for r, c in smoothed_grid]

        # Replace first and last with exact requested coordinates
        # (only if they are not in occupied cells)
        if not self.is_occupied(start_xy[0], start_xy[1]):
            world_path[0] = start_xy
        if not self.is_occupied(goal_xy[0], goal_xy[1]):
            world_path[-1] = goal_xy

        return world_path

    def find_path_to_waypoint(
        self,
        start_xy: tuple[float, float],
        waypoint_name: str,
    ) -> list[tuple[float, float]]:
        """Convenience method: find path from start to a named factory waypoint.

        Parameters
        ----------
        start_xy : tuple[float, float]
            Current robot position in world coordinates.
        waypoint_name : str
            Name of a waypoint defined in constants.FACTORY_WAYPOINTS.

        Returns
        -------
        list[tuple[float, float]]
            Path waypoints, or empty list if waypoint not found or no path.
        """
        goal = FACTORY_WAYPOINTS.get(waypoint_name)
        if goal is None:
            return []
        return self.find_path(start_xy, goal)

    def path_length(self, path: list[tuple[float, float]]) -> float:
        """Compute total Euclidean length of a path in meters."""
        total = 0.0
        for i in range(1, len(path)):
            dx = path[i][0] - path[i - 1][0]
            dy = path[i][1] - path[i - 1][1]
            total += math.sqrt(dx * dx + dy * dy)
        return total

    def get_grid_debug(self) -> dict:
        """Return grid metadata for visualization/debugging.

        Returns
        -------
        dict
            Grid info including dimensions, resolution, bounds, and
            the number of occupied vs. free cells.
        """
        occupied = sum(cell for row in self.grid for cell in row)
        total = self.rows * self.cols
        return {
            "rows": self.rows,
            "cols": self.cols,
            "resolution": self.resolution,
            "bounds": {
                "min_x": self.min_x,
                "max_x": self.max_x,
                "min_y": self.min_y,
                "max_y": self.max_y,
            },
            "occupied_cells": occupied,
            "free_cells": total - occupied,
            "total_cells": total,
            "occupancy_pct": round(100.0 * occupied / total, 1) if total > 0 else 0.0,
        }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    planner = PathPlanner()
    info = planner.get_grid_debug()
    print(f"Grid: {info['cols']}x{info['rows']} cells at {info['resolution']}m resolution")
    print(f"Occupied: {info['occupied_cells']} / {info['total_cells']} ({info['occupancy_pct']}%)")
    print()

    # Test paths between all named waypoints
    names = list(FACTORY_WAYPOINTS.keys())
    origin = (0.0, 0.0)

    print(f"Paths from origin {origin}:")
    for name in names:
        goal = FACTORY_WAYPOINTS[name]
        path = planner.find_path(origin, goal)
        if path:
            length = planner.path_length(path)
            print(f"  -> {name:12s} {goal}: {len(path)} waypoints, {length:.2f}m")
        else:
            print(f"  -> {name:12s} {goal}: NO PATH FOUND")

    print()
    print("Cross-waypoint paths:")
    for i, src_name in enumerate(names):
        for dst_name in names[i + 1:]:
            src = FACTORY_WAYPOINTS[src_name]
            dst = FACTORY_WAYPOINTS[dst_name]
            path = planner.find_path(src, dst)
            if path:
                length = planner.path_length(path)
                print(f"  {src_name:12s} -> {dst_name:12s}: {len(path)} pts, {length:.2f}m")
            else:
                print(f"  {src_name:12s} -> {dst_name:12s}: NO PATH")
