import React, { useState, useEffect, useCallback, useMemo } from 'react'
import Minimap from './components/Minimap.jsx'
import CoachingCard from './components/CoachingCard.jsx'
import EconomyChart from './components/EconomyChart.jsx'

// Base64 → Uint8Array
function b64(s) {
  return Uint8Array.from(atob(s), c => c.charCodeAt(0))
}

// Format seconds as M:SS
function fmtDuration(s) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

// AoE2 player color palette by color_id
const PLAYER_COLOR_HEX = {
  0: '#0050e0',
  1: '#e01818',
  2: '#18c818',
  3: '#e0c818',
  4: '#18d8d8',
  5: '#8018c8',
  6: '#e07818',
  7: '#e07818',
}

function getPlayerAccent(colorId) {
  return PLAYER_COLOR_HEX[colorId] ?? '#a07828'
}

// Parse coaching markdown into named sections
function parseCoachingText(text) {
  const sections = {}
  let currentKey = null
  let currentLines = []
  const SECTION_MAP = [
    ['The Decisive Moment', 'decisive'],
    ['What You Should Have Done', 'action'],
    ['What Led You There', 'macro'],
    ['Civ Matchup', 'matchup'],
    ['Top 3 Things To Fix', 'fixes'],
  ]

  for (const line of text.split('\n')) {
    if (line.startsWith('## ')) {
      if (currentKey) sections[currentKey] = currentLines.join('\n').trim()
      const heading = line.slice(3).trim()
      currentKey = null
      for (const [title, key] of SECTION_MAP) {
        if (
          heading.toLowerCase().includes(title.toLowerCase()) ||
          title.toLowerCase().includes(heading.toLowerCase())
        ) {
          currentKey = key
          break
        }
      }
      if (!currentKey) currentKey = `unknown_${Object.keys(sections).length}`
      currentLines = []
    } else {
      currentLines.push(line)
    }
  }
  if (currentKey) sections[currentKey] = currentLines.join('\n').trim()
  return sections
}

const CARD_CONFIG = [
  {
    key: 'decisive',
    title: 'The Decisive Moment',
    icon: '⚔',
    color: '#e04040',
  },
  {
    key: 'action',
    title: 'What You Should Have Done',
    icon: '🎯',
    color: '#e09020',
  },
  {
    key: 'macro',
    title: 'What Led You There',
    icon: '📜',
    color: '#a07828',
  },
  {
    key: 'matchup',
    title: 'Civ Matchup',
    icon: '🛡',
    color: '#5080c0',
  },
  {
    key: 'fixes',
    title: 'Top 3 Things To Fix',
    icon: '🔨',
    color: '#40a840',
  },
]

// Determine which player is the "focus" (loser, or first player listed)
function getFocusPlayer(players) {
  if (!players) return null
  const entries = Object.entries(players)
  // Prefer the loser
  const loser = entries.find(([, p]) => p.winner === false || p.winner === 0)
  if (loser) return loser[0]
  return entries[0]?.[0] ?? null
}

export default function App() {
  const [rawData, setRawData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [currentTimeS, setCurrentTimeS] = useState(0)

  useEffect(() => {
    fetch('/data.json')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
        return res.json()
      })
      .then(json => {
        setRawData(json)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  const handleTimeChange = useCallback((valOrFn) => {
    setCurrentTimeS(valOrFn)
  }, [])

  const handleTimeJump = useCallback((s) => {
    setCurrentTimeS(s)
  }, [])

  // Decoded minimap data (memoized so we don't re-decode on every render)
  const minimapData = useMemo(() => {
    if (!rawData?.minimap) return null
    const mm = rawData.minimap
    try {
      return {
        ...mm,
        terrain: b64(mm.terrain_b64),
        elevation: b64(mm.elevation_b64),
      }
    } catch (e) {
      console.error('Failed to decode minimap base64:', e)
      return { ...mm, terrain: new Uint8Array(mm.dim * mm.dim), elevation: new Uint8Array(mm.dim * mm.dim) }
    }
  }, [rawData])

  const coachingSections = useMemo(() => {
    if (!rawData?.coaching) return {}
    return parseCoachingText(rawData.coaching)
  }, [rawData])

  if (loading) {
    return (
      <div className="loading-screen">
        <p>Loading Coaching Report...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="error-screen">
        <h2>Failed to Load Report</h2>
        <p>{error}</p>
      </div>
    )
  }

  const game = rawData.game || {}
  const mapInfo = game.map || {}
  const gamePlayers = game.players || {}
  const durationS = minimapData?.duration_s ?? game.duration_s ?? 0
  const uptimeEvents = game.uptime_events || []
  const coachingData = game.coaching_data || {}
  const economyTimeline = game.economy_timeline || {}

  const focusId = getFocusPlayer(gamePlayers)

  // Build player name map for EconomyChart
  const playerNames = useMemo(() => {
    const names = {}
    for (const [pid, pdata] of Object.entries(gamePlayers)) {
      names[pid] = pdata.name || `Player ${pid}`
    }
    return names
  }, [gamePlayers])

  // Map/duration display
  const mapName = mapInfo.name || 'Unknown Map'
  const mapSize = mapInfo.size || (mapInfo.dimension ? `${mapInfo.dimension}×${mapInfo.dimension}` : '')
  const durationDisplay = game.duration || fmtDuration(durationS)
  const gameDate = game.date || ''

  return (
    <div>
      {/* Banner */}
      <div className="game-banner">
        <div className="banner-title">
          AoE2 Zeus
          <span>Coaching Report</span>
        </div>
        <div className="banner-meta">
          <strong>{mapName}</strong>
          {mapSize ? ` · ${mapSize}` : ''}
          {durationDisplay ? ` · ${durationDisplay}` : ''}
          {gameDate ? ` · ${gameDate}` : ''}
        </div>
      </div>

      <div className="page-wrap">
        {/* Player Row */}
        <div className="player-row">
          {Object.entries(gamePlayers).map(([pid, pdata]) => {
            const isWinner = pdata.winner === true || pdata.winner === 1
            const colorId = pdata.color_id ?? (pid === '1' ? 0 : 1)
            const accent = getPlayerAccent(colorId)
            return (
              <div
                key={pid}
                className="player-card"
                style={{ '--player-accent': accent }}
              >
                <div className="player-card-top">
                  <span className="player-name">{pdata.name || `Player ${pid}`}</span>
                  <span className={`badge ${isWinner ? 'badge-win' : 'badge-loss'}`}>
                    {isWinner ? 'WIN' : 'LOSS'}
                  </span>
                </div>
                <div className="player-civ">{pdata.civilization || pdata.civ || 'Unknown Civ'}</div>
                {pdata.eapm != null && (
                  <div className="player-eapm">
                    eAPM: <strong>{typeof pdata.eapm === 'number' ? pdata.eapm.toFixed(1) : pdata.eapm}</strong>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Main two-column layout */}
        <div className="main-layout">
          {/* Left: Minimap */}
          <div className="panel">
            {minimapData ? (
              <Minimap
                data={minimapData}
                currentTimeS={currentTimeS}
                onTimeChange={handleTimeChange}
                durationS={durationS}
              />
            ) : (
              <div style={{ textAlign: 'center', color: 'var(--text-dim)', padding: '40px 0' }}>
                No minimap data available.
              </div>
            )}
          </div>

          {/* Right: Coaching cards + economy chart */}
          <div className="right-column">
            <div className="panel coaching-column">
              {CARD_CONFIG.map(cfg => {
                const content = coachingSections[cfg.key]
                if (!content) return null
                return (
                  <CoachingCard
                    key={cfg.key}
                    sectionKey={cfg.key}
                    title={cfg.title}
                    icon={cfg.icon}
                    color={cfg.color}
                    content={content}
                    currentTimeS={currentTimeS}
                    onTimeJump={handleTimeJump}
                  />
                )
              })}
              {Object.keys(coachingSections).length === 0 && (
                <p style={{ color: 'var(--text-dim)', fontSize: '0.88rem', padding: '8px 0' }}>
                  No coaching analysis available.
                </p>
              )}
            </div>

            <div className="panel">
              <EconomyChart
                economyTimeline={economyTimeline}
                uptimeEvents={uptimeEvents}
                coachingData={coachingData}
                focusId={focusId}
                currentTimeS={currentTimeS}
                durationS={durationS}
                playerNames={playerNames}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
