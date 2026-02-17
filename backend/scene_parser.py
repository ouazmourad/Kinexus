"""Parse MuJoCo scene XML into 2D map data for the dashboard."""

import xml.etree.ElementTree as ET
from pathlib import Path


def parse_scene(xml_path: str) -> dict:
    """Parse a MuJoCo scene XML and extract 2D map objects with colors.

    Returns a dict with:
      - materials: {name: {rgba: [r,g,b,a], ...}}
      - objects: list of {name, type, pos, size, material, rgba, category}
      - floor_size: [half_x, half_y]
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # --- Parse materials ---
    materials = {}
    for mat in root.iter("material"):
        name = mat.get("name")
        if not name:
            continue
        rgba_str = mat.get("rgba")
        rgba = [float(v) for v in rgba_str.split()] if rgba_str else [0.5, 0.5, 0.5, 1.0]
        materials[name] = {
            "rgba": rgba,
            "hex": _rgba_to_hex(rgba),
        }

    # --- Parse geoms ---
    objects = []
    floor_size = [8, 8]  # default

    for geom in root.iter("geom"):
        name = geom.get("name", "")
        geom_type = geom.get("type", "sphere")
        mat_name = geom.get("material", "")

        # Parse position (x y z) — default to origin
        pos_str = geom.get("pos", "0 0 0")
        pos = [float(v) for v in pos_str.split()]
        while len(pos) < 3:
            pos.append(0.0)

        # Parse size
        size_str = geom.get("size", "0.1")
        size = [float(v) for v in size_str.split()]

        # Get color from material
        rgba = materials.get(mat_name, {}).get("rgba", [0.5, 0.5, 0.5, 1.0])
        hex_color = materials.get(mat_name, {}).get("hex", "#808080")

        # Categorize by name/type for the frontend legend
        category = _categorize(name, mat_name, geom_type)

        # Floor is special — store its size for bounds
        if geom_type == "plane":
            if len(size) >= 2:
                floor_size = [size[0], size[1]]
            continue  # don't add floor as an object

        # Build 2D representation
        obj = {
            "name": name,
            "type": geom_type,       # box, cylinder, plane
            "category": category,
            "material": mat_name,
            "rgba": rgba,
            "hex": hex_color,
            "x": pos[0],             # world X
            "y": pos[1],             # world Y (MuJoCo forward)
            "z": pos[2],             # world Z (height) — for layering
        }

        if geom_type == "box":
            # MuJoCo box size = half-extents [sx, sy, sz]
            obj["w"] = size[0] * 2 if len(size) >= 1 else 0.2
            obj["h"] = size[1] * 2 if len(size) >= 2 else 0.2
        elif geom_type == "cylinder":
            # MuJoCo cylinder size = [radius, half_height]
            obj["r"] = size[0] if len(size) >= 1 else 0.1
        else:
            obj["w"] = 0.2
            obj["h"] = 0.2

        objects.append(obj)

    # Sort by z (height) so ground-level items draw first, elevated items on top
    objects.sort(key=lambda o: o["z"])

    return {
        "materials": materials,
        "objects": objects,
        "floor_size": floor_size,
    }


def _rgba_to_hex(rgba: list) -> str:
    """Convert [r, g, b, a] (0-1 floats) to #rrggbb hex string."""
    r = int(min(1.0, max(0.0, rgba[0])) * 255)
    g = int(min(1.0, max(0.0, rgba[1])) * 255)
    b = int(min(1.0, max(0.0, rgba[2])) * 255)
    return f"#{r:02x}{g:02x}{b:02x}"


def _categorize(name: str, material: str, geom_type: str) -> str:
    """Assign a semantic category based on geom name/material."""
    n = name.lower()
    m = material.lower()

    if "floor" in n:
        return "floor"
    if "wall" in n:
        return "wall"
    if "pillar" in n:
        return "pillar"
    if "lane" in n:
        return "lane"
    if "shelf" in n and ("shelf" in n and "box" not in n):
        return "shelf"
    if n.startswith("sa_") or n.startswith("sb_"):
        if "upright" in n or "brace" in n:
            return "shelf_frame"
        if "shelf" in n:
            return "shelf"
        if "box" in n:
            return "box"
    if "conv" in n:
        if "belt" in n:
            return "conveyor"
        if "rail" in n or "leg" in n:
            return "conveyor_frame"
        if "box" in n:
            return "box"
    if "table" in n:
        if "surface" in n or "top" in n:
            return "table"
        if "leg" in n:
            return "table_leg"
        if "box" in n:
            return "box"
    if "pallet" in n and "box" not in n:
        return "pallet"
    if "p1_" in n or "p2_" in n:
        return "box"
    if "bollard" in n:
        return "bollard"
    if "charge" in n or "charging" in n:
        return "charging_station"
    if "cabinet" in n:
        return "tool_cabinet"
    if "storage" in n and "box" not in n:
        return "storage_rack"
    if "inspect" in n:
        return "inspection_zone"
    if "box" in n or "box" in m:
        return "box"

    # Fallback
    if "wall" in m:
        return "wall"
    if "shelf" in m or "beam" in m:
        return "shelf_frame"
    if "pallet" in m:
        return "pallet"
    if "safety" in m or "stripe" in m:
        return "bollard"
    if "conveyor" in m:
        return "conveyor"
    if "table" in m:
        return "table"

    return "other"


# Default scene path
_DEFAULT_SCENE = str(Path(__file__).resolve().parent.parent / "simulation" / "scenes" / "factory_scene.xml")


def get_default_map() -> dict:
    """Parse the default factory scene and return map data."""
    return parse_scene(_DEFAULT_SCENE)
