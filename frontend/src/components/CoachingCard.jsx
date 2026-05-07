import React, { useMemo } from 'react'

function extractTimestamps(text) {
  return [...text.matchAll(/\b(\d{1,2}:\d{2})\b/g)].map(m => {
    const [min, sec] = m[1].split(':').map(Number)
    return min * 60 + sec
  })
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function mdToHtml(text, onTimeJump) {
  if (!text) return ''

  const lines = text.split('\n')
  const output = []
  let inList = false

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i]

    // Blank line — close list and add paragraph break
    if (raw.trim() === '') {
      if (inList) {
        output.push('</ul>')
        inList = false
      }
      continue
    }

    // List item
    if (/^[\-•]\s/.test(raw.trim())) {
      if (!inList) {
        output.push('<ul>')
        inList = true
      }
      output.push('<li>' + formatInline(raw.trim().replace(/^[\-•]\s/, '')) + '</li>')
      continue
    }

    // Regular line
    if (inList) {
      output.push('</ul>')
      inList = false
    }
    output.push('<p>' + formatInline(raw) + '</p>')
  }

  if (inList) output.push('</ul>')

  return output.join('\n')
}

function formatInline(text) {
  // Escape HTML first
  let out = escapeHtml(text)

  // Timestamps → clickable chips (before bold/italic so ** doesn't interfere)
  out = out.replace(/\b(\d{1,2}:\d{2})\b/g, (match, ts) => {
    const [min, sec] = ts.split(':').map(Number)
    const s = min * 60 + sec
    return `<span class="ts-chip" data-s="${s}">${ts}</span>`
  })

  // **bold**
  out = out.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

  // *italic*
  out = out.replace(/\*([^*]+?)\*/g, '<em>$1</em>')

  return out
}

export default function CoachingCard({ sectionKey, title, icon, color, content, currentTimeS, onTimeJump }) {
  const timestamps = useMemo(() => extractTimestamps(content || ''), [content])

  const isActive = useMemo(() => {
    return timestamps.some(ts => Math.abs(ts - currentTimeS) <= 90)
  }, [timestamps, currentTimeS])

  const htmlContent = useMemo(() => mdToHtml(content || '', onTimeJump), [content])

  function handleCardClick(e) {
    const chip = e.target.closest('.ts-chip')
    if (chip) {
      const s = parseInt(chip.dataset.s, 10)
      if (!isNaN(s)) onTimeJump(s)
    }
  }

  return (
    <div
      className={`coaching-card${isActive ? ' card-active' : ''}`}
      data-card-key={sectionKey}
      style={{ '--card-color': color }}
      onClick={handleCardClick}
    >
      <div className="card-header">
        <span className="card-icon">{icon}</span>
        <span className="card-title">{title}</span>
      </div>
      <div
        className="card-body"
        dangerouslySetInnerHTML={{ __html: htmlContent }}
      />
    </div>
  )
}
