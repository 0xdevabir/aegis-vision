import { useState } from 'react'
import { Card, Icons, Empty, Seg, Stat, timeAgo } from '../components/ui'
import { fetchIncidentReport } from '../services/api'
import { parseTs } from '../lib/time'

function download(filename, content, type) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// Quote every cell, and stop spreadsheet apps from running a cell that starts like a formula.
const csvCell = (v) => {
  const s = String(v ?? '')
  return `"${(/^[=+\-@]/.test(s) ? `'${s}` : s).replace(/"/g, '""')}"`
}

const RANGES = [{ value: 24, label: '24 h' }, { value: 72, label: '3 days' }, { value: 168, label: '7 days' }]

export function Reports({ ctx }) {
  const { report, events } = ctx
  const [hours, setHours] = useState(24)
  const [fetched, setFetched] = useState(null)      // { hours, data } from the last "generate"
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // The app preloads the 24 h report; other windows are fetched on demand.
  const current = fetched?.hours === hours ? fetched.data : (hours === 24 ? report : null)

  const generate = async (h) => {
    setHours(h); setLoading(true); setError('')
    try {
      setFetched({ hours: h, data: await fetchIncidentReport(h) })
    } catch (e) {
      setError(e.message || 'Could not generate the report')
    } finally {
      setLoading(false)
    }
  }

  const summary = current?.summary
  const matches = current?.breakdown?.criminals || []
  const weapons = current?.breakdown?.weapons || []
  const stamp = new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-')
  const rangeLabel = RANGES.find((r) => r.value === hours)?.label

  const exportJSON = () => download(`incident-report-${stamp}.json`, JSON.stringify(current, null, 2), 'application/json')

  const exportCSV = () => {
    const rows = [['type', 'severity', 'message', 'camera', 'time', 'lat', 'lng']]
    events.forEach((e) => rows.push([e.type, e.severity, e.msg, e.camera, e.time, e.lat, e.lng]))
    download(`alerts-${stamp}.csv`, rows.map((r) => r.map(csvCell).join(',')).join('\n'), 'text/csv')
  }

  return (
    <div className="grid grid-23">
      <Card
        title="Incident report"
        sub={`Last ${rangeLabel}`}
        actions={<Seg value={hours} onChange={generate} options={RANGES} />}
      >
        {error && <div className="login-error mb" role="alert">{error}</div>}
        {loading && <div className="skeleton" style={{ height: 180 }} aria-label="Generating report" />}
        {!loading && !summary && !error && (
          <Empty icon={Icons.report}>The report has not loaded yet. Pick a time range to generate it.</Empty>
        )}
        {!loading && summary && (
          <>
            <div className="report-meta">
              Generated {timeAgo(current.generated_at)}
              {parseTs(current.generated_at) && ` · ${parseTs(current.generated_at).toLocaleString()}`}
            </div>
            <div className="grid grid-2">
              <Stat label="Evidence records" value={summary.total_events} accent="primary" icon={Icons.evidence} />
              <Stat label="Alerts raised" value={summary.alerts_triggered} accent="cyan" icon={Icons.dispatch} />
              <Stat label="Watchlist matches" value={summary.criminal_detections} accent={summary.criminal_detections ? 'danger' : 'ok'} icon={Icons.watchlist} />
              <Stat label="Weapon detections" value={summary.weapon_detections} accent={summary.weapon_detections ? 'warn' : 'ok'} icon={Icons.alert} />
            </div>

            <h4 className="sub-head">Watchlist matches</h4>
            {matches.length === 0 && <p className="muted">None in this period.</p>}
            {matches.slice(0, 10).map((m, i) => (
              <div key={`${m.time}-${i}`} className="row">
                <div><b>{m.name || 'Unknown'}</b><div className="meta">{m.location || 'Unknown camera'}</div></div>
                <span className="muted">{timeAgo(m.time)}</span>
              </div>
            ))}

            <h4 className="sub-head">Weapon detections</h4>
            {weapons.length === 0 && <p className="muted">None in this period.</p>}
            {weapons.slice(0, 10).map((w, i) => (
              <div key={`${w.time}-${i}`} className="row">
                <span>{w.location || 'Unknown camera'}</span>
                <span className="muted">{timeAgo(w.time)}</span>
              </div>
            ))}
          </>
        )}
      </Card>

      <Card title="Export">
        <div className="stack" style={{ gap: 10 }}>
          <button className="btn btn-primary" onClick={exportJSON} disabled={!current}><Icons.download /> Download report (JSON)</button>
          <button className="btn" onClick={exportCSV} disabled={!events.length}><Icons.download /> Download recent alerts (CSV)</button>
          <button className="btn" onClick={() => window.print()}><Icons.report /> Print or save as PDF</button>
          <p className="note">
            The JSON file is the report shown here. The CSV holds the {events.length} most recent alerts loaded in this session.
            Printing uses your browser's dialog, where you can choose "Save as PDF".
          </p>
        </div>
      </Card>
    </div>
  )
}
