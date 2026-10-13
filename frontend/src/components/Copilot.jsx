import { useRef, useState } from 'react'
import { Icons } from './ui'

/*
 * Command Assistant — on-device analyst assistant.
 * Answers from live dashboard data (alerts, cameras, analytics) using
 * rule-based intent matching. Designed so an LLM endpoint can be plugged
 * in later by replacing `answer()` with an API call.
 */

const SUGGESTIONS = [
  'Summarize the last 24 hours',
  'What is the current threat level?',
  'Which camera has the most detections?',
  'Suggest response actions',
  'Explain the latest alert',
]

function answer(q, ctx) {
  const t = q.toLowerCase()
  const { events = [], summary, cameras = [], threatLevel, locations = [] } = ctx
  const crit = events.filter((e) => e.severity === 'critical')

  if (t.includes('summar')) {
    if (summary) {
      return `In the last ${summary.period_hours}h: ${summary.total_events} events recorded — ` +
        `${summary.criminal_detections} criminal detections, ${summary.weapon_detections} weapon detections, ` +
        `${summary.suspicious_activities} suspicious activities, and ${summary.alerts_triggered} alerts dispatched. ` +
        (crit.length ? `⚠ ${crit.length} critical alert(s) are in the live feed — review the Alert Center.` : 'No critical alerts currently active.')
    }
    return `The live feed holds ${events.length} events, ${crit.length} of them critical. Connect the backend analytics API for a full 24h summary.`
  }

  if (t.includes('threat')) {
    const map = {
      critical: 'CRITICAL — an active criminal or weapon detection is in progress. Open Alerts to acknowledge it.',
      high: 'HIGH — elevated threat scores detected on at least one camera. Monitor closely.',
      low: 'LOW — all cameras nominal, no active threats.',
    }
    return `Current threat level: ${map[threatLevel] || threatLevel}`
  }

  if (t.includes('camera') && (t.includes('most') || t.includes('top'))) {
    if (locations.length) {
      const top = [...locations].sort((a, b) => b.events - a.events)[0]
      return `“${top.location || 'Unknown'}” recorded the most detections (${top.events} events in the last 24h). Consider reviewing its live feed and increasing patrol coverage there.`
    }
    return 'No per-camera detection data available yet — the analytics API returned no location breakdown.'
  }

  if (t.includes('respon') || t.includes('action') || t.includes('suggest')) {
    if (crit.length) {
      const a = crit[0]
      return `Recommended response for “${a.msg}” at ${a.camera || 'unknown location'}: ` +
        `1) Verify the detection snapshot in Evidence Center. 2) Dispatch the nearest unit` +
        (a.lat != null ? ` to GPS ${Number(a.lat).toFixed(5)}, ${Number(a.lng).toFixed(5)}` : '') +
        `. 3) Lock adjacent cameras onto the subject via Live Monitoring. 4) Open an incident ticket and attach the evidence.`
    }
    return 'No active critical alerts. Recommended standing actions: verify offline cameras, review overnight evidence, and confirm the watchlist is up to date.'
  }

  if (t.includes('explain') || t.includes('latest alert') || t.includes('last alert')) {
    const a = events[0]
    if (!a) return 'There are no alerts in the current session feed.'
    return `Latest alert: ${a.type?.replace(/_/g, ' ')} (severity: ${a.severity}) — “${a.msg}” from ${a.camera || 'an unknown camera'}. ` +
      (a.severity === 'critical'
        ? 'Critical alerts are recorded with evidence and an audit entry. Open Alerts to review it and see who was notified.'
        : 'This alert is informational.')
  }

  if (t.includes('offline') || t.includes('health')) {
    const off = cameras.filter((c) => !c.active)
    return off.length
      ? `${off.length} camera(s) appear offline: ${off.map((c) => c.name || c.camera_id).join(', ')}. Check power and network links.`
      : `All ${cameras.length} registered cameras report active.`
  }

  if (t.includes('report')) {
    return 'Open the Reports page to generate a 24h incident report (JSON/CSV export). It aggregates events, criminal and weapon detections, and dispatched alerts.'
  }

  return 'I can summarize incidents, explain alerts, report threat level, find hotspot cameras, and suggest response actions. Try one of the suggestion chips, or ask about “threat level”, “summary”, or “response actions”.'
}

export function Copilot({ ctx, onClose }) {
  const [messages, setMessages] = useState([
    { role: 'bot', text: 'Quick answers from the alerts, cameras and analytics loaded in this session. This is a rule-based helper, not an AI model. Try “threat level” or “latest alert”.' },
  ])
  const [input, setInput] = useState('')
  const bodyRef = useRef(null)

  const send = (text) => {
    const q = (text || input).trim()
    if (!q) return
    const reply = answer(q, ctx)
    setMessages((m) => [...m, { role: 'user', text: q }, { role: 'bot', text: reply }])
    setInput('')
    requestAnimationFrame(() => {
      bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: 'smooth' })
    })
  }

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="drawer">
        <div className="drawer-head">
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Icons.bot /> Command Assistant</span>
          <button className="icon-btn" onClick={onClose}><Icons.close /></button>
        </div>
        <div className="drawer-body" ref={bodyRef}>
          <div className="assistant-suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="btn btn-sm" onClick={() => send(s)}>{s}</button>
            ))}
          </div>
          {messages.map((m, i) => (
            <div key={i} className={`assistant-msg ${m.role === 'user' ? 'user' : ''}`}>
              {m.role === 'bot' && <span className="m-icon">?</span>}
              <div className="m-body">{m.text}</div>
            </div>
          ))}
        </div>
        <div className="assistant-input">
          <input
            className="input"
            placeholder="Ask about alerts, threats, cameras…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
          />
          <button className="btn btn-primary" onClick={() => send()}><Icons.dispatch /></button>
        </div>
      </div>
    </>
  )
}
