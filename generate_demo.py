"""
generate_demo.py — Create a demo HTML report with mock data for UI preview.
Usage: python generate_demo.py
Outputs: demo_report.html
"""
import json
import math
import random
from pathlib import Path

from extract_positions import (
    ReplayPositions, MapLayer, PlayerPositions,
    Point, BuildEvent, ActivityEvent,
)
from report_html import generate_html_report

# ── Mock game data ─────────────────────────────────────────────────────────────

random.seed(42)
DIM = 120

MOCK_GAME_DATA = {
    "map": {"name": "Arena", "size": "120×120"},
    "duration": "26:01",
    "players": {
        "1": {"name": "marcoghersii", "civ": "Cumans",   "winner": True,  "eapm": 78},
        "2": {"name": "miguel.f.c.ayala", "civ": "Franks", "winner": False, "eapm": 52},
    },
    "uptime_events": [
        {"time": "8:33",  "player": "marcoghersii",     "age": "Age.FEUDAL_AGE"},
        {"time": "11:02", "player": "miguel.f.c.ayala", "age": "Age.FEUDAL_AGE"},
        {"time": "13:10", "player": "marcoghersii",     "age": "Age.CASTLE_AGE"},
        {"time": "16:54", "player": "miguel.f.c.ayala", "age": "Age.CASTLE_AGE"},
    ],
    "coaching_data": {
        "1": {
            "age_times": {"Feudal": "7:55", "Castle": "12:40"},
            "villagers_queued": 42,
            "tc_idle_total_s": 18,
            "tc_idle_periods": [
                {"start": "4:10", "end": "4:38", "duration_s": 28},
            ],
            "research_timeline": [
                {"time": "4:17", "tech": "Loom"},
                {"time": "7:55", "tech": "Feudal Age"},
                {"time": "9:10", "tech": "Double-Bit Axe"},
                {"time": "10:05", "tech": "Bow Saw"},
                {"time": "12:40", "tech": "Castle Age"},
                {"time": "14:20", "tech": "Man-at-Arms"},
            ],
            "build_order": [
                {"time": "1:30", "building": "Lumber Camp"},
                {"time": "2:45", "building": "Mill"},
                {"time": "4:00", "building": "Barracks"},
                {"time": "7:55", "building": "Blacksmith"},
                {"time": "8:40", "building": "Stable"},
                {"time": "12:40", "building": "Castle"},
            ],
            "military_production": [
                {"time": "12:00", "unit": "Man-at-Arms"},
                {"time": "12:30", "unit": "Man-at-Arms"},
                {"time": "13:00", "unit": "Man-at-Arms"},
                {"time": "13:30", "unit": "Knight"},
            ],
            "boar_lures": [
                {"time": "3:45", "target_id": 101},
                {"time": "5:10", "target_id": 102},
            ],
        },
        "2": {
            "age_times": {"Feudal": "10:22", "Castle": "16:10"},
            "villagers_queued": 34,
            "tc_idle_total_s": 147,
            "tc_idle_periods": [
                {"start": "6:00",  "end": "7:30",  "duration_s": 90},
                {"start": "12:00", "end": "12:57", "duration_s": 57},
            ],
            "research_timeline": [
                {"time": "4:17", "tech": "Loom"},
                {"time": "10:22", "tech": "Feudal Age"},
                {"time": "11:40", "tech": "Double-Bit Axe"},
                {"time": "16:10", "tech": "Castle Age"},
            ],
            "build_order": [
                {"time": "2:00", "building": "Lumber Camp"},
                {"time": "3:30", "building": "Mill"},
                {"time": "5:00", "building": "Barracks"},
                {"time": "10:22", "building": "Blacksmith"},
                {"time": "14:30", "building": "Monastery"},
            ],
            "military_production": [
                {"time": "14:00", "unit": "Crossbowman"},
                {"time": "14:45", "unit": "Crossbowman"},
            ],
            "boar_lures": [
                {"time": "4:20", "target_id": 201},
            ],
        },
    },
    "economy_timeline": {
        "1": [
            {"time": f"{m:02d}:00", "total_res": int(200 + m * 120 + random.gauss(0, 30)), "obj_count": 20 + m * 2}
            for m in range(1, 27)
        ],
        "2": [
            {"time": f"{m:02d}:00", "total_res": int(180 + m * 90 + random.gauss(0, 30)), "obj_count": 18 + m * 2}
            for m in range(1, 27)
        ],
    },
}

MOCK_COACHING_TEXT = """## The Decisive Moment

At **13:59**, marcoghersii's Men-at-Arms crossed your outer wall through the east gate — you had left it open after the last villager run. You had 0 military units available to defend. Your Town Centre was idle at this exact moment (TC had been idle since 12:57). This was the point of no return: without any military production and a Castle still 3 minutes away, you could not recover from a 6-unit Man-at-Arms push on Arena.

## What You Should Have Done At That Moment

At **12:00** — two minutes earlier — you should have queued Spearmen from the Barracks you already had. Spearmen do not counter Man-at-Arms (infantry), but they buy time. The real answer: **at 11:00** you needed to start Crossbowmen production. Franks with Cross + Arbalest kite MAA effectively and you had the Archery Range resources. At 13:59 the correct response was to wall the inner courtyard and age up to Castle Age immediately to unlock Knight production.

## What Led You There — Macro Gaps

- **6:00 – 7:30** (90s TC idle): You stopped queueing villagers while building your Lumber Camp expansion. A 90-second gap here cost you roughly 4 villagers — that is ~120 resources per minute in lost gather rate by mid-game.
- **10:22** Feudal Age: You reached Feudal 2:29 behind marcoghersii. On Arena the gate delay means you are safe, but 2½ minutes of Feudal economy advantage is significant — you should be aiming for **sub-10:00 Feudal** from Arena starts.
- **11:40** Double-Bit Axe: Researched 1:20 after reaching Feudal. This should be your **first** Feudal tech — queue it the moment you click up.
- **12:00 – 12:57** (57s TC idle): Another idle gap just as the midgame pressure window opened. You had 400 food banked at this point; there was no reason to stop villager production.
- **No military before 14:00**: You built a Barracks at 5:00 but queued zero military units until 14:00. Even 2–3 Spearmen as a deterrent would have forced marcoghersii to scout rather than commit immediately.

## Civ Matchup — What You Left Exploited

**marcoghersii (Cumans)** used their Feudal Age Stable bonus — Cumans can build Stables and produce cavalry one age earlier than standard. This is what enabled the 13:59 push: he had Stables running in Feudal. You should have scouted this at **9:00** and adjusted to Skirmishers + Spearmen rather than pure boom.

**You (Franks)** left your entire cavalry bonus unused. Franks get +20% HP on Knights and cheaper Stables — you built zero cavalry. On Arena vs. a cavalry-heavy civ, a Castle Age Knight push at **15:00** with 4–5 Knights would have won the game; Cumans have no Halberdier and their foot soldiers cannot match Frankish Knights. Your monastery at 14:30 was entirely the wrong priority.

The correct Arena strategy for Franks vs. Cumans: **full boom to Castle Age → 3 Knights → pressure**. You had the eco to do this if not for the TC idle gaps.

## Top 3 Things To Fix Next Game

1. **Never let TC sit idle more than 5 seconds**: Set a mental timer. The moment you finish a build command, queue a villager. Your TC was idle 147s this game — that is 6 free villagers you never got.
2. **Research Double-Bit Axe within 30 seconds of reaching Feudal Age**: It is almost always your highest-value first Feudal tech. Write it into muscle memory: click Feudal → immediately queue Double-Bit Axe in the Lumber Camp.
3. **Scout for military buildings at 8:00–10:00**: Check your opponent's base for Stables or Barracks activity. If you see Stable + Blacksmith, start Skirmisher production immediately — do not wait for the push to tell you what's coming.
"""


# ── Mock position data ─────────────────────────────────────────────────────────

def _make_arena_terrain(dim: int) -> tuple[list[int], list[int]]:
    """Generate a convincing Arena-style terrain grid."""
    terrain   = [0] * (dim * dim)
    elevation = [0] * (dim * dim)
    cx, cy = dim // 2, dim // 2
    wall_r = int(dim * 0.38)
    stone_r = int(dim * 0.34)

    for y in range(dim):
        for x in range(dim):
            dx, dy = x - cx, y - cy
            d = math.sqrt(dx * dx + dy * dy)
            idx = y * dim + x

            if d > wall_r:
                terrain[idx] = 18    # outer grass (Arena)
            elif d > stone_r:
                terrain[idx] = 113   # stone wall / transition
            else:
                terrain[idx] = 113   # inner cobblestone
                # inner courtyard: gentle elevation bump
                elevation[idx] = max(0, int(3 - d / 10))

            # Add noise
            if random.random() < 0.04:
                elevation[idx] = min(7, elevation[idx] + 1)

    return terrain, elevation


def _make_resources(dim: int) -> list[dict]:
    """Scatter gold/stone/trees around the map."""
    res = []
    cx, cy = dim / 2, dim / 2

    def norm(v): return round(v / dim, 4)

    # Gold piles (4 per player corner)
    for base_x, base_y in [(25, 25), (95, 95)]:
        for _ in range(4):
            x = base_x + random.randint(-6, 6)
            y = base_y + random.randint(-6, 6)
            res.append({"type": "gold", "x": norm(x), "y": norm(y)})

    # Stone piles
    for base_x, base_y in [(25, 95), (95, 25)]:
        for _ in range(3):
            x = base_x + random.randint(-5, 5)
            y = base_y + random.randint(-5, 5)
            res.append({"type": "stone", "x": norm(x), "y": norm(y)})

    # Trees around outer ring
    wall_r = dim * 0.38
    for _ in range(80):
        angle = random.uniform(0, 2 * math.pi)
        d = random.uniform(wall_r + 2, dim * 0.49)
        x = cx + d * math.cos(angle)
        y = cy + d * math.sin(angle)
        if 2 < x < dim - 2 and 2 < y < dim - 2:
            res.append({"type": "tree", "x": norm(x), "y": norm(y)})

    # Deer + boar near TCs
    for base_x, base_y in [(22, 22), (98, 98)]:
        for _ in range(3):
            res.append({"type": "hunt", "x": norm(base_x + random.randint(-5, 5)),
                        "y": norm(base_y + random.randint(-5, 5))})
        res.append({"type": "boar", "x": norm(base_x + 8), "y": norm(base_y)})

    return res


def _make_player(number: int, name: str, color_id: int,
                 tc_x: float, tc_y: float, duration_s: int) -> PlayerPositions:
    dim = DIM

    building_data = [
        (90,  "Lumber Camp"),
        (165, "Mill"),
        (240, "Barracks"),
        (480, "Blacksmith"),
        (540, "Stable"),
        (794, "Castle"),
    ] if number == 1 else [
        (120, "Lumber Camp"),
        (210, "Mill"),
        (300, "Barracks"),
        (622, "Blacksmith"),
        (870, "Monastery"),
    ]

    # Scatter buildings near TC
    rng = random.Random(number * 999)
    buildings = []
    for t, bname in building_data:
        bx = tc_x + rng.uniform(-0.08, 0.08)
        by = tc_y + rng.uniform(-0.08, 0.08)
        bx = max(0.02, min(0.98, bx))
        by = max(0.02, min(0.98, by))
        buildings.append(BuildEvent(time_s=t, building=bname, pos=Point(bx, by)))

    # Activity trail: mostly near TC, then expanding in late game
    activity = []
    t = 0
    ax, ay = tc_x, tc_y
    while t < duration_s:
        t += 5
        # Wander with drift toward center in late game
        progress = t / duration_s
        target_x = 0.5 if progress > 0.6 else tc_x
        target_y = 0.5 if progress > 0.6 else tc_y
        ax += (target_x - ax) * 0.05 + rng.gauss(0, 0.025)
        ay += (target_y - ay) * 0.05 + rng.gauss(0, 0.025)
        ax = max(0.05, min(0.95, ax))
        ay = max(0.05, min(0.95, ay))
        action = rng.choice(["Move", "Move", "Move", "Target", "Patrol"])
        activity.append(ActivityEvent(time_s=t, action=action, pos=Point(round(ax, 4), round(ay, 4))))

    return PlayerPositions(
        number=number,
        name=name,
        color_id=color_id,
        tc=Point(tc_x, tc_y),
        buildings=buildings,
        activity=activity,
    )


def build_mock_position_data() -> ReplayPositions:
    terrain, elevation = _make_arena_terrain(DIM)
    resources = _make_resources(DIM)

    map_layer = MapLayer(
        dimension=DIM,
        terrain=terrain,
        elevation=elevation,
        resources=resources,
    )

    duration_s = 26 * 60 + 1

    p1 = _make_player(1, "marcoghersii",     0, tc_x=0.20, tc_y=0.20, duration_s=duration_s)
    p2 = _make_player(2, "miguel.f.c.ayala", 1, tc_x=0.80, tc_y=0.80, duration_s=duration_s)

    return ReplayPositions(
        duration_s=duration_s,
        map=map_layer,
        players={1: p1, 2: p2},
    )


# ── Generate ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Building mock position data…")
    position_data = build_mock_position_data()

    print("Rendering HTML report…")
    html = generate_html_report(
        game_data=MOCK_GAME_DATA,
        focus_player_id=2,
        coaching_text=MOCK_COACHING_TEXT,
        position_data=position_data,
    )

    out = Path(__file__).parent / "demo_report.html"
    out.write_text(html, encoding="utf-8")
    print(f"Done → {out}  ({len(html):,} bytes)")
