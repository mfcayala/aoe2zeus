"""
Generate a self-contained HTML coaching report with interactive minimap.

Designed with clean CSS-variable structure and vanilla JS for easy
migration to a React/Flask frontend.

Public API:
    generate_html_report(game_data, focus_player_id, coaching_text,
                         position_data=None) -> str
"""

from __future__ import annotations

import base64
import html as html_mod
import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from extract_positions import ReplayPositions


# ── Section registry ───────────────────────────────────────────────────────────

_SECTIONS = [
    ("The Decisive Moment",                      "decisive", "#e05252"),
    ("What You Should Have Done At That Moment", "action",   "#5299e0"),
    ("What Led You There",                       "macro",    "#c8a22c"),
    ("Civ Matchup",                              "matchup",  "#8b5cf6"),
    ("Top 3 Things To Fix Next Game",            "fixes",    "#52c878"),
]

_SECTION_LABELS = {
    "decisive": "The Decisive Moment",
    "action":   "What You Should Have Done",
    "macro":    "Macro Gaps",
    "matchup":  "Civ Matchup",
    "fixes":    "Top 3 Fixes",
}

_SECTION_ICONS = {
    "decisive": "&#9889;",
    "action":   "&#8594;",
    "macro":    "&#9650;",
    "matchup":  "&#9876;",
    "fixes":    "&#10003;",
}


# ── Text helpers ───────────────────────────────────────────────────────────────

def _ts_to_s(ts: str) -> int:
    """MM:SS → seconds."""
    m, s = ts.split(":")
    return int(m) * 60 + int(s)


def _parse_sections(coaching_text: str) -> dict[str, str]:
    """Split LLM markdown into section key → raw text."""
    result: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in coaching_text.splitlines():
        if line.startswith("## "):
            if current_key:
                result[current_key] = "\n".join(current_lines).strip()
            heading = line[3:].strip()
            current_key = None
            for full_title, key, _ in _SECTIONS:
                if full_title.lower() in heading.lower() or heading.lower() in full_title.lower():
                    current_key = key
                    break
            if current_key is None:
                current_key = f"unknown_{len(result)}"
            current_lines = []
        else:
            current_lines.append(line)

    if current_key:
        result[current_key] = "\n".join(current_lines).strip()
    return result


def _extract_timestamps(text: str) -> list[int]:
    """Return all MM:SS timestamps found in text as seconds."""
    return [_ts_to_s(m) for m in re.findall(r'\b(\d{1,2}:\d{2})\b', text)]


def _md_to_html(text: str) -> str:
    """Minimal markdown → HTML converter."""
    text = html_mod.escape(text)
    # Timestamps → styled chip
    text = re.sub(
        r'\b(\d{1,2}:\d{2})\b',
        r'<span class="timestamp">\1</span>',
        text,
    )
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*',     r'<em>\1</em>',         text)

    lines = text.splitlines()
    out: list[str] = []
    in_ul = False
    for line in lines:
        s = line.strip()
        if s.startswith("- ") or s.startswith("• "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{s[2:]}</li>")
        else:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if s:
                out.append(f"<p>{s}</p>")
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


# ── Economy SVG (collapsible data panel) ──────────────────────────────────────

def _economy_svg(game_data: dict, focus_id: int, opp_id: int) -> str:
    W, H = 760, 180
    ML, MR, MT, MB = 50, 16, 16, 30

    focus_eco = game_data["economy_timeline"].get(str(focus_id), [])
    opp_eco   = game_data["economy_timeline"].get(str(opp_id),   [])
    uptimes   = game_data["uptime_events"]
    focus_name = game_data["players"][str(focus_id)]["name"]
    duration_s = _ts_to_s(game_data["duration"])

    all_res = [e["total_res"] for e in focus_eco + opp_eco if e["total_res"]]
    max_res = max(all_res, default=1) * 1.1

    def tx(s: int) -> float:
        return ML + (s / max(duration_s, 1)) * (W - ML - MR)

    def ty(r) -> float:
        return MT + (1 - r / max_res) * (H - MT - MB)

    def polyline(eco, color):
        pts = [f"{tx(_ts_to_s(e['time'])):.1f},{ty(e['total_res']):.1f}" for e in eco]
        if not pts:
            return ""
        return (
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round" opacity="0.9"/>'
        )

    idle_bands = []
    for p in game_data["coaching_data"][str(focus_id)]["tc_idle_periods"]:
        x1 = tx(_ts_to_s(p["start"]))
        x2 = tx(_ts_to_s(p["end"]))
        idle_bands.append(
            f'<rect x="{x1:.1f}" y="{MT}" width="{max(x2-x1,2):.1f}" '
            f'height="{H-MT-MB}" fill="#e05252" opacity="0.12"/>'
        )

    age_colors = {"Feudal": "#c8a22c", "Castle": "#8b5cf6", "Imperial": "#e05252"}
    age_lines = []
    for u in uptimes:
        s = _ts_to_s(u["time"])
        age_short = u["age"].replace("Age.", "").replace("_", " ").title().split()[0]
        color = age_colors.get(age_short, "#666")
        is_focus = u["player"] == focus_name
        dash = "4,4" if is_focus else "2,4"
        xv = tx(s)
        age_lines.append(
            f'<line x1="{xv:.1f}" y1="{MT}" x2="{xv:.1f}" y2="{H-MB}" '
            f'stroke="{color}" stroke-width="1.5" stroke-dasharray="{dash}" opacity="0.7"/>'
        )
        age_lines.append(
            f'<text x="{xv+3:.1f}" y="{MT+10}" fill="{color}" font-size="8" opacity="0.8">{age_short}</text>'
        )

    x_ticks = []
    for m in range(0, duration_s // 60 + 1, 5):
        xv = tx(m * 60)
        x_ticks += [
            f'<line x1="{xv:.1f}" y1="{H-MB}" x2="{xv:.1f}" y2="{H-MB+4}" stroke="#555" stroke-width="1"/>',
            f'<text x="{xv:.1f}" y="{H-MB+14}" fill="#666" font-size="9" text-anchor="middle">{m:02d}:00</text>',
        ]

    y_labels = []
    for frac in [0, 0.5, 1.0]:
        val = int(max_res * frac)
        yv = ty(val)
        y_labels += [
            f'<text x="{ML-4}" y="{yv+4:.1f}" fill="#666" font-size="9" text-anchor="end">{val}</text>',
            f'<line x1="{ML}" y1="{yv:.1f}" x2="{W-MR}" y2="{yv:.1f}" stroke="#2a2a38" stroke-width="1"/>',
        ]

    return (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto;display:block">'
        f'{"".join(y_labels)}{"".join(idle_bands)}{"".join(age_lines)}'
        f'{polyline(focus_eco,"#5299e0")}{polyline(opp_eco,"#e05252")}'
        f'{"".join(x_ticks)}'
        f'<line x1="{ML}" y1="{MT}" x2="{ML}" y2="{H-MB}" stroke="#333" stroke-width="1"/>'
        f'<line x1="{ML}" y1="{H-MB}" x2="{W-MR}" y2="{H-MB}" stroke="#333" stroke-width="1"/>'
        f'</svg>'
    )


# ── Minimap data embedding ─────────────────────────────────────────────────────

def _encode_map_arrays(position_data: ReplayPositions) -> tuple[str, str]:
    """Encode terrain and elevation as base64 Uint8 strings (~3× smaller than JSON)."""
    terrain_b64   = base64.b64encode(bytes(position_data.map.terrain)).decode("ascii")
    elevation_b64 = base64.b64encode(bytes(position_data.map.elevation)).decode("ascii")
    return terrain_b64, elevation_b64


def _minimap_data_script(position_data: ReplayPositions) -> str:
    terrain_b64, elevation_b64 = _encode_map_arrays(position_data)
    players_json  = json.dumps({str(k): v.to_dict() for k, v in position_data.players.items()})
    resources_json = json.dumps(position_data.map.resources)

    return f"""<script>
(function () {{
  const _b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
  window.MINIMAP = {{
    dim:       {position_data.map.dimension},
    terrain:   _b64("{terrain_b64}"),
    elevation: _b64("{elevation_b64}"),
    resources: {resources_json},
    players:   {players_json},
    durationS: {position_data.duration_s},
  }};
}})();
</script>"""


# ── Minimap JS engine ──────────────────────────────────────────────────────────

_MINIMAP_JS = r"""
<script>
(function () {
  if (!window.MINIMAP) return;

  // ── Palette tables ───────────────────────────────────────────────────────
  // terrain_id → [r, g, b] base colour (elevation darkens it slightly)
  const TERRAIN_RGB = {
    0:   [38,  80, 22],   // Grass 1
    1:   [20,  60,120],   // Shallow water
    2:   [180,165, 90],   // Beach
    3:   [10,  40, 90],   // Deep water
    4:   [16,  65,140],   // Water
    5:   [22,  90,150],   // Shallows
    7:   [110, 88, 60],   // Dirt
    8:   [120,100, 48],   // Farm
    9:   [34,  80, 20],   // Grass 2
    13:  [190,170, 80],   // Sand
    14:  [40,  82, 26],   // Grass 3
    18:  [42,  90, 26],   // Grass variant (Arena outer)
    24:  [18,  58, 10],   // Forest
    34:  [210,218,230],   // Snow
    38:  [160,185,200],   // Ice
    46:  [90,  75, 55],   // Rock
    77:  [100, 84, 62],   // Old cobblestone
    113: [118, 98, 68],   // Arena stone floor
  };
  const TERRAIN_DEFAULT = [70, 65, 55];

  const RESOURCE_RGB = {
    gold:    [240, 195,  30],
    stone:   [155, 155, 170],
    tree:    [ 18,  72,  10],
    boar:    [130,  60,  20],
    hunt:    [190, 140,  60],
    berries: [190,  40,  60],
  };

  // Player number → CSS colour string
  const PLAYER_COLORS = {
    1: '#4488ff',
    2: '#ff4444',
    3: '#44cc44',
    4: '#cccc00',
    5: '#00cccc',
    6: '#cc44cc',
    7: '#aaaaaa',
    8: '#ff8800',
  };

  // Age → scrubber marker colour
  const AGE_COLORS = {
    'Feudal': '#c8a22c',
    'Castle': '#8b5cf6',
    'Imperial': '#e05252',
  };

  // ── State ────────────────────────────────────────────────────────────────
  const state = {
    currentTime: 0,
    playing: false,
    speed: 30,
    lastRealMs: null,
    animHandle: null,
  };

  // ── DOM refs ─────────────────────────────────────────────────────────────
  const canvas  = document.getElementById('minimap-canvas');
  const ctx     = canvas.getContext('2d');
  const playBtn = document.getElementById('play-btn');
  const scrubTrack  = document.getElementById('scrubber-track');
  const scrubThumb  = document.getElementById('scrubber-thumb');
  const scrubTime   = document.getElementById('scrubber-time');
  const speedSelect = document.getElementById('speed-select');

  const { dim, terrain, elevation, resources, players, durationS } = window.MINIMAP;

  // ── Pre-render terrain ───────────────────────────────────────────────────
  const SCALE = Math.max(1, Math.floor(480 / dim));
  canvas.width  = dim * SCALE;
  canvas.height = dim * SCALE;

  let terrainCanvas;
  function buildTerrainImage() {
    terrainCanvas = document.createElement('canvas');
    terrainCanvas.width  = dim;
    terrainCanvas.height = dim;
    const tCtx = terrainCanvas.getContext('2d');
    const img   = tCtx.createImageData(dim, dim);
    const d     = img.data;

    for (let y = 0; y < dim; y++) {
      for (let x = 0; x < dim; x++) {
        const idx = y * dim + x;
        const tid = terrain[idx];
        const elev = elevation[idx];
        const [r, g, b] = TERRAIN_RGB[tid] || TERRAIN_DEFAULT;
        // Darken slightly with elevation (walls stand out)
        const factor = 1 - elev * 0.07;
        const pi = idx * 4;
        d[pi]   = Math.round(r * factor);
        d[pi+1] = Math.round(g * factor);
        d[pi+2] = Math.round(b * factor);
        d[pi+3] = 255;
      }
    }
    tCtx.putImageData(img, 0, 0);
  }

  // ── Coordinate helpers ───────────────────────────────────────────────────
  function toCanvasXY(normX, normY) {
    return [normX * canvas.width, normY * canvas.height];
  }

  function dot(normX, normY, radius, color, alpha) {
    const [cx, cy] = toCanvasXY(normX, normY);
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.globalAlpha = alpha;
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  function ring(normX, normY, radius, color, strokeColor) {
    const [cx, cy] = toCanvasXY(normX, normY);
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = strokeColor || '#fff';
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  // ── Static resource layer ────────────────────────────────────────────────
  function drawResources() {
    resources.forEach(r => {
      const rgb = RESOURCE_RGB[r.type];
      if (!rgb) return;
      const color = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
      const radius = r.type === 'tree' ? 1.5 * SCALE : 2.5 * SCALE;
      dot(r.x, r.y, radius, color, r.type === 'tree' ? 0.6 : 0.85);
    });
  }

  // ── Dynamic layer ────────────────────────────────────────────────────────
  const TRAIL_WINDOW_S = 45;  // seconds of activity to show

  function drawDynamic(timeS) {
    Object.values(players).forEach(player => {
      const color = PLAYER_COLORS[player.number] || '#ffffff';

      // Activity trail: commands in the trailing window
      player.activity
        .filter(a => a.time_s <= timeS && a.time_s >= timeS - TRAIL_WINDOW_S)
        .forEach(a => {
          // Fade: newer = more opaque
          const age = timeS - a.time_s;
          const alpha = 0.08 + 0.22 * (1 - age / TRAIL_WINDOW_S);
          dot(a.pos.x, a.pos.y, 2.5 * SCALE, color, alpha);
        });

      // Buildings placed up to timeS
      player.buildings
        .filter(b => b.time_s <= timeS)
        .forEach(b => {
          const isMilitary = /Barracks|Stable|Archery|Castle|Siege|Blacksmith|University/i.test(b.building);
          const radius = isMilitary ? 3.5 * SCALE : 2.5 * SCALE;
          dot(b.pos.x, b.pos.y, radius, color, 0.75);
        });

      // TC — always visible
      ring(player.tc.x, player.tc.y, 5 * SCALE, color, '#ffffff');
    });
  }

  // ── Full render ──────────────────────────────────────────────────────────
  function render(timeS) {
    state.currentTime = Math.max(0, Math.min(timeS, durationS));

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(terrainCanvas, 0, 0, canvas.width, canvas.height);

    drawResources();
    drawDynamic(state.currentTime);

    updateScrubberUI(state.currentTime);
    updateCardHighlights(state.currentTime);
  }

  // ── Coaching card sync ───────────────────────────────────────────────────
  const CARD_WINDOW_S = 90;  // highlight cards whose timestamps are within ±Ns

  function updateCardHighlights(timeS) {
    let anyActive = false;
    document.querySelectorAll('.coaching-card').forEach(card => {
      const times = JSON.parse(card.dataset.timestamps || '[]');
      const active = times.some(t => Math.abs(t - timeS) < CARD_WINDOW_S);
      card.classList.toggle('card-active', active);
      if (active) anyActive = true;
    });
  }

  // ── Scrubber UI ──────────────────────────────────────────────────────────
  function fmtTime(s) {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
  }

  function updateScrubberUI(timeS) {
    const pct = (timeS / durationS) * 100;
    scrubThumb.style.left = `${pct}%`;
    scrubTime.textContent = `${fmtTime(timeS)} / ${fmtTime(durationS)}`;
  }

  function timeFromPointer(clientX) {
    const rect = scrubTrack.getBoundingClientRect();
    const pct  = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return pct * durationS;
  }

  function addAgeUpMarkers() {
    // Age-up events live in game_data (embedded separately)
    const events = window.UPTIME_EVENTS || [];
    events.forEach(ev => {
      const ageName = ev.age.replace('Age.', '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      const ageKey  = ageName.split(' ')[0];
      const color   = AGE_COLORS[ageKey] || '#888';
      const pct = (ev.time_s / durationS) * 100;
      const marker = document.createElement('div');
      marker.className = 'age-marker';
      marker.style.left  = `${pct}%`;
      marker.style.background = color;
      marker.title = `${ev.player} → ${ageName} (${fmtTime(ev.time_s)})`;
      scrubTrack.appendChild(marker);
    });
  }

  // ── Scrubber interaction ─────────────────────────────────────────────────
  function setupScrubber() {
    let dragging = false;

    function onScrub(clientX) {
      if (state.playing) pausePlayback();
      render(timeFromPointer(clientX));
    }

    scrubTrack.addEventListener('mousedown', e => { dragging = true; onScrub(e.clientX); });
    document.addEventListener('mousemove',  e => { if (dragging) onScrub(e.clientX); });
    document.addEventListener('mouseup',    () => { dragging = false; });

    scrubTrack.addEventListener('touchstart', e => onScrub(e.touches[0].clientX), { passive: true });
    scrubTrack.addEventListener('touchmove',  e => { e.preventDefault(); onScrub(e.touches[0].clientX); }, { passive: false });
  }

  // ── Playback ─────────────────────────────────────────────────────────────
  function tick(realMs) {
    if (!state.playing) return;
    if (state.lastRealMs !== null) {
      const deltaGameS = ((realMs - state.lastRealMs) / 1000) * state.speed;
      const next = state.currentTime + deltaGameS;
      if (next >= durationS) {
        render(durationS);
        pausePlayback();
        return;
      }
      render(next);
    }
    state.lastRealMs = realMs;
    state.animHandle = requestAnimationFrame(tick);
  }

  function startPlayback() {
    state.playing    = true;
    state.lastRealMs = null;
    playBtn.textContent = '⏸';
    playBtn.classList.add('playing');
    if (state.currentTime >= durationS) render(0);
    state.animHandle = requestAnimationFrame(tick);
  }

  function pausePlayback() {
    state.playing = false;
    playBtn.textContent = '▶';
    playBtn.classList.remove('playing');
    if (state.animHandle) cancelAnimationFrame(state.animHandle);
  }

  playBtn.addEventListener('click', () => {
    state.playing ? pausePlayback() : startPlayback();
  });

  speedSelect.addEventListener('change', () => {
    state.speed = parseFloat(speedSelect.value);
  });

  // ── Bootstrap ────────────────────────────────────────────────────────────
  buildTerrainImage();
  addAgeUpMarkers();
  setupScrubber();
  render(0);
})();
</script>
"""


# ── HTML assembly ──────────────────────────────────────────────────────────────

_CSS = r"""
<style>
/* ── Design tokens ── */
:root {
  --bg:        #0f0f13;
  --surface:   #16161d;
  --surface2:  #1e1e2a;
  --border:    #2a2a3a;
  --gold:      #c8a22c;
  --gold-dim:  #7a6118;
  --blue:      #5299e0;
  --red:       #e05252;
  --purple:    #8b5cf6;
  --green:     #52c878;
  --text:      #e0e0e8;
  --text-muted:#6e6e88;
  --radius:    8px;
  --radius-lg: 14px;
  --font-mono: "SF Mono","Fira Code","Consolas",monospace;
}

/* ── Reset ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.6;
  padding-bottom: 4rem;
}

/* ── Layout ── */
.report-header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 1.25rem 1.5rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.header-brand   { font-size:.7rem;letter-spacing:.15em;text-transform:uppercase;color:var(--gold);margin-right:auto; }
.header-duration{ font-family:var(--font-mono);font-size:.85rem;color:var(--text-muted); }

.container { max-width: 860px; margin: 0 auto; padding: 0 1.25rem; }

/* ── Meta grid ── */
.meta-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  margin: 1.5rem 0;
  background: var(--surface);
}
.meta-cell {
  padding: .9rem 1rem;
  border-right: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  display: flex; flex-direction: column; gap: .25rem;
}
.meta-cell:nth-child(3n)     { border-right: none; }
.meta-cell:nth-last-child(-n+3) { border-bottom: none; }
.meta-label { font-size:.65rem;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted); }
.meta-value { font-size:1.05rem;font-weight:600;color:var(--text); }

/* ── Player matchup ── */
.matchup {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 1rem;
  align-items: center;
  margin-bottom: 1.5rem;
}
.player-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 1rem 1.25rem;
}
.player-card.focus { border-color:var(--blue);box-shadow:0 0 0 1px rgba(82,153,224,.2); }
.player-card.opp   { border-color:var(--red); box-shadow:0 0 0 1px rgba(224,82,82,.2); }
.player-name { font-size:1rem;font-weight:700;margin-bottom:.2rem; }
.focus .player-name { color:var(--blue); }
.opp   .player-name { color:var(--red);  }
.player-civ  { font-size:.8rem;color:var(--gold);margin-bottom:.75rem; }
.pstat { display:flex;justify-content:space-between;gap:1rem;margin-top:.3rem; }
.pstat-label { font-size:.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em; }
.pstat-value { font-family:var(--font-mono);font-size:.82rem;color:var(--text); }
.badge { display:inline-block;padding:.15rem .6rem;border-radius:4px;font-size:.65rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;margin-top:.6rem; }
.badge-win  { background:rgba(82,200,120,.15);color:var(--green);border:1px solid rgba(82,200,120,.3); }
.badge-loss { background:rgba(224,82,82,.12); color:var(--red);  border:1px solid rgba(224,82,82,.25); }
.vs-badge   { font-size:1.1rem;font-weight:800;color:var(--text-muted);text-align:center;user-select:none; }

/* ── Section heading ── */
.section-heading {
  font-size:.7rem;letter-spacing:.18em;text-transform:uppercase;
  color:var(--gold);padding-bottom:.5rem;
  border-bottom:1px solid var(--gold-dim);
  margin-bottom:1.25rem;margin-top:2.5rem;
}

/* ── Minimap player ── */
.map-section {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 1.25rem;
  margin-bottom: 2rem;
}
.map-wrapper {
  display: flex;
  gap: 1.25rem;
  align-items: flex-start;
  flex-wrap: wrap;
}
.map-canvas-wrap {
  position: relative;
  flex-shrink: 0;
}
#minimap-canvas {
  display: block;
  width: 320px;
  height: 320px;
  image-rendering: pixelated;
  border-radius: var(--radius);
  border: 1px solid var(--border);
}
.map-legend {
  display: flex;
  flex-direction: column;
  gap: .4rem;
  margin-top: .5rem;
}
.legend-row {
  display: flex;
  align-items: center;
  gap: .5rem;
  font-size: .75rem;
  color: var(--text-muted);
}
.legend-swatch {
  width: 10px; height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.map-resource-legend {
  display: flex;
  flex-wrap: wrap;
  gap: .5rem;
  margin-top: .75rem;
  font-size: .68rem;
  color: var(--text-muted);
}
.map-resource-legend span { display:flex;align-items:center;gap:.3rem; }
.res-dot {
  width:8px;height:8px;border-radius:50%;display:inline-block;flex-shrink:0;
}

/* ── Scrubber ── */
.scrubber-bar {
  display: flex;
  align-items: center;
  gap: .75rem;
  margin-top: 1rem;
}
#play-btn {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-size: 1rem;
  width: 36px; height: 36px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  transition: background .15s;
}
#play-btn:hover        { background: var(--border); }
#play-btn.playing      { color: var(--gold); }

.scrubber-wrap {
  flex: 1;
  position: relative;
  height: 36px;
  display: flex;
  align-items: center;
}
#scrubber-track {
  position: relative;
  width: 100%;
  height: 6px;
  background: var(--surface2);
  border-radius: 3px;
  cursor: pointer;
  border: 1px solid var(--border);
}
#scrubber-thumb {
  position: absolute;
  top: 50%;
  width: 14px; height: 14px;
  border-radius: 50%;
  background: var(--gold);
  border: 2px solid var(--bg);
  transform: translate(-50%, -50%);
  pointer-events: none;
  transition: transform .1s;
  z-index: 2;
}
.age-marker {
  position: absolute;
  top: 50%;
  width: 3px; height: 14px;
  transform: translate(-50%, -50%);
  border-radius: 2px;
  opacity: .8;
  pointer-events: none;
  z-index: 1;
}
.scrubber-time {
  font-family: var(--font-mono);
  font-size: .78rem;
  color: var(--text-muted);
  white-space: nowrap;
  min-width: 7ch;
}
#speed-select {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-size: .8rem;
  padding: .25rem .4rem;
  cursor: pointer;
}

/* ── Coaching cards ── */
.coaching-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--card-color, var(--gold));
  border-radius: var(--radius-lg);
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.25rem;
  position: relative;
  transition: box-shadow .3s, background .3s;
}
.coaching-card.card-active {
  background: var(--surface2);
  box-shadow: 0 0 0 1px var(--card-color), 0 4px 24px rgba(0,0,0,.4);
}
.card-title {
  font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--card-color,var(--gold));margin-bottom:.9rem;
  display:flex;align-items:center;gap:.5rem;
}
.card-icon  { font-size:1rem;line-height:1; }
.card-body p  { margin-bottom:.65rem;color:var(--text);font-size:.93rem;line-height:1.65; }
.card-body p:last-child { margin-bottom:0; }
.card-body ul { margin:.5rem 0 .65rem 1.25rem; }
.card-body li { margin-bottom:.35rem;font-size:.93rem;line-height:1.65; }
.card-body strong { color:var(--text);font-weight:700; }

/* Timestamp chips */
.timestamp {
  font-family: var(--font-mono);
  font-size: .82em;
  background: rgba(200,162,44,.12);
  color: var(--gold);
  border: 1px solid rgba(200,162,44,.25);
  border-radius: 3px;
  padding: .05em .35em;
  white-space: nowrap;
  cursor: pointer;
}
.timestamp:hover { background: rgba(200,162,44,.22); }

/* ── Economy panel ── */
details.data-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  margin-top: 2rem;
  overflow: hidden;
}
details.data-panel summary {
  padding: .9rem 1.25rem;
  cursor: pointer;
  user-select: none;
  font-size: .7rem;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: var(--text-muted);
  list-style: none;
  display: flex; align-items: center; gap: .5rem;
}
details.data-panel summary::-webkit-details-marker { display: none; }
details.data-panel summary::before { content:"▶";font-size:.6rem;transition:transform .2s; }
details[open].data-panel summary::before { transform:rotate(90deg); }
.data-panel-body  { padding: 0 1.25rem 1.25rem; }
.chart-legend     { display:flex;gap:1.5rem;margin-bottom:.75rem;font-size:.75rem;color:var(--text-muted); }
.legend-dot       { width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:.35rem;vertical-align:middle; }
.chart-note       { font-size:.7rem;color:var(--text-muted);margin-top:.5rem; }
</style>
"""


def generate_html_report(
    game_data: dict,
    focus_player_id: int,
    coaching_text: str,
    position_data=None,
) -> str:
    opp_id = 1 if focus_player_id == 2 else 2
    focus  = game_data["players"][str(focus_player_id)]
    opp    = game_data["players"][str(opp_id)]
    focus_cd = game_data["coaching_data"][str(focus_player_id)]
    opp_cd   = game_data["coaching_data"][str(opp_id)]

    focus_civ = focus["civ"] if not str(focus["civ"]).startswith("civ_") else "Unknown"
    opp_civ   = opp["civ"]   if not str(opp["civ"]).startswith("civ_")   else "Unknown"
    map_info  = game_data["map"]

    sections = _parse_sections(coaching_text)

    # ── Helpers ──
    def meta_cell(label, value):
        return (f'<div class="meta-cell">'
                f'<span class="meta-label">{label}</span>'
                f'<span class="meta-value">{value}</span></div>')

    def player_stat(label, value):
        return (f'<div class="pstat">'
                f'<span class="pstat-label">{label}</span>'
                f'<span class="pstat-value">{value}</span></div>')

    focus_feudal = focus_cd["age_times"].get("Feudal Age", "—")
    opp_feudal   = opp_cd["age_times"].get("Feudal Age", "—")
    focus_castle = focus_cd["age_times"].get("Castle Age", "—")
    opp_castle   = opp_cd["age_times"].get("Castle Age", "—")

    focus_result_cls = "badge-win"  if focus["winner"] else "badge-loss"
    focus_result_txt = "WIN"        if focus["winner"] else "LOSS"
    opp_result_cls   = "badge-win"  if opp["winner"]   else "badge-loss"
    opp_result_txt   = "WIN"        if opp["winner"]    else "LOSS"

    # ── Coaching cards ──
    section_cards = []
    for full_title, key, color in _SECTIONS:
        raw = sections.get(key, "")
        if not raw:
            continue
        timestamps = _extract_timestamps(raw)
        section_cards.append(
            f'<section class="coaching-card" '
            f'style="--card-color:{color}" '
            f'data-timestamps="{html_mod.escape(json.dumps(timestamps))}">'
            f'<h2 class="card-title">'
            f'<span class="card-icon" aria-hidden="true">{_SECTION_ICONS[key]}</span>'
            f'{_SECTION_LABELS[key]}</h2>'
            f'<div class="card-body">{_md_to_html(raw)}</div>'
            f'</section>'
        )

    # ── Uptime events for scrubber markers ──
    uptime_js_events = json.dumps([
        {"player": u["player"], "age": u["age"],
         "time_s": _ts_to_s(u["time"])}
        for u in game_data["uptime_events"]
    ])

    # ── Minimap section ──
    if position_data is not None:
        player1_color = "#4488ff"
        player2_color = "#ff4444"

        p_colors = {}
        for pid, p in game_data["players"].items():
            p_colors[p["name"]] = player1_color if int(pid) == 1 else player2_color

        focus_color = p_colors.get(focus["name"], "#4488ff")
        opp_color   = p_colors.get(opp["name"],   "#ff4444")

        map_block = f"""
<p class="section-heading">Overview</p>
<div class="map-section">
  <div class="map-wrapper">
    <div class="map-canvas-wrap">
      <canvas id="minimap-canvas"></canvas>
      <div class="map-legend">
        <div class="legend-row">
          <div class="legend-swatch" style="background:{focus_color}"></div>
          <span>{html_mod.escape(focus['name'])} ({html_mod.escape(focus_civ)})</span>
        </div>
        <div class="legend-row">
          <div class="legend-swatch" style="background:{opp_color}"></div>
          <span>{html_mod.escape(opp['name'])} ({html_mod.escape(opp_civ)})</span>
        </div>
      </div>
      <div class="map-resource-legend">
        <span><span class="res-dot" style="background:#f0c81e"></span>Gold</span>
        <span><span class="res-dot" style="background:#9b9baa"></span>Stone</span>
        <span><span class="res-dot" style="background:#12481a"></span>Trees</span>
        <span><span class="res-dot" style="background:#c83c46"></span>Berries</span>
        <span><span class="res-dot" style="background:#c89640"></span>Hunt</span>
        <span><span class="res-dot" style="background:#823c14"></span>Boar</span>
      </div>
    </div>
  </div>

  <div class="scrubber-bar">
    <button id="play-btn">&#9654;</button>
    <div class="scrubber-wrap">
      <div id="scrubber-track">
        <div id="scrubber-thumb"></div>
      </div>
    </div>
    <span class="scrubber-time" id="scrubber-time">00:00&nbsp;/&nbsp;{game_data['duration']}</span>
    <select id="speed-select">
      <option value="5">5&#215;</option>
      <option value="15">15&#215;</option>
      <option value="30" selected>30&#215;</option>
      <option value="60">60&#215;</option>
    </select>
  </div>
</div>

{_minimap_data_script(position_data)}
<script>window.UPTIME_EVENTS = {uptime_js_events};</script>
{_MINIMAP_JS}
"""
    else:
        map_block = ""

    economy_svg = _economy_svg(game_data, focus_player_id, opp_id)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AoE2 Zeus &#8212; {html_mod.escape(focus['name'])}</title>
{_CSS}
</head>
<body>

<header class="report-header">
  <span class="header-brand">AoE2 Zeus &#8212; Coaching Report</span>
  <span class="header-duration">{html_mod.escape(map_info['name'])} &#183; {game_data['duration']}</span>
</header>

<div class="container">

  <div class="meta-grid">
    {meta_cell("Map",        html_mod.escape(map_info['name']))}
    {meta_cell("Size",       html_mod.escape(map_info['size']))}
    {meta_cell("Duration",   game_data['duration'])}
    {meta_cell("Population", "200")}
    {meta_cell("Speed",      "Normal")}
    {meta_cell("Victory",    "Conquest")}
  </div>

  <div class="matchup">
    <div class="player-card focus">
      <div class="player-name">{html_mod.escape(focus['name'])}</div>
      <div class="player-civ">{html_mod.escape(focus_civ)}</div>
      {player_stat("eAPM", str(focus.get("eapm","—")))}
      {player_stat("Feudal", focus_feudal)}
      {player_stat("Castle", focus_castle) if focus_castle != "—" else ""}
      <div><span class="badge {focus_result_cls}">{focus_result_txt}</span></div>
    </div>
    <div class="vs-badge">VS</div>
    <div class="player-card opp">
      <div class="player-name">{html_mod.escape(opp['name'])}</div>
      <div class="player-civ">{html_mod.escape(opp_civ)}</div>
      {player_stat("eAPM", str(opp.get("eapm","—")))}
      {player_stat("Feudal", opp_feudal)}
      {player_stat("Castle", opp_castle) if opp_castle != "—" else ""}
      <div><span class="badge {opp_result_cls}">{opp_result_txt}</span></div>
    </div>
  </div>

  {map_block}

  <p class="section-heading">Coaching Report</p>
  {"".join(section_cards)}

  <details class="data-panel">
    <summary>Economy Timeline</summary>
    <div class="data-panel-body">
      <div class="chart-legend">
        <span><span class="legend-dot" style="background:var(--blue)"></span>{html_mod.escape(focus['name'])}</span>
        <span><span class="legend-dot" style="background:var(--red)"></span>{html_mod.escape(opp['name'])}</span>
        <span style="color:#e05252;font-size:.68rem">&#9644; TC idle</span>
      </div>
      {economy_svg}
      <p class="chart-note">Total resources per minute. Dashed verticals = age-ups. Red bands = your TC idle.</p>
    </div>
  </details>

</div>
</body>
</html>"""
