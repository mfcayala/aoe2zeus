"""
AoE2 Zeus — Coaching Report Generator
Usage: python coach.py <replay.aoe2record> [--player <name_or_number>]

Requires ANTHROPIC_API_KEY environment variable.
"""
import sys
import os
import json
import argparse
from pathlib import Path
from extract_game_data import extract
from report_html import generate_html_report

_DATA_DIR = Path(__file__).parent
_CIV_BONUSES_PATH = _DATA_DIR / "civ_bonuses.json"

def _load_civ_bonuses() -> dict:
    if _CIV_BONUSES_PATH.exists():
        with open(_CIV_BONUSES_PATH) as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    return {}

CIV_BONUSES = _load_civ_bonuses()


def _civ_context_block(civ_name: str) -> str:
    """Return a compact civ summary for the prompt."""
    if civ_name.startswith("civ_") or civ_name == "Unknown":
        return "Unknown civilization — cannot provide matchup-specific advice."
    data = CIV_BONUSES.get(civ_name)
    if not data:
        return f"{civ_name}: No data available in civ_bonuses.json — verify manually."
    needs_verify = any("Verify" in str(v) for v in data.get("bonuses", []))
    warn = " ⚠ DATA MAY BE STALE — verify bonuses against current patch." if needs_verify else ""
    lines = [f"{civ_name}:{warn}", f"  Style: {data.get('style', '?')}"]
    for b in data.get("bonuses", [])[:4]:
        lines.append(f"  • {b}")
    lines.append(f"  Unique unit: {data.get('unique_unit', '?')}")
    lines.append(f"  Key missing techs: {', '.join(data.get('missing_notable', [])[:4]) or 'none noted'}")
    if data.get("arena_strategy"):
        lines.append(f"  Arena strategy: {data['arena_strategy']}")
    return "\n".join(lines)


def format_game_data_for_prompt(data: dict, focus_player_id: int) -> str:
    """Format extracted game data into a prompt-friendly text block."""
    opponent_id = 1 if focus_player_id == 2 else 2

    focus = data["players"][str(focus_player_id)]
    opponent = data["players"][str(opponent_id)]
    focus_cd = data["coaching_data"][str(focus_player_id)]
    opp_cd = data["coaching_data"][str(opponent_id)]

    focus_civ = focus["civ"] if not str(focus["civ"]).startswith("civ_") else "Unknown"
    opp_civ = opponent["civ"] if not str(opponent["civ"]).startswith("civ_") else "Unknown"

    civ_context = (
        _civ_context_block(focus_civ) + "\n\n" + _civ_context_block(opp_civ)
    )
    # Per-matchup note if available
    focus_data = CIV_BONUSES.get(focus_civ, {})
    opp_data = CIV_BONUSES.get(opp_civ, {})
    matchup_note = focus_data.get(f"vs_{opp_civ.lower()}_note") or opp_data.get(f"vs_{focus_civ.lower()}_note", "")

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

    lines.append(f"")
    lines.append(f"=== CIV MATCHUP CONTEXT ===")
    lines.append(f"⚠ Civ data may be stale — patch notes should be verified.")
    lines.append(civ_context)
    if matchup_note:
        lines.append(f"Specific matchup note: {matchup_note}")

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


COACHING_SYSTEM_PROMPT = """You are an expert Age of Empires II Definitive Edition coaching assistant.

CRITICAL RULES — follow these exactly:
1. Unit counters: Spearmen/Pikemen counter CAVALRY (horses) only — NOT infantry. Men-at-Arms (infantry) are countered by Crossbowmen/Arbalests (ranged kiting) or equal/superior numbers of your own MAA. Never suggest Spearmen vs. MAA.
2. The civ data provided may be stale (game is actively patched). Flag any advice that depends on specific numbers (e.g., HP values, costs) as "verify against current patch."
3. Use only the timestamps and events from the provided replay data — do not invent events.
4. Arena-specific: both players start with pre-built stone walls. The map favors booming but Battering Rams can break walls if timed correctly.

You will receive structured replay data. Produce a coaching report with exactly these sections:

## The Decisive Moment
The single inflection point where the game was effectively decided. Exact timestamp, what happened, why it was fatal.

## What You Should Have Done At That Moment
Concrete advice: specific units, buildings, or techs. What decision reverses the outcome.

## What Led You There — Macro Gaps
3–5 macro mistakes in chronological order, each with timestamp from the data. TC idle, age-up timing, missing production, wrong tech priority.

## Civ Matchup — What You Left Exploited
What advantages the opponent's civ had and used. What YOUR civ's advantages were that went unused. What the correct strategy for this matchup on this map looks like.

## Top 3 Things To Fix Next Game
Specific and measurable. Not "improve eco" — instead "queue a villager every 25 seconds; your TC should never sit idle more than 5 seconds."

Be direct. Use exact timestamps from the data. This player wants to improve, not be coddled."""


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

    # Write self-contained HTML report alongside the replay file
    replay_path = Path(args.replay)
    html_path = replay_path.with_suffix(".html")
    html_content = generate_html_report(game_data, focus_player_id, report)
    html_path.write_text(html_content, encoding="utf-8")
    print(f"\nHTML report saved: {html_path}")


if __name__ == "__main__":
    main()
