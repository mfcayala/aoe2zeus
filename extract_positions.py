"""
extract_positions.py — Spatial data extraction from AoE2 DE replay files.

Produces structured position data for minimap and timeline visualisation.

Design principles:
  - Coordinates are normalised to [0.0, 1.0] relative to map dimension
    so the rendering layer is map-size agnostic.
  - All data classes expose `to_dict()` for clean JSON serialisation.
  - This module has no dependency on extract_game_data.py; it can be
    used standalone or composed with it.
  - Activity events are downsampled (one per player per ACTIVITY_INTERVAL_S)
    to keep output payload manageable.

Public API:
    extract_positions(replay_path: str) -> ReplayPositions
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

from mgz.model import parse_match
from mgz.summary import Summary


# ── Constants ──────────────────────────────────────────────────────────────────

# Gaia object class IDs
_CLASS_TREE    = 70
_CLASS_CLIFF   = 50
_CLASS_MISC    = 10   # terrain decor
_CLASS_ANIMAL  = 20   # deer, boar

# Named gaia object → resource category
_RESOURCE_NAMES: dict[str, str] = {
    "Gold Mine":    "gold",
    "Stone Mine":   "stone",
    "Wild Boar":    "boar",
    "Pig":          "boar",
    "Rhinoceros":   "boar",
    "Javelina":     "boar",
    "Deer":         "hunt",
    "Ostrich":      "hunt",
    "Zebra":        "hunt",
    "Elephant":     "hunt",
    "Forage Bush":  "berries",
    "Fruit Bush":   "berries",
}

# Action types that indicate unit activity at a map position
_ACTIVITY_TYPES = frozenset({"Move", "Target", "Patrol", "Attack"})

# Minimum seconds between recorded activity points per player
ACTIVITY_INTERVAL_S: int = 5


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class Point:
    """Normalised map coordinate, each axis in [0.0, 1.0]."""
    x: float
    y: float

    def to_dict(self) -> dict:
        return {"x": round(self.x, 4), "y": round(self.y, 4)}


@dataclass
class MapLayer:
    """
    Terrain and resource data for the static map backdrop.

    `terrain` is a row-major flat array of terrain IDs, length = dimension²,
    indexed as terrain[y * dimension + x].  The frontend can palette-map
    terrain IDs to colours without knowing their game semantics.
    """
    dimension: int
    terrain: list[int]          # flat [y * dim + x], terrain_id values
    elevation: list[int]        # flat [y * dim + x], elevation values
    resources: list[dict]       # [{type, x, y}] normalised

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "terrain":   self.terrain,
            "elevation": self.elevation,
            "resources": self.resources,
        }


@dataclass
class BuildEvent:
    """A building placed on the map."""
    time_s: int
    building: str
    pos: Point

    def to_dict(self) -> dict:
        return {"time_s": self.time_s, "building": self.building, "pos": self.pos.to_dict()}


@dataclass
class ActivityEvent:
    """
    A downsampled unit-command position — where a player directed attention.
    Covers Move, Target, Patrol, and Attack commands.
    """
    time_s: int
    action: str
    pos: Point

    def to_dict(self) -> dict:
        return {"time_s": self.time_s, "action": self.action, "pos": self.pos.to_dict()}


@dataclass
class PlayerPositions:
    """All spatial data for a single player across the full game."""
    number: int
    name: str
    color_id: int
    tc: Point                           # starting Town Centre position
    buildings: list[BuildEvent]         # in chronological order
    activity: list[ActivityEvent]       # downsampled, chronological

    def to_dict(self) -> dict:
        return {
            "number":    self.number,
            "name":      self.name,
            "color_id":  self.color_id,
            "tc":        self.tc.to_dict(),
            "buildings": [b.to_dict() for b in self.buildings],
            "activity":  [a.to_dict() for a in self.activity],
        }


@dataclass
class ReplayPositions:
    """Top-level container returned by extract_positions()."""
    duration_s: int
    map: MapLayer
    players: dict[int, PlayerPositions]  # keyed by player number

    def to_dict(self) -> dict:
        return {
            "duration_s": self.duration_s,
            "map":        self.map.to_dict(),
            "players":    {k: v.to_dict() for k, v in self.players.items()},
        }


# ── Internal helpers ───────────────────────────────────────────────────────────

def _td_to_s(td: timedelta) -> int:
    return int(td.total_seconds())


def _norm(value: float, dimension: int) -> float:
    """Normalise a raw map coordinate to [0, 1]."""
    return max(0.0, min(1.0, value / dimension))


def _point(pos, dimension: int) -> Point:
    return Point(_norm(pos.x, dimension), _norm(pos.y, dimension))


def _build_map_layer(summary: Summary) -> MapLayer:
    """Extract terrain grid and static gaia resources from Summary."""
    map_info = summary.get_map()
    dim = map_info["dimension"]
    tiles = map_info.get("tiles", [])

    # Build flat arrays indexed y*dim + x
    terrain   = [0] * (dim * dim)
    elevation = [0] * (dim * dim)
    for t in tiles:
        idx = t["y"] * dim + t["x"]
        terrain[idx]   = t["terrain_id"]
        elevation[idx] = t["elevation"]

    return MapLayer(
        dimension=dim,
        terrain=terrain,
        elevation=elevation,
        resources=[],   # populated later from gaia objects
    )


def _classify_gaia_resources(gaia_objects, dimension: int) -> list[dict]:
    """Return resource dots (gold, stone, trees, hunt, boar, berries) from gaia."""
    resources = []
    seen_positions: set[tuple[int, int]] = set()   # deduplicate overlapping

    for obj in gaia_objects:
        pos = getattr(obj, "position", None)
        if pos is None:
            continue

        name = getattr(obj, "name", None)
        class_id = obj.class_id

        if name and name in _RESOURCE_NAMES:
            category = _RESOURCE_NAMES[name]
        elif class_id == _CLASS_TREE:
            category = "tree"
        else:
            continue

        # Round to integer grid to deduplicate very close objects
        gx, gy = round(pos.x), round(pos.y)
        key = (gx, gy, category)
        if key in seen_positions:
            continue
        seen_positions.add(key)

        resources.append({
            "type": category,
            "x": round(_norm(pos.x, dimension), 4),
            "y": round(_norm(pos.y, dimension), 4),
        })

    return resources


def _extract_player_positions(
    match,
    dimension: int,
    summary_color_ids: dict[str, int] | None = None,
) -> dict[int, PlayerPositions]:
    """Parse all inputs and return per-player positional data."""

    # Index inputs by player number
    inputs_by_player: dict[int, list] = defaultdict(list)
    for inp in match.inputs:
        p = getattr(inp, "player", None)
        if p is not None:
            inputs_by_player[p.number].append(inp)

    # Build player map: number → PlayerPositions
    players: dict[int, PlayerPositions] = {}

    for p in match.players:
        tc_raw = p.position
        tc = _point(tc_raw, dimension) if tc_raw else Point(0.5, 0.5)

        buildings: list[BuildEvent] = []
        activity:  list[ActivityEvent] = []

        last_activity_s: int = -ACTIVITY_INTERVAL_S  # allow first event immediately

        for inp in inputs_by_player[p.number]:
            t = _td_to_s(inp.timestamp)
            pos_raw = getattr(inp, "position", None)

            if inp.type == "Build" and pos_raw:
                building_name = inp.payload.get("building") or inp.payload.get("building_id") or "?"
                buildings.append(BuildEvent(
                    time_s=t,
                    building=str(building_name),
                    pos=_point(pos_raw, dimension),
                ))

            elif inp.type in _ACTIVITY_TYPES and pos_raw:
                if t - last_activity_s >= ACTIVITY_INTERVAL_S:
                    activity.append(ActivityEvent(
                        time_s=t,
                        action=inp.type,
                        pos=_point(pos_raw, dimension),
                    ))
                    last_activity_s = t

        # Sort chronologically (inputs should already be ordered, but be safe)
        buildings.sort(key=lambda e: e.time_s)
        activity.sort(key=lambda e: e.time_s)

        # Prefer Summary color_id (0-7 guaranteed); fall back to parse_match value
        color_id = (summary_color_ids or {}).get(p.name)
        if color_id is None:
            raw = getattr(p, "color_id", None)
            color_id = raw if (raw is not None and 0 <= raw <= 7) else 0

        players[p.number] = PlayerPositions(
            number=p.number,
            name=p.name,
            color_id=color_id,
            tc=tc,
            buildings=buildings,
            activity=activity,
        )

    return players


# ── Public API ─────────────────────────────────────────────────────────────────

def extract_positions(replay_path: str) -> ReplayPositions:
    """
    Extract all spatial data from a replay file.

    Two parse passes are made:
      1. Summary  — map tiles, duration
      2. parse_match — player inputs and gaia objects

    Args:
        replay_path: Path to the .aoe2record file.

    Returns:
        ReplayPositions instance with normalised coordinates.
    """
    # Pass 1: Summary for map tiles, duration, and reliable color_ids (0-7)
    with open(replay_path, "rb") as f:
        summary = Summary(f)
        duration_ms = summary.get_duration()
        map_layer = _build_map_layer(summary)
        summary_color_ids: dict[str, int] = {}
        try:
            for sp in summary.get_players():
                name = sp.get("name", "")
                cid  = sp.get("color_id")
                if name and cid is not None and 0 <= cid <= 7:
                    summary_color_ids[name] = cid
        except Exception:
            pass

    duration_s = int(duration_ms / 1000)
    dim = map_layer.dimension

    # Pass 2: parse_match for inputs and gaia objects
    with open(replay_path, "rb") as f:
        match = parse_match(f)

    map_layer.resources = _classify_gaia_resources(match.gaia, dim)
    players = _extract_player_positions(match, dim, summary_color_ids)

    return ReplayPositions(
        duration_s=duration_s,
        map=map_layer,
        players=players,
    )


# ── CLI for inspection ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python extract_positions.py <replay.aoe2record>")
        sys.exit(1)

    data = extract_positions(sys.argv[1])
    result = data.to_dict()

    # Print summary stats instead of full JSON (terrain array is huge)
    dim = result["map"]["dimension"]
    print(f"Duration:   {data.duration_s}s ({data.duration_s//60}m{data.duration_s%60:02d}s)")
    print(f"Map:        {dim}x{dim}, {len(result['map']['terrain'])} tiles")
    print(f"Resources:  {len(result['map']['resources'])} objects")
    for pid, p in result["players"].items():
        print(f"Player {pid} ({p['name']}): "
              f"TC=({p['tc']['x']:.3f},{p['tc']['y']:.3f}), "
              f"{len(p['buildings'])} buildings, "
              f"{len(p['activity'])} activity events")

    if "--json" in sys.argv:
        print(json.dumps(result, indent=2))
