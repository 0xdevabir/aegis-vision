/* Dependency-free SVG charts: area/line, bar list, donut, sparkline. */

export function AreaChart({ data = [], height = 180, color = 'var(--primary)', label }) {
  const w = 600
  const h = height
  const pad = 8
  if (!data.length) data = [0, 0]
  const max = Math.max(...data, 1)
  const step = (w - pad * 2) / (data.length - 1 || 1)
  const pts = data.map((v, i) => [pad + i * step, h - pad - (v / max) * (h - pad * 2 - 14)])
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
  const area = `${line} L${pts[pts.length - 1][0]},${h - pad} L${pad},${h - pad} Z`
  const gid = `g${Math.abs(hashCode(String(data) + color))}`

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} preserveAspectRatio="none">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.35" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={pad} x2={w - pad} y1={h * f} y2={h * f} stroke="var(--border)" strokeDasharray="4 5" strokeWidth="1" />
        ))}
        <path d={area} fill={`url(#${gid})`} />
        <path d={line} fill="none" stroke={color} strokeWidth="2.4" strokeLinecap="round" />
        {pts.map((p, i) => (
          <circle key={i} cx={p[0]} cy={p[1]} r="3" fill={color} opacity={i === pts.length - 1 ? 1 : 0} />
        ))}
      </svg>
      {label && (
        <div className="chart-legend">
          <span className="key"><span className="swatch" style={{ background: color }} />{label}</span>
        </div>
      )}
    </div>
  )
}

export function BarList({ items = [], color = 'var(--primary)' }) {
  const max = Math.max(...items.map((i) => i.value), 1)
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
      {items.length === 0 && <p className="muted" style={{ fontSize: '0.82rem' }}>No data yet</p>}
    </div>
  )
}

export function Donut({ segments = [], size = 150, label, sublabel }) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1
  const r = 42
  const c = 2 * Math.PI * r
  const offsets = segments.reduce((acc, s) => {
    acc.push(acc[acc.length - 1] + s.value / total)
    return acc
  }, [0])
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
      <svg width={size} height={size} viewBox="0 0 100 100">
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
      <div className="chart-legend" style={{ flexDirection: 'column', gap: 8, marginTop: 0 }}>
        {segments.map((s) => (
          <span className="key" key={s.label}>
            <span className="swatch" style={{ background: s.color }} />
            {s.label} — <b>{s.value}</b>
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

function hashCode(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) { h = (h << 5) - h + str.charCodeAt(i); h |= 0 }
  return h
}
