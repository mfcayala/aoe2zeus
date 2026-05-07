"""
Explore an AoE2 DE replay file using mgz.
Usage: python explore_replay.py <path_to_replay.aoe2record>
"""
import sys
import json
import asyncio
from collections import defaultdict
from datetime import timedelta

from mgz.summary import Summary
from mgz.model import parse_match, serialize


def ms_to_ts(ms):
    return str(timedelta(milliseconds=ms)).split(".")[0]


async def explore(path: str):
    with open(path, "rb") as f:
        summary = Summary(f)

        print("=" * 60)
        print("MATCH SUMMARY")
        print("=" * 60)
        print(f"Map:       {summary.get_map()}")
        print(f"Duration:  {ms_to_ts(summary.get_duration())}")
        print(f"Version:   {summary.get_version()}")
        print(f"Dataset:   {summary.get_dataset()}")

        print("\nPLAYERS")
        print("-" * 40)
        for p in summary.get_players():
            print(f"  [{p['number']}] {p['name']} — civ: {p['civilization']} | winner: {p['winner']}")

        print("\nTEAMS")
        print("-" * 40)
        for i, team in enumerate(summary.get_teams()):
            print(f"  Team {i}: {team}")

        print("\nSETTINGS")
        print("-" * 40)
        settings = summary.get_settings()
        for k, v in settings.items():
            print(f"  {k}: {v}")

        chat = summary.get_chat()
        if chat:
            print("\nCHAT LOG")
            print("-" * 40)
            for msg in chat:
                ts = ms_to_ts(msg.get("time", 0))
                print(f"  [{ts}] {msg.get('player', '?')}: {msg.get('message', '')}")

    # Full model parse — actions, inputs, age-ups
    print("\n" + "=" * 60)
    print("ACTION STREAM (model parse)")
    print("=" * 60)
    with open(path, "rb") as f:
        match, _ = await parse_match(f)

    inputs_by_type = defaultdict(list)
    age_events = []

    for inp in match.inputs:
        inputs_by_type[inp.type].append(inp)
        if inp.type == "research":
            # Age-up research IDs: 101=Feudal, 102=Castle, 103=Imperial
            if hasattr(inp, "technology_type") and inp.technology_type in (101, 102, 103):
                age_map = {101: "Feudal", 102: "Castle", 103: "Imperial"}
                age_events.append({
                    "age": age_map[inp.technology_type],
                    "timestamp": ms_to_ts(inp.timestamp),
                    "player": inp.player_id,
                })

    print("\nInput type counts:")
    for t, items in sorted(inputs_by_type.items(), key=lambda x: -len(x[1])):
        print(f"  {t}: {len(items)}")

    if age_events:
        print("\nAGE-UP EVENTS")
        print("-" * 40)
        for e in age_events:
            print(f"  Player {e['player']} → {e['age']} Age at {e['timestamp']}")

    # Sample of first 20 inputs
    print("\nFIRST 20 INPUTS (raw)")
    print("-" * 40)
    for inp in match.inputs[:20]:
        print(f"  {ms_to_ts(inp.timestamp):>8}  type={inp.type}  player={inp.player_id}  {serialize(inp)}")

    # Show structure of inputs by type (one example each)
    print("\nONE EXAMPLE PER INPUT TYPE")
    print("-" * 40)
    seen = set()
    for inp in match.inputs:
        if inp.type not in seen:
            seen.add(inp.type)
            print(f"\n  type={inp.type}")
            print(f"  {json.dumps(serialize(inp), indent=4, default=str)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python explore_replay.py <replay.aoe2record>")
        sys.exit(1)
    asyncio.run(explore(sys.argv[1]))
