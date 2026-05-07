"""
Extract structured coaching data from an AoE2 DE replay file.
Returns a dict with all relevant macro/micro signals for the coaching LLM.
"""
from datetime import timedelta
from collections import defaultdict

from mgz import fast
from mgz.fast.header import parse as fast_parse
from mgz.model import parse_match, serialize
from mgz.summary import Summary


BOAR_NAMES = {"Pig", "Rhinoceros", "Wild Boar", "Javelina"}
HUNT_NAMES = {"Deer", "Ostrich", "Zebra", "Elephant"}
GATHER_NAMES = {"Forage Bush", "Fruit Bush"}
GOLD_NAMES = {"Gold Mine"}
STONE_NAMES = {"Stone Mine"}
TREE_CLASS = 70  # class_id for trees

RESOURCE_CATEGORY = {}
for n in BOAR_NAMES:   RESOURCE_CATEGORY[n] = "boar"
for n in HUNT_NAMES:   RESOURCE_CATEGORY[n] = "hunt"
for n in GATHER_NAMES: RESOURCE_CATEGORY[n] = "berries"
for n in GOLD_NAMES:   RESOURCE_CATEGORY[n] = "gold"
for n in STONE_NAMES:  RESOURCE_CATEGORY[n] = "stone"


def ts(td):
    """Format timedelta as MM:SS."""
    total_s = int(td.total_seconds())
    return f"{total_s // 60:02d}:{total_s % 60:02d}"


def compute_tc_idle(queue_actions, vill_train_time_s=25):
    """
    Compute TC idle time from villager queue timestamps.
    Models TC queue: each villager takes 25s. Gap between when queue empties
    and when next villager is queued = idle time.
    """
    vill_queues = sorted(
        [a for a in queue_actions if a.payload.get("unit") == "Villager"],
        key=lambda a: a.timestamp
    )

    idle_periods = []
    queue_empty_at = timedelta(0)

    for q in vill_queues:
        t = q.timestamp
        if t > queue_empty_at:
            # TC was idle between queue_empty_at and t
            idle_s = (t - queue_empty_at).total_seconds()
            if idle_s > 2:  # ignore tiny sub-2s gaps (rounding)
                idle_periods.append({
                    "start": ts(queue_empty_at),
                    "end": ts(t),
                    "duration_s": round(idle_s),
                })
            queue_empty_at = t + timedelta(seconds=vill_train_time_s)
        else:
            # Queue not empty yet; this vill starts after current queue drains
            queue_empty_at += timedelta(seconds=vill_train_time_s)

    return idle_periods


def get_resource_type(target_id, gaia_map):
    obj = gaia_map.get(target_id)
    if obj is None:
        return None
    if obj.name in RESOURCE_CATEGORY:
        return RESOURCE_CATEGORY[obj.name]
    if obj.class_id == TREE_CLASS:
        return "wood"
    return None


def extract(replay_path: str) -> dict:
    # ── Summary pass ──────────────────────────────────────────────────────────
    with open(replay_path, "rb") as f:
        summary = Summary(f)
        map_info = summary.get_map()
        players_summary = summary.get_players()
        duration_td = timedelta(milliseconds=summary.get_duration())

    # ── Model parse ───────────────────────────────────────────────────────────
    with open(replay_path, "rb") as f:
        match = parse_match(f)

    gaia_map = {obj.instance_id: obj for obj in match.gaia}

    # ── Player info ───────────────────────────────────────────────────────────
    players = {}
    for p in match.players:
        # resolve actual civ from player objects if civ_id=0 (random)
        civ_name = p.civilization
        if civ_name.startswith("civ_"):
            # try to find from summary
            for ps in players_summary:
                if ps["number"] == p.number:
                    civ_name = ps.get("civilization", civ_name)
                    break
        players[p.number] = {
            "name": p.name,
            "civ": civ_name,
            "winner": getattr(p, "winner", None),
            "eapm": getattr(p, "eapm", None),
            "tc_position": (round(p.position.x), round(p.position.y)) if p.position else None,
        }

    # ── Categorize all inputs by player ───────────────────────────────────────
    inputs_by_player = defaultdict(list)
    for inp in match.inputs:
        player = getattr(inp, "player", None)
        if player:
            inputs_by_player[player.number].append(inp)

    # ── Build per-player coaching data ────────────────────────────────────────
    coaching_data = {}

    for pid, player_info in players.items():
        inputs = inputs_by_player[pid]

        # -- Research timeline
        research_events = []
        for inp in inputs:
            if inp.type != "Research":
                continue
            tech = inp.payload.get("technology", inp.payload.get("technology_id", "?"))
            research_events.append({"time": ts(inp.timestamp), "tech": tech})

        # -- Age-up times (from research)
        age_times = {}
        for e in research_events:
            for age_name in ["Feudal Age", "Castle Age", "Imperial Age"]:
                if age_name in e["tech"]:
                    age_times[age_name] = e["time"]

        # -- Villager production and TC idle
        queue_inputs = [i for i in inputs if i.type == "Queue"]
        vill_count = sum(1 for i in queue_inputs if i.payload.get("unit") == "Villager")
        idle_periods = compute_tc_idle(queue_inputs)
        total_idle_s = sum(p["duration_s"] for p in idle_periods)

        # -- Military unit queue events
        military_events = []
        for inp in queue_inputs:
            unit = inp.payload.get("unit", "")
            if unit and unit != "Villager":
                military_events.append({"time": ts(inp.timestamp), "unit": unit})

        # -- Build order
        build_events = []
        for inp in inputs:
            if inp.type != "Build":
                continue
            building = inp.payload.get("building", inp.payload.get("building_id", "?"))
            pos = None
            if hasattr(inp, "position") and inp.position:
                pos = (round(inp.position.x), round(inp.position.y))
            build_events.append({"time": ts(inp.timestamp), "building": building, "pos": pos})

        # -- Villager resource assignment (Gather / Order targeting gaia objects)
        gather_events = []
        for inp in inputs:
            if inp.type not in ("Gather", "Order", "Gather Point"):
                continue
            target_id = inp.payload.get("target_id") or inp.payload.get("target")
            if target_id is None:
                continue
            rtype = get_resource_type(target_id, gaia_map)
            if rtype:
                gather_events.append({
                    "time": ts(inp.timestamp),
                    "resource": rtype,
                    "target_id": target_id,
                })

        # -- Boar luring: Order actions targeting boar/rhino
        boar_lures = [g for g in gather_events if g["resource"] == "boar"]

        # -- Scout movement (De_Autoscout or Move events early game, scout unit)
        # DE Autoscout actions
        autoscout = [
            {"time": ts(inp.timestamp)}
            for inp in inputs if inp.type == "De Autoscout"
        ]

        coaching_data[pid] = {
            "research_timeline": research_events,
            "age_times": age_times,
            "villagers_queued": vill_count,
            "tc_idle_periods": idle_periods,
            "tc_idle_total_s": total_idle_s,
            "military_production": military_events,
            "build_order": build_events,
            "resource_assignments": gather_events,
            "boar_lures": boar_lures,
            "autoscout_commands": autoscout,
            "total_actions": len(inputs),
        }

    # ── Resource economy snapshots (from sync body) ────────────────────────────
    snapshots = defaultdict(list)
    with open(replay_path, "rb") as f:
        fast_parse(f)
        fast.meta(f)
        timestamp_ms = 0
        while True:
            try:
                op_type, op_data = fast.operation(f)
                if op_type is fast.Operation.SYNC:
                    timestamp_ms += op_data[0]
                    if op_data[2]:
                        stat_row = op_data[2]
                        ts_s = timestamp_ms / 1000
                        for pid in players:
                            if pid in stat_row:
                                s = stat_row[pid]
                                snapshots[pid].append({
                                    "time_s": round(ts_s),
                                    "total_res": s.get("total_res", 0),
                                    "obj_count": s.get("obj_count", 0),
                                })
            except EOFError:
                break

    # Downsample snapshots to ~1 per minute for LLM consumption
    economy_timeline = {}
    for pid, snaps in snapshots.items():
        sampled = []
        last_minute = -1
        for snap in snaps:
            minute = snap["time_s"] // 60
            if minute != last_minute:
                sampled.append({
                    "time": f"{minute:02d}:00",
                    "total_res": snap["total_res"],
                    "obj_count": snap["obj_count"],
                })
                last_minute = minute
        economy_timeline[pid] = sampled

    # ── Age-up times from match.uptimes (engine-verified) ─────────────────────
    uptime_events = []
    for u in match.uptimes:
        uptime_events.append({
            "time": ts(u.timestamp),
            "player": u.player.name if u.player else "?",
            "age": str(u.age) if u.age else "?",
        })

    return {
        "map": {
            "name": map_info.get("name"),
            "size": f"{map_info.get('dimension')}x{map_info.get('dimension')}",
        },
        "duration": ts(duration_td),
        "players": {str(k): v for k, v in players.items()},
        "coaching_data": {str(k): v for k, v in coaching_data.items()},
        "economy_timeline": {str(k): v for k, v in economy_timeline.items()},
        "uptime_events": uptime_events,
    }


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python extract_game_data.py <replay.aoe2record>")
        sys.exit(1)

    data = extract(sys.argv[1])
    print(json.dumps(data, indent=2, default=str))
