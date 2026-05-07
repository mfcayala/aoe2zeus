# AoE2 Zeus — Coaching Tool

## Project Goal
Parse `.aoe2record` replay files → extract structured game data → feed to LLM → produce coaching report.

## Stack
- Parser: `mgz` Python library (`pip install mgz`)
- Entry point: `explore_replay.py <replay.aoe2record>`

---

## mgz Compatibility Patches (Save Version 67.2)

AoE2 DE build `v101.103.39862` (April 2026) uses **save version 67.2**, which `mgz==1.8.51` does not support out of the box. Three patches are needed. Apply them to the installed package after `pip install mgz`:

### 1. `/usr/local/lib/python3.11/dist-packages/mgz/header/de.py`

**After `colored_chat`** — add 4 mystery bytes introduced in save version ≥ 66.3:
```python
"colored_chat"/Flag,
If(lambda ctx: find_save_version(ctx) >= 66.3, Bytes(4)),  # ← ADD THIS
"empty_slots"/If(...)
```

**At end of DE struct** — add 8 trailing bytes introduced in save version ≥ 67.0:
```python
"ver37"/If(lambda ctx: find_save_version(ctx) >= 37, Struct(Int32ul, Int32ul)),
If(lambda ctx: find_save_version(ctx) >= 67.0, Bytes(8))  # ← ADD THIS
)
```

### 2. `/usr/local/lib/python3.11/dist-packages/mgz/fast/header.py`

**After `data.read(4)` near the `rated` field** — read the extra separator for ≥ 66.3:
```python
data.read(4)
if save >= 66.3:
    data.read(4)  # ← ADD THIS (separator)
rated = unpack('b', data)
```

**At end of `parse_de`** — add 8 trailing bytes for ≥ 67.0:
```python
if save >= 37:
    timestamp, x = unpack('<II', data)
if save >= 67.0:
    data.read(8)  # ← ADD THIS
```

### 3. `/usr/local/lib/python3.11/dist-packages/mgz/model/__init__.py`

Guard against new color IDs (≥ 8) and unknown civ IDs (e.g. 0 = random):
```python
# Change:
consts['player_colors'][str(player['color_id'])],
dataset['civilizations'][str(player['civilization_id'])]['name'],

# To:
consts['player_colors'].get(str(player['color_id']), str(player['color_id'])),
dataset['civilizations'].get(str(player['civilization_id']), {}).get('name', f"civ_{player['civilization_id']}"),
```

---

## What the Parser Gives Us

From `Summary(f)`:
- Map name, size, dimension
- Duration
- Player names, civ IDs, winner
- Game settings (pop cap, speed, starting age, victory type)
- Chat log with timestamps

From `parse_match(f)` (synchronous, returns `Match` dataclass):
- `.inputs` — full action stream, each with `.type`, `.timestamp` (timedelta), `.player_id`
- Serialize each input with `serialize(inp)` → dict with `payload`, `player`, `objects`

**Action types available:** Move, Queue, Build, Research, Gather, Gather Point, Target, Garrison, Ungarrison, Follow, Patrol, Order, Spawn, Stance, Delete, Stop, Gate, Farm Autoqueue, Fish Trap Autoqueue, De Autoscout, Buy, Resign, Chat, Guard, Unqueue

**Key coaching signals:**
- `Research` payloads → tech name + timestamp → age-up timing, loom timing, blacksmith upgrades
- `Build` payloads → building name + timestamp → build order execution
- `Queue` payloads → unit name + timestamp → villager production gaps (TC idle time)
- `Resign` → loss timestamp

**Known limitation:** `civilization_id` in the DE header is `0` for players who selected "random civ". Actual played civ is resolved in the `initial` section — use `parse_players` from `mgz.fast.header` to get the correct civ from the initial objects block.

---

## Sample Game Data (April 2026)

File: `MP Replay v101.103.39862.0 @2026.04.18 144432 (2).aoe2record`

- Map: Arena 120×120, 26:01 duration
- P1 `marcoghersii` — Cumans — **winner** — Feudal at **8:33**
- P2 `miguel.f.c.ayala` — random civ — **loser** — Loom at 4:17, Feudal at **11:02** (2:29 late), Castle at 16:54, resigned 26:01
- miguel never reached Castle before marcoghersii was already pushing with Man-at-Arms (13:59)
