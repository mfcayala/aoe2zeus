import React, { useMemo } from 'react'

const CHART_W = 680
const CHART_H = 160
const PAD_L = 44
const PAD_R = 12
const PAD_T = 14
const PAD_B = 28

function fmtTime(s) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

// Parse "MM:SS" or return numeric value as-is
function tsToS(val) {
  if (typeof val === 'number') return val
  if (typeof val === 'string' && val.includes(':')) {
    const [m, s] = val.split(':').map(Number)
    return m * 60 + s
  }
  return parseFloat(val) || 0
}

export default function EconomyChart({
  economyTimeline,
  uptimeEvents,
  coachingData,
  focusId,
  currentTimeS,
  durationS,
  playerNames,
}) {
  const plotW = CHART_W - PAD_L - PAD_R
  const plotH = CHART_H - PAD_T - PAD_B

  // Collect all player IDs
  const playerIds = useMemo(() => Object.keys(economyTimeline || {}), [economyTimeline])

  // Determine max resource value for Y axis
  const maxRes = useMemo(() => {
    let m = 100
    for (const pid of playerIds) {
      const points = economyTimeline[pid] || []
      for (const pt of points) {
        if ((pt.total_res || 0) > m) m = pt.total_res
      }
    }
    return m * 1.08
  }, [economyTimeline, playerIds])

  function xOf(timeS) {
    return PAD_L + (timeS / (durationS || 1)) * plotW
  }
  function yOf(val) {
    return PAD_T + plotH - (val / maxRes) * plotH
  }

  // Build polyline points for each player
  const polylines = useMemo(() => {
    return playerIds.map(pid => {
      const points = economyTimeline[pid] || []
      const pts = points
        .filter(pt => (pt.time_s != null || pt.time != null) && pt.total_res != null)
        .map(pt => `${xOf(tsToS(pt.time_s ?? pt.time))},${yOf(pt.total_res)}`)
        .join(' ')
      return { pid, pts }
    })
  }, [economyTimeline, playerIds, durationS, maxRes])

  // TC idle bands from coaching_data — data uses {start, end} MM:SS strings
  const idleBands = useMemo(() => {
    if (!coachingData || !focusId) return []
    const cd = coachingData[String(focusId)] || coachingData
    const tcIdle = cd.tc_idle_periods || []
    const bands = []
    for (const period of tcIdle) {
      const x1 = xOf(tsToS(period.start_s ?? period.start))
      const x2 = xOf(tsToS(period.end_s ?? period.end))
      bands.push({ x: x1, w: Math.max(x2 - x1, 1) })
    }
    return bands
  }, [coachingData, focusId, durationS])

  // Age-up events — data uses {time: "MM:SS", age: "Age.FEUDAL_AGE", player: name}
  const ageUpLines = useMemo(() => {
    if (!uptimeEvents) return []
    const lines = []
    for (const ev of uptimeEvents) {
      const t = ev.time_s ?? ev.time
      if (t == null) continue
      const x = xOf(tsToS(t))
      const ageStr = (ev.age || ev.event || '').toLowerCase()
      let color = '#888'
      if (ageStr.includes('feudal'))   color = '#c8a020'
      else if (ageStr.includes('castle'))   color = '#8844cc'
      else if (ageStr.includes('imperial')) color = '#cc2222'
      const label = (ev.age || '').replace('Age.', '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).split(' ')[0]
      lines.push({ x, color, label, pid: ev.player })
    }
    return lines
  }, [uptimeEvents, durationS])

  // Player colors
  function playerColor(pid) {
    const isFocus = String(pid) === String(focusId)
    return isFocus ? '#4488ee' : '#ee4444'
  }

  // Y axis ticks
  const yTicks = useMemo(() => {
    const count = 4
    const ticks = []
    for (let i = 0; i <= count; i++) {
      const val = (maxRes / count) * i
      ticks.push({ val: Math.round(val), y: yOf(val) })
    }
    return ticks
  }, [maxRes])

  // X axis ticks
  const xTicks = useMemo(() => {
    const tickEvery = durationS > 1200 ? 300 : 120
    const ticks = []
    for (let t = 0; t <= durationS; t += tickEvery) {
      ticks.push({ t, x: xOf(t) })
    }
    return ticks
  }, [durationS])

  // Cursor
  const cursorX = xOf(Math.min(currentTimeS, durationS))

  if (!economyTimeline || playerIds.length === 0) {
    return (
      <div className="economy-section">
        <div className="section-header">Economy Timeline</div>
        <p style={{ color: 'var(--text-dim)', fontSize: '0.82rem', textAlign: 'center', padding: '12px' }}>
          No economy data available.
        </p>
      </div>
    )
  }

  return (
    <div className="economy-section">
      <div className="section-header">Economy Timeline</div>
      <div className="economy-chart-wrap">
        <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} xmlns="http://www.w3.org/2000/svg">
          {/* Background */}
          <rect x={PAD_L} y={PAD_T} width={plotW} height={plotH}
            fill="#0a0806" stroke="#2e2010" strokeWidth="1" />

          {/* TC Idle bands */}
          {idleBands.map((b, i) => (
            <rect key={i} x={b.x} y={PAD_T} width={b.w} height={plotH}
              fill="rgba(220,32,32,0.12)" />
          ))}

          {/* Y gridlines */}
          {yTicks.map((tk, i) => (
            <g key={i}>
              <line x1={PAD_L} x2={PAD_L + plotW} y1={tk.y} y2={tk.y}
                stroke="#2e2010" strokeWidth="1" strokeDasharray="3,4" />
              <text x={PAD_L - 4} y={tk.y + 4} textAnchor="end"
                fill="#5a4a30" fontSize="9" fontFamily="Georgia,serif">
                {tk.val >= 1000 ? `${(tk.val / 1000).toFixed(1)}k` : tk.val}
              </text>
            </g>
          ))}

          {/* X axis ticks */}
          {xTicks.map((tk, i) => (
            <g key={i}>
              <line x1={tk.x} x2={tk.x} y1={PAD_T + plotH} y2={PAD_T + plotH + 4}
                stroke="#5a3e18" strokeWidth="1" />
              <text x={tk.x} y={PAD_T + plotH + 13} textAnchor="middle"
                fill="#5a4a30" fontSize="9" fontFamily="Georgia,serif">
                {fmtTime(tk.t)}
              </text>
            </g>
          ))}

          {/* Age-up dashed lines */}
          {ageUpLines.map((ln, i) => (
            <g key={i}>
              <line x1={ln.x} x2={ln.x} y1={PAD_T} y2={PAD_T + plotH}
                stroke={ln.color} strokeWidth="1.2" strokeDasharray="4,3" opacity="0.7" />
              <text x={ln.x + 2} y={PAD_T + 10} fill={ln.color}
                fontSize="8" fontFamily="Georgia,serif" opacity="0.9">
                {ln.label}
              </text>
            </g>
          ))}

          {/* Player polylines */}
          {polylines.map(({ pid, pts }) => {
            const isFocus = String(pid) === String(focusId)
            return (
              <polyline key={pid}
                points={pts}
                fill="none"
                stroke={playerColor(pid)}
                strokeWidth={isFocus ? 2 : 1.5}
                strokeLinejoin="round"
                opacity={isFocus ? 0.9 : 0.65}
              />
            )
          })}

          {/* Cursor */}
          <line x1={cursorX} x2={cursorX} y1={PAD_T} y2={PAD_T + plotH}
            stroke="#e8c840" strokeWidth="1.5" opacity="0.85" />

          {/* Legend */}
          {playerIds.map((pid, i) => {
            const name = (playerNames && playerNames[pid]) || `Player ${pid}`
            const col = playerColor(pid)
            const lx = PAD_L + 8 + i * 160
            return (
              <g key={pid}>
                <rect x={lx} y={PAD_T + 4} width={20} height={3} fill={col} rx="1" />
                <text x={lx + 24} y={PAD_T + 10} fill={col}
                  fontSize="9" fontFamily="Georgia,serif">
                  {name}
                </text>
              </g>
            )
          })}

          {/* Axis label */}
          <text x={PAD_L - 30} y={PAD_T + plotH / 2} fill="#5a4a30"
            fontSize="9" fontFamily="Georgia,serif"
            transform={`rotate(-90, ${PAD_L - 30}, ${PAD_T + plotH / 2})`}
            textAnchor="middle">
            Total Resources
          </text>
        </svg>
      </div>
    </div>
  )
}
