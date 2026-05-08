import React, { useRef, useEffect, useState, useCallback } from 'react'

const TERRAIN_RGB = {
  0:   [56,  120, 28],
  1:   [20,  60,  160],
  2:   [24,  70,  180],
  3:   [180, 160, 100],
  4:   [210, 185, 120],
  5:   [200, 190, 140],
  7:   [180, 160, 90],
  8:   [220, 210, 170],
  9:   [195, 175, 110],
  13:  [240, 230, 200],
  14:  [220, 215, 195],
  18:  [52,  110, 28],
  24:  [28,  90,  20],
  34:  [200, 185, 145],
  38:  [170, 150, 90],
  46:  [30,  110, 35],
  77:  [40,  100, 25],
  113: [128, 108, 72],
}
const DEFAULT_RGB = [60, 120, 30]

// Exact AoE2 player color palette (matches reference minimap generator)
const PLAYER_COLORS = ['#0000DD', '#ff0000', '#00ff00', '#ffff00', '#00ffff', '#ff00ff', '#E9E9E9', '#ff8201']

// Resolve player color: use color_id if 0-7, else pick next unused from palette
function resolveColors(players) {
  const out = {}
  const used = new Set()
  // First pass: valid color_ids
  for (const [pid, p] of Object.entries(players)) {
    if (p.color_id >= 0 && p.color_id <= 7) {
      out[pid] = PLAYER_COLORS[p.color_id]
      used.add(p.color_id)
    }
  }
  // Second pass: fallback — assign next unused palette entry
  let next = 0
  for (const [pid] of Object.entries(players)) {
    if (!out[pid]) {
      while (used.has(next)) next++
      out[pid] = PLAYER_COLORS[next] ?? '#aaaaaa'
      used.add(next++)
    }
  }
  return out
}

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return [r, g, b]
}

function buildTerrainImageData(terrain, elevation, dim, scale) {
  const canvas = document.createElement('canvas')
  canvas.width = dim * scale
  canvas.height = dim * scale
  const ctx = canvas.getContext('2d')
  const img = ctx.createImageData(dim * scale, dim * scale)
  for (let y = 0; y < dim; y++) {
    for (let x = 0; x < dim; x++) {
      const tid = terrain[y * dim + x]
      const elev = elevation[y * dim + x]
      const [r, g, b] = TERRAIN_RGB[tid] ?? DEFAULT_RGB
      const f = 1 - elev * 0.07
      const fr = Math.max(0, Math.min(255, Math.round(r * f)))
      const fg = Math.max(0, Math.min(255, Math.round(g * f)))
      const fb = Math.max(0, Math.min(255, Math.round(b * f)))
      for (let sy = 0; sy < scale; sy++) {
        for (let sx = 0; sx < scale; sx++) {
          const idx = ((y * scale + sy) * dim * scale + (x * scale + sx)) * 4
          img.data[idx]     = fr
          img.data[idx + 1] = fg
          img.data[idx + 2] = fb
          img.data[idx + 3] = 255
        }
      }
    }
  }
  ctx.putImageData(img, 0, 0)
  return canvas
}

const TRAIL_WINDOW_S = 45

function fmtTime(s) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

export default function Minimap({ data, currentTimeS, onTimeChange, durationS }) {
  const canvasRef = useRef(null)
  const offscreenRef = useRef(null)
  const rafRef = useRef(null)
  const lastRealTsRef = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(15)

  const dim = data?.dim ?? 120
  const SCALE = Math.floor(480 / dim)

  // Pre-render terrain to offscreen canvas when data changes
  useEffect(() => {
    if (!data || !data.terrain || !data.elevation) return
    offscreenRef.current = buildTerrainImageData(data.terrain, data.elevation, dim, SCALE)
  }, [data, dim, SCALE])

  // Animation loop
  useEffect(() => {
    if (!playing) {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      lastRealTsRef.current = null
      return
    }

    function tick(realTs) {
      if (lastRealTsRef.current === null) {
        lastRealTsRef.current = realTs
      }
      const dtReal = (realTs - lastRealTsRef.current) / 1000
      lastRealTsRef.current = realTs

      onTimeChange(prev => {
        const next = prev + dtReal * speed
        if (next >= durationS) {
          setPlaying(false)
          return durationS
        }
        return next
      })

      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [playing, speed, durationS, onTimeChange])

  // Draw frame
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !data) return
    const ctx = canvas.getContext('2d')
    const w = dim * SCALE
    const h = dim * SCALE

    // Clear
    ctx.clearRect(0, 0, w, h)

    // Terrain
    if (offscreenRef.current) {
      ctx.drawImage(offscreenRef.current, 0, 0)
    } else {
      ctx.fillStyle = '#1a2a10'
      ctx.fillRect(0, 0, w, h)
    }

    // Resources — sized to be clearly visible
    const RES_STYLE = {
      gold:    { color: '#f0d020', size: 5 },
      stone:   { color: '#c8c8c8', size: 5 },
      tree:    { color: '#1a5010', size: 2 },
      hunt:    { color: '#c89858', size: 4 },
      deer:    { color: '#c89858', size: 4 },
      boar:    { color: '#e07018', size: 4 },
      berries: { color: '#d04888', size: 4 },
      fish:    { color: '#4888cc', size: 3 },
    }

    if (data.resources) {
      for (const res of data.resources) {
        const rx = res.x * w
        const ry = res.y * h
        const key = (res.type || '').toLowerCase()
        const style = RES_STYLE[key] ?? { color: '#888', size: 3 }
        ctx.fillStyle = style.color
        ctx.fillRect(rx - style.size / 2, ry - style.size / 2, style.size, style.size)
      }
    }

    // Player buildings and activity
    const players = data.players || {}
    const colorMap = resolveColors(players)
    for (const [pid, pdata] of Object.entries(players)) {
      const color = colorMap[pid]
      const [cr, cg, cb] = hexToRgb(color)

      // ── Connected movement trail ──────────────────────────────────────────
      // Collect activity events in the trailing window, sorted oldest→newest
      const trail = (pdata.activity || []).filter(a => {
        if (!a.pos) return false
        const age = currentTimeS - (a.time_s ?? 0)
        return age >= 0 && age <= TRAIL_WINDOW_S
      })

      if (trail.length > 1) {
        ctx.beginPath()
        ctx.moveTo(trail[0].pos.x * w, trail[0].pos.y * h)
        for (let i = 1; i < trail.length; i++) {
          ctx.lineTo(trail[i].pos.x * w, trail[i].pos.y * h)
        }
        ctx.strokeStyle = `rgba(${cr},${cg},${cb},0.85)`
        ctx.lineWidth = 3
        ctx.lineJoin = 'round'
        ctx.lineCap = 'round'
        ctx.stroke()

        // Dot at the current head position (most recent event)
        const head = trail[trail.length - 1]
        ctx.beginPath()
        ctx.arc(head.pos.x * w, head.pos.y * h, 5, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.fill()
        ctx.strokeStyle = 'rgba(255,255,255,0.6)'
        ctx.lineWidth = 1.5
        ctx.stroke()
      }

      // ── Buildings placed up to currentTimeS ───────────────────────────────
      if (pdata.buildings) {
        for (const bld of pdata.buildings) {
          if (!bld.pos || (bld.time_s ?? 0) > currentTimeS) continue
          const bx = bld.pos.x * w
          const by = bld.pos.y * h
          ctx.fillStyle = `rgba(${cr},${cg},${cb},0.9)`
          ctx.fillRect(bx - 4, by - 4, 8, 8)
        }
      }

      // ── TC marker: filled circle + outline ring (reference style) ────────
      if (pdata.tc) {
        const tx = pdata.tc.x * w
        const ty = pdata.tc.y * h
        // Filled centre
        ctx.beginPath()
        ctx.arc(tx, ty, 6, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.fill()
        // Outer ring
        ctx.beginPath()
        ctx.arc(tx, ty, 11, 0, Math.PI * 2)
        ctx.strokeStyle = color
        ctx.lineWidth = 3
        ctx.stroke()
        // White dot at centre
        ctx.beginPath()
        ctx.arc(tx, ty, 2, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(255,255,255,0.9)'
        ctx.fill()
      }
    }
  }, [data, currentTimeS, dim, SCALE])

  const handleScrub = useCallback((e) => {
    const val = parseFloat(e.target.value)
    onTimeChange(val)
  }, [onTimeChange])

  const handleReset = useCallback(() => {
    setPlaying(false)
    onTimeChange(0)
  }, [onTimeChange])

  const handlePlayPause = useCallback(() => {
    setPlaying(p => {
      if (!p && currentTimeS >= durationS) {
        onTimeChange(0)
      }
      return !p
    })
  }, [currentTimeS, durationS, onTimeChange])

  return (
    <div className="minimap-section">
      <div className="section-header">Battlefield Map</div>
      <div className="minimap-frame">
        <div className="minimap-canvas-wrap">
          <canvas
            ref={canvasRef}
            width={dim * SCALE}
            height={dim * SCALE}
          />
        </div>
      </div>
      <div className="minimap-controls">
        <input
          type="range"
          className="minimap-scrubber"
          min={0}
          max={durationS}
          step={1}
          value={Math.round(currentTimeS)}
          onChange={handleScrub}
        />
        <div className="minimap-btn-row">
          <button className="ctrl-btn" onClick={handleReset} title="Reset to start">
            &#9198;
          </button>
          <button className="ctrl-btn" onClick={handlePlayPause} title={playing ? 'Pause' : 'Play'}>
            {playing ? '⏸' : '▶'}
          </button>
          <span className="minimap-time-display">{fmtTime(Math.round(currentTimeS))}</span>
          <select
            className="speed-select"
            value={speed}
            onChange={e => setSpeed(Number(e.target.value))}
          >
            <option value={5}>5×</option>
            <option value={15}>15×</option>
            <option value={30}>30×</option>
            <option value={60}>60×</option>
          </select>
        </div>
      </div>
    </div>
  )
}
