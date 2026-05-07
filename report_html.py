"""
Generate a self-contained HTML coaching report.
Designed with clean CSS-variable structure for easy React migration.
"""
import re
import html as html_mod


# ── Section metadata ───────────────────────────────────────────────────────────
_SECTIONS = [
    ("The Decisive Moment",                   "decisive",  "#e05252"),
    ("What You Should Have Done At That Moment", "action", "#5299e0"),
    ("What Led You There",                    "macro",     "#c8a22c"),
    ("Civ Matchup",                           "matchup",   "#8b5cf6"),
    ("Top 3 Things To Fix Next Game",         "fixes",     "#52c878"),
]

_SECTION_LABELS = {
    "decisive": "The Decisive Moment",
    "action":   "What You Should Have Done",
    "macro":    "Macro Gaps",
    "matchup":  "Civ Matchup",
    "fixes":    "Top 3 Fixes",
}

_SECTION_ICONS = {
    "decisive": "&#9889;",   # ⚡
    "action":   "&#8594;",   # →
    "macro":    "&#9650;",   # ▲
    "matchup":  "&#9876;",   # ⚔ (crossed swords)
    "fixes":    "&#10003;",  # ✓
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ts_to_s(ts: str) -> int:
    """MM:SS → seconds."""
    parts = ts.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _parse_sections(coaching_text: str) -> dict:
    """Split LLM markdown output into section key → raw text."""
    result = {}
    current_key = None
    current_lines = []

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


def _md_to_html(text: str) -> str:
    """Minimal markdown → HTML: bold, italic, bullets, timestamps."""
    text = html_mod.escape(text)

    # Timestamps  MM:SS  → styled span
    text = re.sub(
        r'\b(\d{1,2}:\d{2})\b',
        r'<span class="timestamp">\1</span>',
        text
    )
    # **bold**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # *italic*
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)

    lines = text.splitlines()
    out = []
    in_ul = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("• "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{stripped[2:]}</li>")
        else:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if stripped:
                out.append(f"<p>{stripped}</p>")
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


# ── SVG economy chart ──────────────────────────────────────────────────────────

def _economy_svg(game_data: dict, focus_id: int, opp_id: int) -> str:
    W, H = 760, 180
    ML, MR, MT, MB = 50, 16, 16, 30

    focus_eco = game_data["economy_timeline"].get(str(focus_id), [])
    opp_eco   = game_data["economy_timeline"].get(str(opp_id), [])
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
        pts = []
        for e in eco:
            s = _ts_to_s(e["time"])
            pts.append(f"{tx(s):.1f},{ty(e['total_res']):.1f}")
        if not pts:
            return ""
        return (
            f'<polyline points="{" ".join(pts)}" '
            f'fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round" opacity="0.9"/>'
        )

    # TC idle bands for focus player
    idle_bands = []
    for p in game_data["coaching_data"][str(focus_id)]["tc_idle_periods"]:
        x1 = tx(_ts_to_s(p["start"]))
        x2 = tx(_ts_to_s(p["end"]))
        idle_bands.append(
            f'<rect x="{x1:.1f}" y="{MT}" width="{max(x2-x1,2):.1f}" '
            f'height="{H-MT-MB}" fill="#e05252" opacity="0.12"/>'
        )

    # Age-up vertical lines
    age_lines = []
    age_colors = {"Feudal": "#c8a22c", "Castle": "#8b5cf6", "Imperial": "#e05252"}
    for u in uptimes:
        s = _ts_to_s(u["time"])
        age_label = u["age"].replace("Age.", "").replace("_", " ").title()
        age_short = age_label.split()[0] if age_label else "?"
        color = age_colors.get(age_short, "#666")
        is_focus = u["player"] == focus_name
        dash = "4,4" if is_focus else "2,4"
        xv = tx(s)
        age_lines.append(
            f'<line x1="{xv:.1f}" y1="{MT}" x2="{xv:.1f}" y2="{H-MB}" '
            f'stroke="{color}" stroke-width="1.5" stroke-dasharray="{dash}" opacity="0.7"/>'
        )
        age_lines.append(
            f'<text x="{xv+3:.1f}" y="{MT+10}" fill="{color}" '
            f'font-size="8" opacity="0.8">{age_short}</text>'
        )

    # X axis ticks (every 5 minutes)
    x_ticks = []
    for m in range(0, duration_s // 60 + 1, 5):
        xv = tx(m * 60)
        x_ticks.append(
            f'<line x1="{xv:.1f}" y1="{H-MB}" x2="{xv:.1f}" y2="{H-MB+4}" '
            f'stroke="#555" stroke-width="1"/>'
        )
        x_ticks.append(
            f'<text x="{xv:.1f}" y="{H-MB+14}" fill="#666" font-size="9" '
            f'text-anchor="middle">{m:02d}:00</text>'
        )

    # Y axis
    y_labels = []
    for frac in [0, 0.5, 1.0]:
        val = int(max_res * frac)
        yv = ty(val)
        y_labels.append(
            f'<text x="{ML-4}" y="{yv+4:.1f}" fill="#666" font-size="9" '
            f'text-anchor="end">{val}</text>'
        )
        y_labels.append(
            f'<line x1="{ML}" y1="{yv:.1f}" x2="{W-MR}" y2="{yv:.1f}" '
            f'stroke="#2a2a38" stroke-width="1"/>'
        )

    return f"""<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;display:block">
  {"".join(y_labels)}
  {"".join(idle_bands)}
  {"".join(age_lines)}
  {polyline(focus_eco, "#5299e0")}
  {polyline(opp_eco, "#e05252")}
  {"".join(x_ticks)}
  <line x1="{ML}" y1="{MT}" x2="{ML}" y2="{H-MB}" stroke="#333" stroke-width="1"/>
  <line x1="{ML}" y1="{H-MB}" x2="{W-MR}" y2="{H-MB}" stroke="#333" stroke-width="1"/>
</svg>"""


# ── Main HTML builder ──────────────────────────────────────────────────────────

def generate_html_report(game_data: dict, focus_player_id: int, coaching_text: str) -> str:
    opp_id = 1 if focus_player_id == 2 else 2
    focus  = game_data["players"][str(focus_player_id)]
    opp    = game_data["players"][str(opp_id)]
    focus_cd = game_data["coaching_data"][str(focus_player_id)]
    opp_cd   = game_data["coaching_data"][str(opp_id)]

    focus_civ = focus["civ"] if not str(focus["civ"]).startswith("civ_") else "Unknown"
    opp_civ   = opp["civ"]   if not str(opp["civ"]).startswith("civ_")   else "Unknown"

    sections = _parse_sections(coaching_text)

    def meta_cell(label, value):
        return f"""<div class="meta-cell">
      <span class="meta-label">{label}</span>
      <span class="meta-value">{value}</span>
    </div>"""

    def player_stat(label, value):
        return f'<div class="pstat"><span class="pstat-label">{label}</span><span class="pstat-value">{value}</span></div>'

    focus_feudal = focus_cd["age_times"].get("Feudal Age", "—")
    opp_feudal   = opp_cd["age_times"].get("Feudal Age", "—")
    focus_castle = focus_cd["age_times"].get("Castle Age", "—")
    opp_castle   = opp_cd["age_times"].get("Castle Age", "—")

    map_info = game_data["map"]

    # Build section cards
    section_cards = []
    for full_title, key, color in _SECTIONS:
        raw = sections.get(key, "")
        if not raw:
            continue
        icon = _SECTION_ICONS[key]
        label = _SECTION_LABELS[key]
        body = _md_to_html(raw)
        section_cards.append(f"""<section class="coaching-card" style="--card-color:{color}">
    <h2 class="card-title">
      <span class="card-icon" aria-hidden="true">{icon}</span>
      {label}
    </h2>
    <div class="card-body">{body}</div>
  </section>""")

    svg = _economy_svg(game_data, focus_player_id, opp_id)

    focus_result_cls = "badge-win" if focus["winner"] else "badge-loss"
    focus_result_txt = "WIN" if focus["winner"] else "LOSS"
    opp_result_cls   = "badge-win" if opp["winner"] else "badge-loss"
    opp_result_txt   = "WIN" if opp["winner"] else "LOSS"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AoE2 Zeus — {html_mod.escape(focus["name"])}</title>
<style>
/* ── Design tokens ── */
:root {{
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
  --font-mono: "SF Mono", "Fira Code", "Consolas", monospace;
}}

/* ── Reset & base ── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ font-size: 16px; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.6;
  min-height: 100vh;
  padding-bottom: 4rem;
}}

/* ── Header bar ── */
.report-header {{
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 1.25rem 1.5rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}}
.header-brand {{
  font-size: 0.7rem;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--gold);
  margin-right: auto;
}}
.header-duration {{
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: var(--text-muted);
}}

/* ── Container ── */
.container {{
  max-width: 820px;
  margin: 0 auto;
  padding: 0 1.25rem;
}}

/* ── Game meta grid ── */
.meta-grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  margin: 1.5rem 0;
  background: var(--surface);
}}
.meta-cell {{
  padding: 0.9rem 1rem;
  border-right: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}}
.meta-cell:nth-child(3n) {{ border-right: none; }}
.meta-cell:nth-last-child(-n+3) {{ border-bottom: none; }}
.meta-label {{
  font-size: 0.65rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-muted);
}}
.meta-value {{
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text);
}}

/* ── Player matchup strip ── */
.matchup {{
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 1rem;
  align-items: center;
  margin-bottom: 2rem;
}}
.player-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 1rem 1.25rem;
}}
.player-card.focus {{ border-color: var(--blue); box-shadow: 0 0 0 1px rgba(82,153,224,0.2); }}
.player-card.opp   {{ border-color: var(--red);  box-shadow: 0 0 0 1px rgba(224,82,82,0.2); }}
.player-name {{
  font-size: 1rem;
  font-weight: 700;
  margin-bottom: 0.2rem;
}}
.focus .player-name {{ color: var(--blue); }}
.opp   .player-name {{ color: var(--red); }}
.player-civ {{
  font-size: 0.8rem;
  color: var(--gold);
  margin-bottom: 0.75rem;
}}
.pstat {{ display: flex; justify-content: space-between; gap: 1rem; margin-top: 0.3rem; }}
.pstat-label {{ font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}
.pstat-value {{ font-family: var(--font-mono); font-size: 0.82rem; color: var(--text); }}
.badge {{
  display: inline-block;
  padding: 0.15rem 0.6rem;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-top: 0.6rem;
}}
.badge-win  {{ background: rgba(82,200,120,0.15); color: var(--green); border: 1px solid rgba(82,200,120,0.3); }}
.badge-loss {{ background: rgba(224,82,82,0.12);  color: var(--red);   border: 1px solid rgba(224,82,82,0.25); }}
.vs-badge {{
  font-size: 1.1rem;
  font-weight: 800;
  color: var(--text-muted);
  text-align: center;
  user-select: none;
}}

/* ── Section heading ── */
.section-heading {{
  font-size: 0.7rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--gold);
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--gold-dim);
  margin-bottom: 1.25rem;
  margin-top: 2.5rem;
}}

/* ── Coaching cards ── */
.coaching-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--card-color, var(--gold));
  border-radius: var(--radius-lg);
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.25rem;
  position: relative;
}}
.card-title {{
  font-size: 0.72rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--card-color, var(--gold));
  margin-bottom: 0.9rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}}
.card-icon {{
  font-size: 1rem;
  line-height: 1;
}}
.card-body p {{ margin-bottom: 0.65rem; color: var(--text); font-size: 0.93rem; line-height: 1.65; }}
.card-body p:last-child {{ margin-bottom: 0; }}
.card-body ul {{ margin: 0.5rem 0 0.65rem 1.25rem; }}
.card-body li {{ margin-bottom: 0.35rem; font-size: 0.93rem; line-height: 1.65; }}
.card-body strong {{ color: var(--text); font-weight: 700; }}

/* Timestamps ── styled inline chips */
.timestamp {{
  font-family: var(--font-mono);
  font-size: 0.82em;
  background: rgba(200,162,44,0.12);
  color: var(--gold);
  border: 1px solid rgba(200,162,44,0.25);
  border-radius: 3px;
  padding: 0.05em 0.35em;
  white-space: nowrap;
}}

/* ── Economy panel (collapsible) ── */
details.data-panel {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  margin-top: 2rem;
  overflow: hidden;
}}
details.data-panel summary {{
  padding: 0.9rem 1.25rem;
  cursor: pointer;
  user-select: none;
  font-size: 0.7rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text-muted);
  list-style: none;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}}
details.data-panel summary::-webkit-details-marker {{ display: none; }}
details.data-panel summary::before {{
  content: "▶";
  font-size: 0.6rem;
  transition: transform 0.2s;
}}
details[open].data-panel summary::before {{ transform: rotate(90deg); }}
.data-panel-body {{ padding: 0 1.25rem 1.25rem; }}
.chart-legend {{
  display: flex;
  gap: 1.5rem;
  margin-bottom: 0.75rem;
  font-size: 0.75rem;
  color: var(--text-muted);
}}
.legend-dot {{
  width: 10px; height: 10px;
  border-radius: 50%;
  display: inline-block;
  margin-right: 0.35rem;
  vertical-align: middle;
}}
.chart-note {{
  font-size: 0.7rem;
  color: var(--text-muted);
  margin-top: 0.5rem;
}}
</style>
</head>
<body>

<header class="report-header">
  <span class="header-brand">AoE2 Zeus &mdash; Coaching Report</span>
  <span class="header-duration">{html_mod.escape(map_info['name'])} &nbsp;&#183;&nbsp; {html_mod.escape(game_data['duration'])}</span>
</header>

<div class="container">

  <!-- Game metadata grid -->
  <div class="meta-grid">
    {meta_cell("Map", html_mod.escape(map_info["name"]))}
    {meta_cell("Size", html_mod.escape(map_info["size"]))}
    {meta_cell("Duration", game_data["duration"])}
    {meta_cell("Population", "200")}
    {meta_cell("Speed", "Normal")}
    {meta_cell("Victory", "Conquest")}
  </div>

  <!-- Player matchup strip -->
  <div class="matchup">
    <div class="player-card focus">
      <div class="player-name">{html_mod.escape(focus["name"])}</div>
      <div class="player-civ">{html_mod.escape(focus_civ)}</div>
      {player_stat("eAPM", str(focus.get("eapm", "—")))}
      {player_stat("Feudal", focus_feudal)}
      {player_stat("Castle", focus_castle) if focus_castle != "—" else ""}
      <div><span class="badge {focus_result_cls}">{focus_result_txt}</span></div>
    </div>
    <div class="vs-badge">VS</div>
    <div class="player-card opp">
      <div class="player-name">{html_mod.escape(opp["name"])}</div>
      <div class="player-civ">{html_mod.escape(opp_civ)}</div>
      {player_stat("eAPM", str(opp.get("eapm", "—")))}
      {player_stat("Feudal", opp_feudal)}
      {player_stat("Castle", opp_castle) if opp_castle != "—" else ""}
      <div><span class="badge {opp_result_cls}">{opp_result_txt}</span></div>
    </div>
  </div>

  <!-- Coaching report cards (hero section) -->
  <p class="section-heading">Coaching Report</p>
  {"".join(section_cards)}

  <!-- Economy data panel (collapsible) -->
  <details class="data-panel">
    <summary>Economy Timeline</summary>
    <div class="data-panel-body">
      <div class="chart-legend">
        <span>
          <span class="legend-dot" style="background:var(--blue)"></span>
          {html_mod.escape(focus["name"])}
        </span>
        <span>
          <span class="legend-dot" style="background:var(--red)"></span>
          {html_mod.escape(opp["name"])}
        </span>
        <span style="color:#e05252;font-size:0.68rem">&#9644; TC idle (your slots)</span>
      </div>
      {svg}
      <p class="chart-note">Total resources (food + wood + gold + stone) per minute. Dashed verticals = age-ups.</p>
    </div>
  </details>

</div>
</body>
</html>"""
