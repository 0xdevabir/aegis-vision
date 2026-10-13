import { useEffect, useMemo, useState } from 'react'
import { Card, Icons, Tag, Empty, timeAgo, SEVERITY_TONE, Seg } from '../components/ui'
import { searchEvents } from '../services/api'
import { eventLabel, eventGroup, eventIconKey, GROUPS } from '../lib/events'
import { parseTs } from '../lib/time'

const RANGES = [
  { value: 1, label: '1 h' },
  { value: 24, label: '24 h' },
  { value: 168, label: '7 days' },
]
const PAGE = 24

export function DetectionCenter({ ctx }) {
  const { cameras = [], setPage } = ctx
  const [group, setGroup] = useState('all')
  const [camera, setCamera] = useState('')
  const [hours, setHours] = useState(24)
  const [rows, setRows] = useState([])
  const [state, setState] = useState('loading')   // loading | ready | error
  const [visible, setVisible] = useState(PAGE)
  const liveCount = ctx.events.length

  /* Server-side time window; camera/group filters are applied to this window. */
  useEffect(() => {
    let alive = true
    const since = new Date(Date.now() - hours * 3600 * 1000).toISOString()
    searchEvents({ since, limit: 500 })
      .then((r) => { if (alive) { setRows(r); setState('ready') } })
      .catch(() => { if (alive) setState('error') })
    return () => { alive = false }
  }, [hours, liveCount])

  const inWindow = useMemo(
    () => rows.filter((e) => !camera || e.camera_id === camera),
    [rows, camera],
  )
  const counts = useMemo(() => {
    const c = {}
    inWindow.forEach((e) => { const g = eventGroup(e.event_type); c[g] = (c[g] || 0) + 1 })
    return c
  }, [inWindow])
  const filtered = group === 'all' ? inWindow : inWindow.filter((e) => eventGroup(e.event_type) === group)
  const shown = filtered.slice(0, visible)

  const camOptions = [...new Set([...cameras.map((c) => c.camera_id), ...rows.map((r) => r.camera_id)].filter(Boolean))]

  return (
    <>
      <div className="page-head">
        <div>
          <h2>Detection Center</h2>
          <p>Every recorded detection, searchable by type, camera and time.</p>
        </div>
        <div className="head-actions">
          <label className="field inline">
            <span className="sr-only">Camera</span>
            <select value={camera} onChange={(e) => { setCamera(e.target.value); setVisible(PAGE) }} aria-label="Camera">
              <option value="">All cameras</option>
              {camOptions.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <Seg value={hours} onChange={(v) => { setHours(v); setVisible(PAGE) }} options={RANGES} />
        </div>
      </div>

      <div className="chip-row" role="tablist" aria-label="Detection type">
        {GROUPS.map((g) => {
          const n = g.id === 'all' ? inWindow.length : (counts[g.id] || 0)
          return (
            <button
              key={g.id} type="button" role="tab" aria-selected={group === g.id}
              className={`chip ${group === g.id ? 'on' : ''}`}
              onClick={() => { setGroup(g.id); setVisible(PAGE) }}
            >
              {g.label} <span className="chip-n">{n}</span>
            </button>
          )
        })}
      </div>

      <Card
        title="Detections"
        sub={state === 'ready' ? `${filtered.length} in the last ${RANGES.find((r) => r.value === hours)?.label}${rows.length >= 500 ? ' · showing the latest 500' : ''}` : ''}
      >
        {state === 'loading' && <Empty icon={Icons.clock}>Loading detections…</Empty>}
        {state === 'error' && <Empty icon={Icons.alert}>Could not load detections. Check the backend connection.</Empty>}
        {state === 'ready' && filtered.length === 0 && (
          <Empty icon={Icons.ai}>No detections match these filters. That is normal on a quiet camera.</Empty>
        )}
        <div className="grid grid-2">
          {shown.map((e) => {
            const Icon = Icons[eventIconKey(e.event_type)] || Icons.eye
            const when = parseTs(e.timestamp)
            return (
              <article key={e.id} className={`alert-card p-${e.severity || 'info'}`}>
                <div className="a-top">
                  <span className={`tq-icon sev-${e.severity}`}><Icon /></span>
                  <div style={{ minWidth: 0 }}>
                    <div className="a-title">{eventLabel(e.event_type)}</div>
                    <div className="a-meta">
                      <span>{e.camera_location || e.camera_id || 'Unknown camera'}</span>
                      <span title={when ? when.toLocaleString() : ''}>{timeAgo(e.timestamp)}</span>
                      {e.zone && <span>Zone: {e.zone}</span>}
                      {e.confidence != null && <span>{Math.round(e.confidence * 100)}% conf.</span>}
                      {e.track_id != null && e.track_id >= 0 && <span>Track #{e.track_id}</span>}
                    </div>
                  </div>
                  <span className="spacer" />
                  <Tag tone={SEVERITY_TONE[e.severity] || 'muted'}>{e.severity}</Tag>
                </div>
                {e.message && <div className="dc-msg">{e.message}</div>}
                {e.alert_id && (
                  <div className="a-actions">
                    <button type="button" className="btn btn-sm btn-ghost" onClick={() => setPage?.('alerts')}>
                      Open in Triage
                    </button>
                  </div>
                )}
              </article>
            )
          })}
        </div>
        {filtered.length > visible && (
          <div className="load-more">
            <button type="button" className="btn" onClick={() => setVisible((v) => v + PAGE)}>
              Show more ({filtered.length - visible} left)
            </button>
          </div>
        )}
      </Card>
    </>
  )
}
