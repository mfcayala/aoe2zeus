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

// AoE2 player color palette indexed by color_id
const PLAYER_COLORS = {
  0: '#0050e0',
  1: '#e01818',
  2: '#18c818',
  3: '#e0c818',
  4: '#18d8d8',
  5: '#8018c8',
  6: '#e07818',
  7: '#e07818',
}

function getPlayerColor(colorId) {
  return PLAYER_COLORS[colorId] ?? PLAYER_COLORS[colorId % 8] ?? '#aaaaaa'
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

    // Resources
    const resourceColors = {
      gold:     '#f0d020',
      stone:    '#aaaaaa',
      tree:     '#1a4a10',
      trees:    '#1a4a10',
      forest:   '#1a4a10',
      hunt:     '#c8a878',
      deer:     '#c8a878',
      boar:     '#e08020',
      berries:  '#e060a0',
      berry:    '#e060a0',
      fish:     '#4888cc',
    }

    if (data.resources) {
      for (const res of data.resources) {
        const rx = res.x * w
        const ry = res.y * h
        const resType = (res.type || '').toLowerCase()
        let color = '#888'
        let size = 2
        for (const [key, val] of Object.entries(resourceColors)) {
          if (resType.includes(key)) { color = val; break }
        }
        if (resType.includes('tree') || resType.includes('forest')) size = 1
        ctx.fillStyle = color
        ctx.fillRect(rx - size / 2, ry - size / 2, size, size)
      }
    }

    // Player buildings and activity
    const players = data.players || {}
    for (const [pid, pdata] of Object.entries(players)) {
      const color = getPlayerColor(pdata.color_id)
      const [cr, cg, cb] = hexToRgb(color)

      // Activity trail (within last TRAIL_WINDOW_S of currentTimeS)
      if (pdata.activity) {
        for (const act of pdata.activity) {
          if (!act.pos) continue
          const ats = act.time_s ?? 0
          const age = currentTimeS - ats
          if (age < 0 || age > TRAIL_WINDOW_S) continue
          const opacity = (1 - age / TRAIL_WINDOW_S) * 0.75
          const ax = act.pos.x * w
          const ay = act.pos.y * h
          ctx.beginPath()
          ctx.arc(ax, ay, 2, 0, Math.PI * 2)
          ctx.fillStyle = `rgba(${cr},${cg},${cb},${opacity})`
          ctx.fill()
        }
      }

      // Buildings placed up to currentTimeS
      if (pdata.buildings) {
        for (const bld of pdata.buildings) {
          if (!bld.pos) continue
          if ((bld.time_s ?? 0) > currentTimeS) continue
          const bx = bld.pos.x * w
          const by = bld.pos.y * h
          ctx.fillStyle = `rgba(${cr},${cg},${cb},0.8)`
          ctx.fillRect(bx - 2, by - 2, 4, 4)
        }
      }

      // TC marker — always visible
      if (pdata.tc) {
        const tx = pdata.tc.x * w
        const ty = pdata.tc.y * h
        // White border
        ctx.fillStyle = 'rgba(255,255,255,0.9)'
        ctx.fillRect(tx - 4, ty - 4, 8, 8)
        // Player color fill
        ctx.fillStyle = color
        ctx.fillRect(tx - 3, ty - 3, 6, 6)
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
