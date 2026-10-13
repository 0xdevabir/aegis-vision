import { useEffect, useState } from 'react'
import { can } from '../lib/permissions'
import { Card, Icons, Tag, Empty, timeAgo, SEVERITY_TONE, Modal } from '../components/ui'
import {
  fetchIncidents, fetchIncidentStats, updateIncident, addIncidentNote, createIncident, fetchAssignees,
} from '../services/api'
import { useToast } from '../components/Toast'
const STATUSES = ['open', 'investigating', 'resolved', 'closed']
const STATUS_TONE = { open: 'danger', investigating: 'warn', resolved: 'ok', closed: 'muted' }

export function Incidents({ ctx }) {
  const { push: toast } = useToast()
  const canEdit = can(ctx?.me?.role, 'incident.edit')
  const [assignees, setAssignees] = useState([])
  const [showNew, setShowNew] = useState(false)
  const [newForm, setNewForm] = useState({ title: '', description: '', priority: 'medium' })
  useEffect(() => { fetchAssignees().then(setAssignees).catch(() => {}) }, [])
  const [incidents, setIncidents] = useState([])
  const [stats, setStats] = useState(null)
  const [selected, setSelected] = useState(null)
  const [note, setNote] = useState('')
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [list, st] = await Promise.all([
          fetchIncidents(filter === 'all' ? {} : { status: filter }),
          fetchIncidentStats(),
        ])
        if (!cancelled) {
          setIncidents(list)
          setStats(st)
        }
      } catch (e) {
        if (!cancelled) { setIncidents([]); setLoadError(e.message || 'Could not load incidents') }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [filter])

  const reload = async () => {
    const [list, st] = await Promise.all([
      fetchIncidents(filter === 'all' ? {} : { status: filter }),
      fetchIncidentStats(),
    ])
    setIncidents(list)
    setStats(st)
  }

  const patch = async (id, body) => {
    try {
      const updated = await updateIncident(id, body)
      setIncidents((prev) => prev.map((i) => (i.id === id ? updated : i)))
      if (selected?.id === id) setSelected(updated)
      reload().catch(() => {})
    } catch (e) {
      toast(e.message || 'Update failed', 'danger')
    }
  }

  const submitNote = async () => {
    if (!selected || !note.trim()) return
    try {
      await addIncidentNote(selected.id, note.trim())
      setNote('')
      const refreshed = await fetchIncidents({})
      const found = refreshed.find((i) => i.id === selected.id)
      setIncidents(refreshed)
      if (found) setSelected(found)
    } catch (e) {
      toast(e.message || 'Could not add note', 'danger')
    }
  }

  const createManual = async () => {
    try {
      const inc = await createIncident({
        title: newForm.title.trim(),
        description: newForm.description.trim() || null,
        priority: newForm.priority,
        incident_type: 'MANUAL',
      })
      setIncidents((prev) => [inc, ...prev])
      setSelected(inc)
      setShowNew(false)
      setNewForm({ title: '', description: '', priority: 'medium' })
      toast('Incident created', 'ok')
    } catch (e) {
      toast(e.message || 'Could not create incident', 'danger')
    }
  }

  const by = stats?.by_status || {}

  return (
    <>
      {loadError && <div className="login-error" role="alert" style={{ marginBottom: 12 }}>{loadError}</div>}
      <div className="grid grid-3" style={{ marginBottom: 14 }}>
        <div className="stat accent-danger"><span className="label">Open</span><span className="value">{by.open || 0}</span></div>
        <div className="stat accent-warn"><span className="label">Investigating</span><span className="value">{by.investigating || 0}</span></div>
        <div className="stat accent-ok"><span className="label">Resolved / Closed</span><span className="value">{(by.resolved || 0) + (by.closed || 0)}</span></div>
      </div>

      <Card
        title="Incident Tickets"
        sub="server-side · auto-created from critical alerts"
        actions={
          <div style={{ display: 'flex', gap: 8 }}>
            <select className="input" style={{ padding: '4px 8px' }} value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">All</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            {canEdit && <button className="btn btn-sm btn-primary" onClick={() => setShowNew(true)}><Icons.incident /> New</button>}
          </div>
        }
        flush
      >
        {loading && <div style={{ padding: 16 }} className="muted">Loading…</div>}
        {!loading && incidents.length === 0 && (
          <div style={{ padding: 16 }}>
            <Empty icon={Icons.incident}>
              No tickets yet — critical alerts auto-open incidents, or click New
            </Empty>
          </div>
        )}
        {!loading && incidents.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Ticket</th><th>Title</th><th>Priority</th><th>Camera</th>
                <th>Officer</th><th>Status</th><th>Opened</th><th></th>
              </tr>
            </thead>
            <tbody>
              {incidents.map((inc) => (
                <tr key={inc.id}>
                  <td className="mono">{inc.ticket_id}</td>
                  <td><b>{inc.title}</b></td>
                  <td><Tag tone={SEVERITY_TONE[inc.priority] || 'muted'}>{inc.priority}</Tag></td>
                  <td>{inc.camera_location || '—'}</td>
                  <td>
                    <select
                      className="input" style={{ padding: '4px 8px', fontSize: '0.78rem' }}
                      aria-label={`Assignee for ${inc.ticket_id}`}
                      disabled={!canEdit}
                      value={inc.assigned_to || 0}
                      onChange={(e) => patch(inc.id, { assigned_to: Number(e.target.value) })}
                    >
                      <option value={0}>Unassigned</option>
                      {assignees.map((u) => <option key={u.id} value={u.id}>{u.username} ({u.role})</option>)}
                    </select>
                  </td>
                  <td>
                    <select
                      className="input" style={{ padding: '4px 8px', fontSize: '0.78rem' }}
                      aria-label={`Status for ${inc.ticket_id}`}
                      disabled={!canEdit}
                      value={inc.status}
                      onChange={(e) => patch(inc.id, { status: e.target.value })}
                    >
                      {STATUSES.map((s) => <option key={s}>{s}</option>)}
                    </select>
                  </td>
                  <td className="muted">{timeAgo(inc.created_at)}</td>
                  <td><button className="btn btn-sm" onClick={() => setSelected(inc)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {selected && (
        <Modal
          title={`${selected.ticket_id} — ${selected.title}`}
          onClose={() => setSelected(null)}
          footer={
            <>
              <button className="btn" onClick={() => window.print()}><Icons.download /> Export</button>
              <button className="btn btn-primary" onClick={() => patch(selected.id, { status: 'resolved' })}>
                <Icons.check /> Mark Resolved
              </button>
            </>
          }
        >
          <dl className="kv" style={{ marginBottom: 18 }}>
            <dt>Type</dt><dd>{selected.incident_type?.replace(/_/g, ' ')}</dd>
            <dt>Priority</dt><dd><Tag tone={SEVERITY_TONE[selected.priority]}>{selected.priority}</Tag></dd>
            <dt>Camera</dt><dd>{selected.camera_location || '—'}</dd>
            <dt>Status</dt><dd><Tag tone={STATUS_TONE[selected.status]}>{selected.status}</Tag></dd>
            <dt>Officer</dt><dd>{selected.assigned_name || 'Unassigned'}</dd>
            {selected.person_name && <><dt>Subject</dt><dd>{selected.person_name}</dd></>}
            {selected.lat != null && (
              <><dt>GPS</dt><dd className="mono">{Number(selected.lat).toFixed(5)}, {Number(selected.lng).toFixed(5)}</dd></>
            )}
          </dl>

          <h4 style={{ marginBottom: 10, fontSize: '0.9rem' }}>Timeline</h4>
          <div className="timeline" style={{ marginBottom: 18 }}>
            {(selected.events || []).length === 0 && <div className="muted">No events yet</div>}
            {(selected.events || []).map((ev) => (
              <div key={ev.id} className="timeline-item">
                <div className="t-time">{timeAgo(ev.created_at)} · {ev.actor}</div>
                <b>{ev.event_type}</b> — {ev.message}
              </div>
            ))}
          </div>

          <h4 style={{ marginBottom: 10, fontSize: '0.9rem' }}>Notes</h4>
          {(selected.notes || []).map((n) => (
            <div key={n.id} className="row">
              <div>
                <b>{n.author_name}</b>
                <div className="meta">{n.body}</div>
              </div>
              <span className="muted" style={{ fontSize: '0.72rem' }}>{timeAgo(n.created_at)}</span>
            </div>
          ))}
          <label className="field" style={{ marginTop: 12 }}>
            Add note
            <textarea className="input" rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Investigation notes…" />
          </label>
          <button className="btn btn-sm btn-primary" style={{ marginTop: 8 }} onClick={submitNote} disabled={!note.trim()}>
            Save note
          </button>
        </Modal>
      )}
      {showNew && (
        <Modal
          title="New incident"
          onClose={() => setShowNew(false)}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button className="btn" onClick={() => setShowNew(false)}>Cancel</button>
              <button className="btn btn-primary" disabled={!newForm.title.trim()} onClick={createManual}>Create</button>
            </div>
          )}
        >
          <div style={{ display: 'grid', gap: 10 }}>
            <label className="field">Title
              <input className="input" value={newForm.title} maxLength={200} onChange={(e) => setNewForm({ ...newForm, title: e.target.value })} />
            </label>
            <label className="field">Description
              <textarea className="input" rows={3} value={newForm.description} onChange={(e) => setNewForm({ ...newForm, description: e.target.value })} />
            </label>
            <label className="field">Priority
              <select className="input" value={newForm.priority} onChange={(e) => setNewForm({ ...newForm, priority: e.target.value })}>
                {['low', 'medium', 'high', 'critical'].map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
          </div>
        </Modal>
      )}
    </>
  )
}
