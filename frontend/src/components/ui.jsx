/* eslint-disable react-refresh/only-export-components */
/* Shared UI primitives: icons, tags, cards, stats, modal, empty states. */
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { parseTs } from '../lib/time'

const stroke = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
}

export const Icons = {
  overview: () => (
    <svg viewBox="0 0 24 24" {...stroke}><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>
  ),
  live: () => (
    <svg viewBox="0 0 24 24" {...stroke}><rect x="2" y="5" width="14" height="12" rx="2"/><path d="M22 7l-6 4 6 4V7z"/></svg>
  ),
  map: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M12 21s-7-5.5-7-11a7 7 0 0 1 14 0c0 5.5-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/></svg>
  ),
  ai: () => (
    <svg viewBox="0 0 24 24" {...stroke}><circle cx="12" cy="12" r="3"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4M5 5l2.5 2.5M16.5 16.5L19 19M19 5l-2.5 2.5M7.5 16.5L5 19"/></svg>
  ),
  alert: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M12 3l10 18H2L12 3z"/><path d="M12 10v4M12 17.5v.5"/></svg>
  ),
  incident: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M9 5h6M9 5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2"/><path d="M9 12h6M9 16h4"/></svg>
  ),
  camera: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M3 8l12-3 1.5 5L5 13 3 8z"/><path d="M14 10.5l4.5-1.5.8 3-4.6 1.4"/><path d="M7 13v5a2 2 0 0 0 2 2h2"/></svg>
  ),
  chart: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M3 3v18h18"/><path d="M7 15l4-5 3 3 5-7"/></svg>
  ),
  evidence: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7z"/></svg>
  ),
  watchlist: () => (
    <svg viewBox="0 0 24 24" {...stroke}><circle cx="12" cy="9" r="3.5"/><path d="M5 20c1.2-3.2 3.8-5 7-5s5.8 1.8 7 5"/></svg>
  ),
  vehicle: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M4 15l1.5-5.5A2 2 0 0 1 7.4 8h9.2a2 2 0 0 1 1.9 1.5L20 15"/><rect x="3" y="15" width="18" height="4" rx="1.5"/><circle cx="7.5" cy="19" r="1.4"/><circle cx="16.5" cy="19" r="1.4"/></svg>
  ),
  report: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M6 3h9l4 4v14H6V3z"/><path d="M15 3v4h4M9 12h6M9 16h6"/></svg>
  ),
  users: () => (
    <svg viewBox="0 0 24 24" {...stroke}><circle cx="9" cy="8.5" r="3"/><path d="M3 19c1-2.8 3.2-4.3 6-4.3s5 1.5 6 4.3"/><circle cx="17" cy="9.5" r="2.4"/><path d="M17.5 14.7c2 .4 3.3 1.6 4 3.5"/></svg>
  ),
  settings: () => (
    <svg viewBox="0 0 24 24" {...stroke}><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2-1.2L14.3 3h-4l-.4 2.5a7 7 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2 1.2l.4 2.5h4l.3-2.5a7 7 0 0 0 2-1.2l2.3 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z"/></svg>
  ),
  search: () => (
    <svg viewBox="0 0 24 24" {...stroke}><circle cx="11" cy="11" r="6.5"/><path d="M21 21l-4.8-4.8"/></svg>
  ),
  bell: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M18 9a6 6 0 1 0-12 0c0 6-2.5 7-2.5 7h17S18 15 18 9z"/><path d="M10 20a2.2 2.2 0 0 0 4 0"/></svg>
  ),
  sun: () => (
    <svg viewBox="0 0 24 24" {...stroke}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
  ),
  moon: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
  ),
  logout: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/></svg>
  ),
  bot: () => (
    <svg viewBox="0 0 24 24" {...stroke}><rect x="4" y="8" width="16" height="11" rx="2"/><path d="M12 4v4M9 4h6"/><circle cx="9" cy="13" r="1"/><circle cx="15" cy="13" r="1"/><path d="M9 16.5h6"/></svg>
  ),
  menu: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M4 6h16M4 12h16M4 18h16"/></svg>
  ),
  close: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M6 6l12 12M18 6L6 18"/></svg>
  ),
  check: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M4 12.5l5 5L20 6.5"/></svg>
  ),
  dispatch: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
  ),
  download: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 21h16"/></svg>
  ),
  shield: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M12 2l8 3.5V11c0 5-3.4 8.6-8 11-4.6-2.4-8-6-8-11V5.5L12 2z"/></svg>
  ),
  eye: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>
  ),
  clock: () => (
    <svg viewBox="0 0 24 24" {...stroke}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/></svg>
  ),
  zone: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M4 7l6-3 9 4-2 11-9 1-4-6 0-7z"/><circle cx="4" cy="7" r="1.2"/><circle cx="10" cy="4" r="1.2"/><circle cx="19" cy="8" r="1.2"/><circle cx="17" cy="19" r="1.2"/></svg>
  ),
  fire: () => (
    <svg viewBox="0 0 24 24" {...stroke}><path d="M12 22c4 0 7-2.8 7-7 0-3-1.8-5-3.5-7C14 6 13 4 13 2c-3 2-5 5-5 8-1-.8-1.6-2-2-3.2C4.7 8.6 5 11 5 13c0 4.7 3 9 7 9z"/></svg>
  ),
}

export function Tag({ tone = 'muted', children }) {
  return <span className={`tag tag-${tone}`}>{children}</span>
}

export function Stat({ label, value, delta, accent = 'primary', icon: Icon }) {
  return (
    <div className={`stat accent-${accent}`}>
      <div className="stat-top">
        <span className="label">{label}</span>
      </div>
      <span className="value">{value}</span>
      {delta && <span className="delta">{delta}</span>}
      {Icon && <span className="stat-icon"><Icon /></span>}
    </div>
  )
}

export function Card({ title, sub, actions, children, className = '', flush = false, style }) {
  return (
    <div className={`card ${className}`} style={style}>
      {(title || actions) && (
        <div className="card-head">
          <span>{title} {sub && <span className="sub">· {sub}</span>}</span>
          {actions}
        </div>
      )}
      <div className={`card-body ${flush ? 'flush' : ''}`}>{children}</div>
    </div>
  )
}

export function Empty({ icon: Icon = Icons.search, children }) {
  return (
    <div className="empty">
      <Icon />
      <div>{children}</div>
    </div>
  )
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

const modalStack = []   // only the top-most dialog reacts to Esc/Tab

/** Accessible dialog: role/aria, Esc to close, Tab stays inside, focus returns to the opener. */
export function Modal({ title, onClose, children, footer }) {
  const ref = useRef(null)
  const titleId = useId()
  useEffect(() => {
    const opener = document.activeElement
    const node = ref.current
    modalStack.push(node)
    const first = node?.querySelector('input, select, textarea') || node?.querySelector(FOCUSABLE)
    first?.focus()
    const onKey = (e) => {
      if (modalStack[modalStack.length - 1] !== node) return
      if (e.key === 'Escape') { e.stopPropagation(); onClose?.(); return }
      if (e.key !== 'Tab' || !node) return
      const items = [...node.querySelectorAll(FOCUSABLE)]
      if (!items.length) return
      const firstEl = items[0]; const lastEl = items[items.length - 1]
      if (e.shiftKey && document.activeElement === firstEl) { e.preventDefault(); lastEl.focus() }
      else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); firstEl.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      modalStack.splice(modalStack.indexOf(node), 1)
      opener?.focus?.()
    }
  }, [onClose])
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span id={titleId}>{title}</span>
          <button className="icon-btn" onClick={onClose} aria-label="Close dialog"><Icons.close /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  )
}

/** Styled replacement for window.confirm. `const [ask, dialog] = useConfirm()`; `if (!(await ask({...}))) return`. */
export function useConfirm() {
  const [state, setState] = useState(null)
  const ask = useCallback((opts) => new Promise((resolve) => setState({ ...opts, resolve })), [])
  const close = (answer) => { state?.resolve(answer); setState(null) }
  const dialog = state && (
    <Modal
      title={state.title || 'Please confirm'}
      onClose={() => close(false)}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className="btn" onClick={() => close(false)}>{state.cancelLabel || 'Cancel'}</button>
          <button className={`btn ${state.danger ? 'btn-danger' : 'btn-primary'}`} onClick={() => close(true)}>
            {state.confirmLabel || 'Confirm'}
          </button>
        </div>
      )}
    >
      <p style={{ margin: 0 }}>{state.message}</p>
    </Modal>
  )
  return [ask, dialog]
}

export function Seg({ options, value, onChange }) {
  return (
    <div className="seg">
      {options.map((o) => (
        <button key={o.value} className={value === o.value ? 'on' : ''} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Pill({ tone = 'muted', children }) {
  return (
    <span className={`pill pill-${tone}`}>
      <span className="dot" />{children}
    </span>
  )
}

export const SEVERITY_TONE = { critical: 'danger', high: 'orange', medium: 'warn', info: 'info', low: 'ok' }

export function timeAgo(ts) {
  if (!ts) return '—'
  const d = parseTs(ts)
  if (!d) return String(ts)
  const s = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return d.toLocaleString()
}

