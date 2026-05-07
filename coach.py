"""
AoE2 Zeus — Coaching Report Generator
Usage: python coach.py <replay.aoe2record> [--player <name_or_number>]

Requires ANTHROPIC_API_KEY environment variable.
"""
import sys
import os
import json
import argparse
from extract_game_data import extract


# Civ knowledge — brief notes relevant to matchup coaching
CIV_NOTES = {
    "Cumans": (
        "Unique bonuses: Can build a second Town Center in Feudal Age (lets them boom fast), "
        "siege moves 10%% faster, Steppe Lancers available. Historically strong aggressive Feudal + Castle push. "
        "Key weakness: TC is exposed in Feudal (no stone walls start). "
        "Standard strategy: Fast Feudal → Men-at-Arms or Scout rush while building second TC, transition to cavalry."
    ),
    "Britons": "Strong archers (Longbowmen), cheaper Archery Ranges in Castle, extra range on foot archers. Best vs. cavalry-heavy civs.",
    "Franks": "Extra HP on cavalry, free Farm upgrades, faster Castles. Dominant Paladin civ. Strong vs. archer civs.",
    "Mayans": "El Dorado Eagle Warriors, 15%% cheaper archers, extra resources at start. Strong archer eco. Good vs. cavalry.",
    "Chinese": "Extra food at start, cheaper techs per age, archers + siege focus. Strong eco and late game.",
    "Mongols": "Mangudai, faster siege, stronger cavalry archers. Aggressive mobile play.",
    "Vikings": "Free wheelbarrow/hand cart, extra HP on infantry. Strong eco and infantry push.",
    "Ethiopians": "Free Pikemen/Elite Skirmisher upgrades when aging up, archer bonus. Good defensive eco.",
    "Malians": "Infantry +1 attack per age, faster building. Gbeto unique unit. Infantry rush civ.",
    "Teutons": "Strongest Paladins/Teutonic Knights, farms cheaper, conversion resistance. Slow but powerful.",
    "Aztecs": "Garrisoned units generate gold, military units +5 HP. Eagle Warriors. Strong eco+rush.",
    "Persians": "TC and docks work faster, war elephants. Fast boom, strong Castle Age.",
}


def format_game_data_for_prompt(data: dict, focus_player_id: int) -> str:
    """Format extracted game data into a prompt-friendly text block."""
    opponent_id = 1 if focus_player_id == 2 else 2

    focus = data["players"][str(focus_player_id)]
    opponent = data["players"][str(opponent_id)]
    focus_cd = data["coaching_data"][str(focus_player_id)]
    opp_cd = data["coaching_data"][str(opponent_id)]

    focus_civ = focus["civ"] if not str(focus["civ"]).startswith("civ_") else "Unknown (random pick)"
    opp_civ = opponent["civ"] if not str(opponent["civ"]).startswith("civ_") else "Unknown (random pick)"

    civ_context = ""
    for civ in [focus_civ, opp_civ]:
        if civ in CIV_NOTES:
            civ_context += f"\n  {civ}: {CIV_NOTES[civ]}"

    lines = []
    lines.append(f"=== GAME SUMMARY ===")
    lines.append(f"Map: {data['map']['name']} ({data['map']['size']})")
    lines.append(f"Duration: {data['duration']}")
    lines.append(f"")
    lines.append(f"FOCUS PLAYER: {focus['name']}")
    lines.append(f"  Civilization: {focus_civ}")
    lines.append(f"  Result: {'WIN' if focus['winner'] else 'LOSS'}")
    lines.append(f"  eAPM: {focus['eapm']}")
    lines.append(f"")
    lines.append(f"OPPONENT: {opponent['name']}")
    lines.append(f"  Civilization: {opp_civ}")
    lines.append(f"  Result: {'WIN' if opponent['winner'] else 'LOSS'}")
    lines.append(f"  eAPM: {opponent['eapm']}")

    if civ_context:
        lines.append(f"")
        lines.append(f"CIV MATCHUP CONTEXT:{civ_context}")

    lines.append(f"")
    lines.append(f"=== AGE-UP TIMELINE ===")
    for e in data["uptime_events"]:
        tag = "(YOU)" if e["player"] == focus["name"] else "(OPP)"
        age = e["age"].replace("Age.", "").replace("_", " ").title()
        lines.append(f"  {e['time']}  {e['player']} {tag} → {age}")

    # Age-up clicks (when they pressed the button, before completion)
    lines.append(f"")
    lines.append(f"Age-up button clicks (your replay data):")
    for rd in [
        (focus["name"], focus_cd["age_times"]),
        (opponent["name"], opp_cd["age_times"]),
    ]:
        name, ages = rd
        tag = "(YOU)" if name == focus["name"] else "(OPP)"
        for age, t in ages.items():
            lines.append(f"  {t}  {name} {tag} clicked {age}")

    lines.append(f"")
    lines.append(f"=== YOUR ECONOMY ===")
    lines.append(f"Villagers queued: {focus_cd['villagers_queued']}")
    lines.append(f"TC idle time: {focus_cd['tc_idle_total_s']}s total")
    if focus_cd["tc_idle_periods"]:
        lines.append(f"TC idle periods:")
        for p in focus_cd["tc_idle_periods"]:
            lines.append(f"  {p['start']} – {p['end']} ({p['duration_s']}s)")

    lines.append(f"")
    lines.append(f"Your research timeline:")
    for r in focus_cd["research_timeline"]:
        lines.append(f"  {r['time']}  {r['tech']}")

    lines.append(f"")
    lines.append(f"Your build order:")
    for b in focus_cd["build_order"]:
        lines.append(f"  {b['time']}  {b['building']}")

    lines.append(f"")
    lines.append(f"Your military production:")
    if focus_cd["military_production"]:
        for m in focus_cd["military_production"]:
            lines.append(f"  {m['time']}  {m['unit']}")
    else:
        lines.append(f"  (none recorded — no military units queued)")

    lines.append(f"")
    lines.append(f"Boar lures executed: {len(focus_cd['boar_lures'])}")
    if focus_cd["boar_lures"]:
        # Deduplicate by target_id and show first contact
        seen = {}
        for lure in focus_cd["boar_lures"]:
            tid = lure["target_id"]
            if tid not in seen:
                seen[tid] = lure["time"]
        for tid, t in seen.items():
            lines.append(f"  Boar #{tid} first targeted at {t}")

    lines.append(f"")
    lines.append(f"=== OPPONENT'S PLAY ===")
    lines.append(f"Opponent research timeline:")
    for r in opp_cd["research_timeline"]:
        lines.append(f"  {r['time']}  {r['tech']}")
    lines.append(f"Opponent villagers queued: {opp_cd['villagers_queued']}")
    lines.append(f"Opponent TC idle: {opp_cd['tc_idle_total_s']}s")
    lines.append(f"Opponent military production:")
    if opp_cd["military_production"]:
        for m in opp_cd["military_production"]:
            lines.append(f"  {m['time']}  {m['unit']}")
    else:
        lines.append(f"  (none recorded)")

    lines.append(f"")
    lines.append(f"=== RESOURCE ECONOMY SNAPSHOTS (per minute) ===")
    lines.append(f"(total_res = combined food+wood+gold+stone, obj_count ≈ total entities including buildings/units)")
    lines.append(f"{'Time':<6}  {'Your total_res':>14}  {'Opp total_res':>13}  {'Your obj_count':>14}  {'Opp obj_count':>13}")
    focus_eco = {e["time"]: e for e in data["economy_timeline"].get(str(focus_player_id), [])}
    opp_eco = {e["time"]: e for e in data["economy_timeline"].get(str(opponent_id), [])}
    all_times = sorted(set(focus_eco) | set(opp_eco))
    for t in all_times:
        f = focus_eco.get(t, {})
        o = opp_eco.get(t, {})
        lines.append(
            f"{t:<6}  {f.get('total_res', '-'):>14}  {o.get('total_res', '-'):>13}  "
            f"{f.get('obj_count', '-'):>14}  {o.get('obj_count', '-'):>13}"
        )

    return "\n".join(lines)


COACHING_SYSTEM_PROMPT = """You are an expert Age of Empires II coaching assistant with deep knowledge of:
- AoE2 DE mechanics, build orders, and civ-specific strategies
- Macro economy fundamentals: TC idle time, villager allocation, resource priorities
- Competitive meta at intermediate (800–1200 ELO) level
- Map-specific strategies (Arena, Arabia, etc.)

You will receive structured data extracted from an AoE2 DE replay file. Your job is to produce a clear, actionable coaching report for the specified player.

Structure your report as follows:

## The Decisive Moment
Identify the single key moment or inflection point where the game was effectively decided. Be specific: name the timestamp, what happened, and why it was fatal.

## What You Should Have Done In That Moment
Concrete, actionable advice for that specific situation. What units/buildings/techs should they have had ready? What decision would have changed the outcome?

## What Led You There — Macro Strategy Gaps
Walk through the earlier part of the game and identify the 3–5 most impactful macro mistakes (TC idle, wrong age-up timing, missing military production, misallocated villagers, missing key techs). Use timestamps from the data.

## Civ Matchup Exploitation
Given the civs in play, explain what advantages the opponent had that they exploited, what advantages the focus player had that they DIDN'T exploit, and what the correct strategy for this matchup looks like on this map.

## Top 3 Action Items for Next Game
Three specific, measurable things the player should focus on in their next game. Make them concrete (e.g., "Queue a villager within 10 seconds of each one finishing" not "improve eco").

Be direct and specific. Use the timestamps from the data. Don't be vague. This player wants to improve."""


def generate_coaching_report(game_data: dict, focus_player_id: int) -> str:
    """Call Anthropic API to generate coaching report."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable not set. "
            "Get your key at https://console.anthropic.com and run:\n"
            "  export ANTHROPIC_API_KEY=your-key-here"
        )

    client = anthropic.Anthropic(api_key=api_key)
    game_text = format_game_data_for_prompt(game_data, focus_player_id)

    focus_name = game_data["players"][str(focus_player_id)]["name"]
    user_message = (
        f"Please analyze this AoE2 DE replay and provide a coaching report for player: {focus_name}\n\n"
        f"{game_text}"
    )

    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2000,
        system=COACHING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    return message.content[0].text


def main():
    parser = argparse.ArgumentParser(description="AoE2 Zeus — Coaching Report Generator")
    parser.add_argument("replay", help="Path to .aoe2record file")
    parser.add_argument(
        "--player",
        default=None,
        help="Player name or number to focus on (default: loser)",
    )
    parser.add_argument(
        "--dump-data",
        action="store_true",
        help="Dump extracted game data as JSON and exit (no API call)",
    )
    args = parser.parse_args()

    print(f"Extracting replay data from: {args.replay}")
    game_data = extract(args.replay)

    if args.dump_data:
        print(json.dumps(game_data, indent=2, default=str))
        return

    # Determine focus player
    focus_player_id = None
    if args.player is not None:
        if args.player.isdigit():
            focus_player_id = int(args.player)
        else:
            for pid, p in game_data["players"].items():
                if args.player.lower() in p["name"].lower():
                    focus_player_id = int(pid)
                    break
        if focus_player_id is None:
            print(f"Player '{args.player}' not found. Available: {[p['name'] for p in game_data['players'].values()]}")
            sys.exit(1)
    else:
        # Default: the loser
        for pid, p in game_data["players"].items():
            if not p["winner"]:
                focus_player_id = int(pid)
                break
        if focus_player_id is None:
            focus_player_id = 1

    focus_name = game_data["players"][str(focus_player_id)]["name"]
    print(f"Generating coaching report for: {focus_name}\n")

    report = generate_coaching_report(game_data, focus_player_id)
    print(report)


if __name__ == "__main__":
    main()
