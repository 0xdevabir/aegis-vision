import { useCallback, useEffect, useRef, useState } from 'react'
import { Card, Icons, Tag, Empty, Seg, timeAgo, SEVERITY_TONE } from '../components/ui'
import {
  fetchAlertsFiltered, fetchAlertContext, acknowledgeAlert, dispatchPolice,
  createIncidentFromAlert, evidenceImageUrl,
} from '../services/api'
import { useToast } from '../components/Toast'
import { can } from '../lib/permissions'
import { useConfirm } from '../components/ui'
import {
  eventLabel, eventIconKey, fromAlertRow, EXPLAIN, REJECT_REASONS, REVIEW_LABEL,
} from '../lib/events'
import { parseTs } from '../lib/time'

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, info: 3, low: 4 }

const QUEUES = {
  review: { params: { reviewStatus: 'pending', dismissed: false }, keep: () => true },
  open: { params: { acknowledged: false, dismissed: false }, keep: () => true },
  done: { params: {}, keep: (a) => a.acknowledged || a.dismissed },
}

function sortItems(list) {
  return [...list].sort((a, b) => {
    const s = (SEVERITY_ORDER[a.severity] ?? 5) - (SEVERITY_ORDER[b.severity] ?? 5)
    if (s) return s
    return (parseTs(b.time)?.getTime() || 0) - (parseTs(a.time)?.getTime() || 0)
  })
}

function TypeIcon({ type }) {
  const Icon = Icons[eventIconKey(type)] || Icons.eye
  return <Icon />
}

function ReviewTag({ status }) {
  if (!REVIEW_LABEL[status]) return null
  const tone = { pending: 'warn', confirmed: 'ok', rejected: 'muted' }[status] || 'muted'
  return <Tag tone={tone}>{REVIEW_LABEL[status]}</Tag>
}

function Fact({ label, value }) {
  if (value == null || value === '') return null
  return (<><dt>{label}</dt><dd>{value}</dd></>)
}

function DetailPane({ item, detail, mode, setMode, busy, canAct, onConfirm, onReject, onDispatch, onIncident }) {
  const [evIdx, setEvIdx] = useState(0)
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')

  const data = detail?.id === item.id ? detail.data : null
  const evidence = data?.evidence?.filter((e) => e.has_image) || []
  const shown = evidence[Math.min(evIdx, Math.max(evidence.length - 1, 0))]
  const resolved = item.acknowledged || item.dismissed
  const notifies = data?.holds_external_notification
  const when = parseTs(item.time)

  return (
    <div className="tq-detail">
      <header className="tq-detail-head">
        <span className={`tq-icon sev-${item.severity}`}><TypeIcon type={item.type} /></span>
        <div className="tq-title">
          <h3>{eventLabel(item.type)}</h3>
          <div className="meta">
            <span>{item.camera || 'Unknown camera'}</span>
            <span title={when ? when.toLocaleString() : ''}>{timeAgo(item.time)}</span>
            {when && <span className="mono">{when.toLocaleTimeString()}</span>}
          </div>
        </div>
        <span className="spacer" />
        <Tag tone={SEVERITY_TONE[item.severity] || 'muted'}>{item.severity}</Tag>
        <ReviewTag status={item.reviewStatus} />
      </header>

      <div className="tq-evidence">
        {shown ? (
          <img
            src={evidenceImageUrl(shown.id, 'frame')}
            alt={`Snapshot for ${eventLabel(item.type)} on ${item.camera || 'camera'}`}
          />
        ) : (
          <Empty icon={Icons.camera}>{data ? 'No snapshot was saved for this alert' : 'Loading snapshot…'}</Empty>
        )}
        {evidence.length > 1 && (
          <div className="tq-thumbs" role="group" aria-label="Snapshots">
            {evidence.map((e, i) => (
              <button
                key={e.id} type="button" className={i === evIdx ? 'on' : ''}
                onClick={() => setEvIdx(i)} aria-label={`Snapshot ${i + 1}`}
              >
                <img src={evidenceImageUrl(e.id, 'roi')} alt="" />
              </button>
            ))}
          </div>
        )}
      </div>

      <p className="tq-why">{EXPLAIN[String(item.type).toUpperCase()] || item.msg}</p>

      <dl className="kv tq-facts">
        <Fact label="Confidence" value={data?.confidence != null ? `${Math.round(data.confidence * 100)}%` : null} />
        <Fact label="Zone" value={data?.zone} />
        <Fact label="Track" value={item.trackId != null && item.trackId >= 0 ? `#${item.trackId}` : null} />
        <Fact label="Candidate" value={item.personName && item.personName !== 'Unknown' ? `${item.personName} (unverified)` : null} />
        <Fact label="Plate" value={item.plate} />
        <Fact label="Details" value={item.msg} />
      </dl>

      {data?.related_events?.length > 0 && (
        <div className="tq-related">
          <div className="section-label"><span>Recent on this camera</span></div>
          {data.related_events.map((r) => (
            <div className="row" key={r.id}>
              <span>{eventLabel(r.type)}</span>
              <span className="meta">{timeAgo(r.timestamp)}</span>
            </div>
          ))}
        </div>
      )}

      {resolved ? (
        <div className="tq-resolved">
          <ReviewTag status={item.reviewStatus} />
          {item.reviewNote && <span className="meta">{item.reviewNote}</span>}
        </div>
      ) : !canAct ? (
        <div className="meta">Your role can view alerts but not act on them.</div>
      ) : mode === 'confirm' ? (
        <div className="tq-panel" role="group" aria-label="Confirm alert">
          <p>
            {notifies
              ? 'Confirming marks this as a real event and sends the held notification to external channels (security / law enforcement).'
              : 'Confirming marks this as a real event.'}
          </p>
          <div className="a-actions">
            <button type="button" className="btn btn-primary" disabled={busy} onClick={onConfirm} autoFocus>
              <Icons.check /> {notifies ? 'Confirm & notify' : 'Confirm'}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setMode(null)}>Cancel</button>
          </div>
        </div>
      ) : mode === 'reject' ? (
        <div className="tq-panel" role="group" aria-label="Reject alert">
          <label className="field">
            <span>Reason (required — helps tune the detector)</span>
            <select value={reason} onChange={(e) => setReason(e.target.value)} autoFocus>
              <option value="">Select a reason…</option>
              {REJECT_REASONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Note (optional)</span>
            <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} />
          </label>
          <div className="a-actions">
            <button
              type="button" className="btn btn-primary" disabled={busy || !reason}
              onClick={() => onReject(reason, note)}
            >Reject alert</button>
            <button type="button" className="btn btn-ghost" onClick={() => setMode(null)}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="a-actions tq-actions">
          <button type="button" className="btn btn-primary" onClick={() => setMode('confirm')}>
            <Icons.check /> Confirm <kbd>V</kbd>
          </button>
          <button type="button" className="btn" onClick={() => setMode('reject')}>
            <Icons.close /> Reject <kbd>D</kbd>
          </button>
          <button type="button" className="btn" disabled={busy} onClick={onDispatch}><Icons.dispatch /> Dispatch police</button>
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={onIncident}>Create incident</button>
        </div>
      )}
    </div>
  )
}

export function Triage({ ctx }) {
  const { setEvents, setPage, reviewPending, refreshReviewCount } = ctx
  const { push: toast } = useToast()
  const [ask, confirmDialog] = useConfirm()
  const canAct = can(ctx.me?.role, 'triage.act')
  const [queue, setQueue] = useState('review')
  const [items, setItems] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [mode, setMode] = useState(null)
  const [busy, setBusy] = useState(false)

  const selected = items.find((i) => i.id === selectedId) || items[0] || null

  const load = useCallback(async () => {
    const q = QUEUES[queue]
    const rows = await fetchAlertsFiltered({ ...q.params, limit: 100 })
    return sortItems(rows.map(fromAlertRow).filter(q.keep))
  }, [queue])

  /* Reload on queue change, on new live events, and every 20 s as a safety net. */
  const liveCount = ctx.events.length
  useEffect(() => {
    let alive = true
    const run = () => load().then((list) => { if (alive) { setItems(list); setLoaded(true) } }).catch(() => {})
    run()
    const t = setInterval(run, 20000)
    return () => { alive = false; clearInterval(t) }
  }, [load, liveCount])

  const selId = selected?.id
  useEffect(() => {
    if (selId == null) return undefined
    let alive = true
    fetchAlertContext(selId)
      .then((data) => { if (alive) setDetail({ id: selId, data }) })
      .catch(() => { if (alive) setDetail({ id: selId, data: {} }) })
    return () => { alive = false }
  }, [selId])

  const move = useCallback((delta) => {
    if (!items.length) return
    const idx = Math.max(0, items.findIndex((i) => i.id === selected?.id))
    setSelectedId(items[Math.min(items.length - 1, Math.max(0, idx + delta))].id)
    setMode(null)
  }, [items, selected])

  const finish = useCallback((id, patch) => {
    const idx = items.findIndex((i) => i.id === id)
    const next = items[idx + 1] || items[idx - 1]
    setItems((prev) => prev.filter((i) => i.id !== id))
    setSelectedId(next ? next.id : null)
    setMode(null)
    setEvents?.((prev) => prev.map((e) => (e.id === id ? { ...e, ...patch } : e)))
    refreshReviewCount?.()
  }, [items, setEvents, refreshReviewCount])

  const run = async (fn, okMsg, id, patch) => {
    setBusy(true)
    try {
      await fn()
      toast(okMsg, 'ok')
      finish(id, patch)
    } catch (err) {
      toast(err.message || 'Action failed', 'danger')
    } finally {
      setBusy(false)
    }
  }

  const confirm = () => selected && run(
    () => acknowledgeAlert(selected.id, { acknowledged: true, dismissed: false }),
    'Alert confirmed', selected.id, { acknowledged: true },
  )
  const reject = (reason, note) => selected && run(
    () => acknowledgeAlert(selected.id, {
      acknowledged: false, dismissed: true, note: `${reason}${note ? `: ${note}` : ''}`,
    }),
    'Alert rejected', selected.id, { dismissed: true },
  )
  const dispatch = async () => {
    if (!selected) return
    if (!(await ask({ title: 'Dispatch police', message: 'This notifies the configured external channels (CAD, SMS, security). Continue?', confirmLabel: 'Dispatch', danger: true }))) return
    run(() => dispatchPolice(selected.id), 'Police dispatched', selected.id, { acknowledged: true })
  }
  const incident = async () => {
    if (!selected) return
    try {
      await createIncidentFromAlert(selected.id)
      toast('Incident created', 'ok')
      setPage?.('incidents')
    } catch (err) {
      toast(err.message || 'Failed to create incident', 'danger')
    }
  }

  /* Keyboard triage. A ref keeps the handler current without re-binding every render. */
  const keys = useRef(null)
  useEffect(() => {
    keys.current = { move, setMode, selected }
  }, [move, selected])
  useEffect(() => {
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return
      const k = keys.current
      if (!k) return
      const key = e.key.toLowerCase()
      if (key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); k.move(1) }
      else if (key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); k.move(-1) }
      else if (key === 'v' && k.selected) k.setMode('confirm')
      else if (key === 'd' && k.selected) { e.preventDefault(); k.setMode('reject') }
      else if (e.key === 'Escape') k.setMode(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <>
      <div className="page-head">
        <div>
          <h2>Alert Triage</h2>
          <p>Review each alert against its snapshot before anything is escalated.</p>
        </div>
        <div className="head-actions">
          <Seg
            value={queue}
            onChange={(v) => { setQueue(v); setSelectedId(null); setLoaded(false); setMode(null) }}
            options={[
              { value: 'review', label: `Needs review${reviewPending ? ` (${reviewPending})` : ''}` },
              { value: 'open', label: 'Open' },
              { value: 'done', label: 'Resolved' },
            ]}
          />
        </div>
      </div>

      <div className="triage">
        <Card title="Queue" sub={`${items.length} alert${items.length === 1 ? '' : 's'}`} flush>
          <div className="tq-list" role="listbox" aria-label="Alerts">
            {loaded && items.length === 0 && (
              <Empty icon={Icons.check}>
                {queue === 'review' ? 'Nothing waiting for review' : 'No alerts in this queue'}
              </Empty>
            )}
            {items.map((it) => (
              <button
                key={it.id} type="button" role="option"
                aria-selected={it.id === selected?.id}
                className={`tq-item ${it.id === selected?.id ? 'on' : ''}`}
                onClick={() => { setSelectedId(it.id); setMode(null) }}
              >
                <span className={`tq-icon sev-${it.severity}`}><TypeIcon type={it.type} /></span>
                <span className="tq-item-body">
                  <b>{eventLabel(it.type)}</b>
                  <span className="meta">{it.camera || 'Unknown camera'} · {timeAgo(it.time)}</span>
                </span>
                <Tag tone={SEVERITY_TONE[it.severity] || 'muted'}>{it.severity}</Tag>
              </button>
            ))}
          </div>
          <div className="tq-keys"><kbd>J</kbd><kbd>K</kbd> move <kbd>V</kbd> confirm <kbd>D</kbd> reject</div>
        </Card>

        <Card title="Alert details" flush>
          {selected ? (
            <DetailPane
              key={selected.id}
              item={selected} detail={detail} mode={mode} setMode={setMode} busy={busy} canAct={canAct}
              onConfirm={confirm} onReject={reject} onDispatch={dispatch} onIncident={incident}
            />
          ) : (
            <Empty icon={Icons.shield}>Select an alert to review it</Empty>
          )}
        </Card>
      </div>
      {confirmDialog}
    </>
  )
}
