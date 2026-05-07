"""
generate_data.py — Export replay data as JSON for the React frontend.

Usage: python generate_data.py [replay.aoe2record]

Defaults to the MP replay in the same directory.
Outputs: frontend/public/data.json
"""
import base64
import json
import sys
from pathlib import Path

from extract_game_data import extract
from extract_positions import extract_positions

_DEFAULT_REPLAY = (
    Path(__file__).parent
    / "MP Replay v101.103.39862.0 @2026.04.18 144432 (2).aoe2record"
)

COACHING_TEXT = """## The Decisive Moment

At **13:59**, marcoghersii completed **Man-at-Arms** — the upgrade that turned his 5 Militia into a killing machine. At this moment you had **zero military units** and your Town Centre had just come off an idle gap. You were still two full minutes from Castle Age. He had been building Militia since **10:01** and queuing them steadily while you were booming with no military production plan whatsoever. This is the moment the game ended: you had no answer to a fully-upgraded Man-at-Arms push with nothing in your base to defend.

## What You Should Have Done At That Moment

At **11:00** — immediately after reaching Feudal Age — you needed a **Barracks and Skirmisher production**. You never built a Barracks at all. Even 3–4 Skirmishers parked at your wall would force marcoghersii to think twice about pushing. The correct response once you saw him building a Siege Workshop at **11:59** and Barracks at **08:41** was to either:
- Build Skirmishers to hold the wall while you rushed Castle Age
- Or rush your own Castle Age faster — you clicked it at **15:00**, which was **4 minutes** after his Man-at-Arms upgrade finished

The window to win was **11:00–13:00**: wall more tightly, get ranged units, and click Castle Age before he can commit.

## What Led You There — Macro Gaps

- **Villager gap**: You queued only **22 villagers** vs marcoghersii's 35. That is a 37% deficit in eco units — the single biggest factor in the game. You effectively played the whole game with a third fewer workers.
- **03:53 – 04:54** (61s TC idle): Your longest idle gap in the opening. You stopped queueing villagers right after building your Lumber Camp. A 61-second gap in dark age costs roughly 2 villagers.
- **11:02** Feudal Age: You reached Feudal 2:29 behind marcoghersii. On Arena the walls give you safety, but he was already 2+ minutes into Feudal economy advantages while you were still in Dark Age.
- **No military buildings ever**: You built zero Barracks, zero Archery Ranges, zero Stables before Castle Age. Your first and only military unit was a **Battering Ram at 25:22** — 11 minutes after marcoghersii's Man-at-Arms push. This is the core problem.
- **09:29 – 09:58** (29s idle): Another idle gap right as you were approaching the Feudal Age click.

## Civ Matchup — What You Left Exploited

**marcoghersii (Cumans)** get free Feudal Age Stables and faster-moving cavalry. He used this to build a Siege Workshop at **11:59** and unlock rams — the perfect Arena tool for breaking your walls. His Militia → Man-at-Arms timing at **13:59** is a classic Feudal Age timing attack on Arena.

**You (Franks)** have arguably the best Knight rush in the game: +20% HP on Knights, cheaper Stable upgrades, and free Farm upgrades. You built a Castle at **20:34** — way too late, and only after you'd already resigned to losing. Your Castle Age Knight push should have landed at **17:00–18:00** with 4–5 knights, which Cumans cannot match in a straight fight (no Halberdier access until very late, and their cavalry don't beat Frankish Knights head-to-head).

The correct strategy for **Franks vs Cumans on Arena**: full boom to Castle Age → double Stable → 4–5 Knights at the wall. You had the civilization to do this. You needed to hold with walls + 3 Skirmishers in Feudal while out-booming him, then overwhelm with Frankish cavalry in Castle Age.

## Top 3 Things To Fix Next Game

1. **Queue a villager every 25 seconds — no exceptions**: You queued 22 villagers this game. Your opponent queued 35. Set a rule: finish any action → immediately check TC queue. Your TC should never show 0 population being trained unless you are actively clicking up to the next age.
2. **Build a Barracks before reaching Feudal Age**: On Arena you are safe behind walls, but you still need *something* to defend. A single Barracks built at minute 7–8 gives you the option to queue 3 Skirmishers as insurance. You had zero military buildings for the entire first 20 minutes.
3. **Click Castle Age by 14:00 on Arena as Franks**: Your Feudal Age should be spent booming and walling, not fighting. Get to Castle Age fast (aim for 14:00 max), then unleash Knights. You clicked Castle at **15:00** and it completed at **16:54** — 3 minutes after Man-at-Arms was already upgraded.
"""


def _b64(arr: list[int]) -> str:
    return base64.b64encode(bytes(arr)).decode("ascii")


def build_json(replay_path: str) -> dict:
    print(f"Extracting game data…")
    game_data = extract(replay_path)

    print("Extracting position data…")
    pos = extract_positions(replay_path)
    dim = pos.map.dimension

    minimap = {
        "dim":          dim,
        "terrain_b64":  _b64(pos.map.terrain),
        "elevation_b64": _b64(pos.map.elevation),
        "resources":    pos.map.resources,
        "duration_s":   pos.duration_s,
        "players": {
            str(k): {
                "name":      v.name,
                "color_id":  v.color_id,
                "tc":        v.tc.to_dict(),
                "buildings": [b.to_dict() for b in v.buildings],
                "activity":  [a.to_dict() for a in v.activity],
            }
            for k, v in pos.players.items()
        },
    }

    return {
        "game":     game_data,
        "coaching": COACHING_TEXT,
        "minimap":  minimap,
    }


if __name__ == "__main__":
    replay = sys.argv[1] if len(sys.argv) > 1 else str(_DEFAULT_REPLAY)
    data = build_json(replay)

    out_dir = Path(__file__).parent / "frontend" / "public"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), default=str)

    size_kb = out_path.stat().st_size / 1024
    print(f"Done → {out_path}  ({size_kb:.0f} KB)")
    print(f"  Map: {data['minimap']['dim']}×{data['minimap']['dim']}, "
          f"{len(data['minimap']['resources'])} resources")
    for pid, p in data["minimap"]["players"].items():
        print(f"  P{pid} {p['name']}: {len(p['buildings'])} buildings, "
              f"{len(p['activity'])} activity pts")
