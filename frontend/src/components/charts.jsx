/* Dependency-free SVG charts: area/line, bar list, donut, sparkline. */
import { useId, useState } from 'react'

const W = 600
const PAD = 8

/** `data` is a list of numbers; `labels` (same length) names each point for the axis and the hover readout. */
export function AreaChart({ data = [], labels = [], height = 180, color = 'var(--primary)', label, emptyText = 'No activity in this period' }) {
  const gid = useId()
  const [hover, setHover] = useState(null)

  if (!data.length || data.every((v) => !v)) {
    return <div className="chart-empty" style={{ height }}>{emptyText}</div>
  }

  const h = height
  const max = Math.max(...data, 1)
  const n = data.length
  const step = n > 1 ? (W - PAD * 2) / (n - 1) : 0
  const pts = data.map((v, i) => [n > 1 ? PAD + i * step : W / 2, h - PAD - (v / max) * (h - PAD * 2 - 14)])
  const line = n > 1
    ? pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
    : `M${PAD},${pts[0][1].toFixed(1)} L${W - PAD},${pts[0][1].toFixed(1)}`
  const area = `${line} L${W - PAD},${h - PAD} L${PAD},${h - PAD} Z`

  const onMove = (e) => {
    const box = e.currentTarget.getBoundingClientRect()
    const ratio = Math.min(1, Math.max(0, (e.clientX - box.left) / box.width))
    setHover(n > 1 ? Math.round(ratio * (n - 1)) : 0)
  }
  const at = hover != null ? pts[hover] : pts[n - 1]
  const shown = hover ?? n - 1
  const ticks = n > 2 ? [0, Math.floor((n - 1) / 2), n - 1] : n === 2 ? [0, 1] : [0]

  return (
    <div className="chart-wrap">
      <div className="chart-plot" style={{ height: h }} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <svg viewBox={`0 0 ${W} ${h}`} width="100%" height={h} preserveAspectRatio="none" role="img"
          aria-label={`${label || 'Chart'}: ${data.map((v, i) => `${labels[i] ?? i + 1} ${v}`).join(', ')}`}>
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.35" />
              <stop offset="100%" stopColor={color} stopOpacity="0" />
            </linearGradient>
          </defs>
          {[0.25, 0.5, 0.75].map((f) => (
            <line key={f} x1={PAD} x2={W - PAD} y1={h * f} y2={h * f} stroke="var(--border)" strokeDasharray="4 5" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          ))}
          <path d={area} fill={`url(#${gid})`} />
          <path d={line} fill="none" stroke={color} strokeWidth="2.4" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          {hover != null && (
            <line x1={at[0]} x2={at[0]} y1={PAD} y2={h - PAD} stroke="var(--border-strong)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          )}
        </svg>
        <span className="chart-max">{max}</span>
        <span className="chart-dot" style={{ left: `${(at[0] / W) * 100}%`, top: at[1], background: color }} />
        {hover != null && (
          <span className="chart-tip" style={{ left: `${Math.min(88, Math.max(12, (at[0] / W) * 100))}%`, top: Math.max(0, at[1] - 40) }}>
            <b>{data[shown]}</b>{labels[shown] != null && <span>{labels[shown]}</span>}
          </span>
        )}
      </div>
      {labels.length === n && (
        <div className="chart-x">
          {ticks.map((i) => <span key={i}>{labels[i]}</span>)}
        </div>
      )}
      {label && (
        <div className="chart-legend">
          <span className="key"><span className="swatch" style={{ background: color }} />{label}</span>
        </div>
      )}
    </div>
  )
}

export function BarList({ items = [], color = 'var(--primary)', emptyText = 'No data yet' }) {
  const max = Math.max(...items.map((i) => i.value), 1)
  if (items.length === 0) return <div className="chart-empty" style={{ height: 90 }}>{emptyText}</div>
  return (
    <div>
      {items.map((it) => (
        <div className="bar-row" key={it.label}>
          <span className="bar-label" title={it.label}>{it.label}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(it.value / max) * 100}%`, background: it.color || color }} />
          </div>
          <span className="bar-val">{it.value}</span>
        </div>
      ))}
    </div>
  )
}

export function Donut({ segments = [], size = 150, label, sublabel }) {
  const sum = segments.reduce((s, x) => s + x.value, 0)
  const total = sum || 1
  const r = 42
  const c = 2 * Math.PI * r
  const offsets = segments.reduce((acc, s) => {
    acc.push(acc[acc.length - 1] + s.value / total)
    return acc
  }, [0])
  return (
    <div className="donut">
      <svg width={size} height={size} viewBox="0 0 100 100" role="img"
        aria-label={segments.map((s) => `${s.label} ${s.value}`).join(', ')}>
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="11" />
        {segments.map((s, i) => (
          <circle
            key={i} cx="50" cy="50" r={r} fill="none"
            stroke={s.color} strokeWidth="11" strokeLinecap="butt"
            strokeDasharray={`${(s.value / total) * c} ${c}`} strokeDashoffset={-offsets[i] * c}
            transform="rotate(-90 50 50)"
          />
        ))}
        <text x="50" y="47" textAnchor="middle" fill="var(--text)" fontSize="17" fontWeight="800">{label}</text>
        <text x="50" y="60" textAnchor="middle" fill="var(--text-3)" fontSize="7.5">{sublabel}</text>
      </svg>
      <div className="chart-legend donut-legend">
        {segments.map((s) => (
          <span className="key" key={s.label}>
            <span className="swatch" style={{ background: s.color }} />
            {s.label}
            <b>{s.value}{sum > 0 && <small> · {Math.round((s.value / sum) * 100)}%</small>}</b>
          </span>
        ))}
      </div>
    </div>
  )
}

export function Sparkline({ data = [], width = 90, height = 28, color = 'var(--ok)' }) {
  if (!data.length) data = [0, 0]
  const max = Math.max(...data, 1)
  const step = width / (data.length - 1 || 1)
  const pts = data.map((v, i) => `${(i * step).toFixed(1)},${(height - 3 - (v / max) * (height - 6)).toFixed(1)}`).join(' ')
  return (
    <svg width={width} height={height}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}
