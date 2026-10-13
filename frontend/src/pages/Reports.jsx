import { useState } from 'react'
import { Card, Icons, Empty, Seg } from '../components/ui'
import { fetchIncidentReport } from '../services/api'

function download(filename, content, type) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function Reports({ ctx }) {
  const { report, events } = ctx
  const [hours, setHours] = useState(24)
  const [current, setCurrent] = useState(report)
  const [loading, setLoading] = useState(false)

  const generate = async (h) => {
    setHours(h); setLoading(true)
    try {
      setCurrent(await fetchIncidentReport(h))
    } catch { /* backend offline — keep last */ }
    setLoading(false)
  }

  const summary = current?.summary
  const stamp = new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-')

  const exportJSON = () => download(`incident-report-${stamp}.json`, JSON.stringify(current ?? { events }, null, 2), 'application/json')

  const exportCSV = () => {
    const rows = [['type', 'severity', 'message', 'camera', 'time', 'lat', 'lng']]
    events.forEach((e) => rows.push([e.type, e.severity, `"${(e.msg || '').replace(/"/g, "'")}"`, e.camera || '', e.time || '', e.lat ?? '', e.lng ?? '']))
    download(`events-${stamp}.csv`, rows.map((r) => r.join(',')).join('\n'), 'text/csv')
  }

  return (
    <div className="grid grid-23">
      <Card
        title="Incident Report"
        sub={`window: last ${hours}h`}
        actions={
          <Seg
            value={hours}
            onChange={generate}
            options={[{ value: 24, label: '24h' }, { value: 72, label: '3d' }, { value: 168, label: '7d' }]}
          />
        }
      >
        {loading && <p className="muted">Generating…</p>}
        {!loading && !summary && <Empty icon={Icons.report}>No report yet — backend must be online</Empty>}
        {!loading && summary && (
          <>
            <div className="grid grid-2" style={{ marginBottom: 16 }}>
              <div className="stat accent-primary"><span className="label">Total Events</span><span className="value">{summary.total_events}</span></div>
              <div className="stat accent-danger"><span className="label">Criminal Detections</span><span className="value">{summary.criminal_detections}</span></div>
              <div className="stat accent-warn"><span className="label">Weapon Detections</span><span className="value">{summary.weapon_detections}</span></div>
              <div className="stat accent-cyan"><span className="label">Alerts Triggered</span><span className="value">{summary.alerts_triggered}</span></div>
            </div>
            {current.top_locations?.length > 0 && (
              <>
                <h4 style={{ marginBottom: 8, fontSize: '0.88rem' }}>Top Locations</h4>
                {current.top_locations.map((l, i) => (
                  <div key={i} className="row"><span>{l.location || l[0]}</span><b>{l.events ?? l[1]}</b></div>
                ))}
              </>
            )}
          </>
        )}
      </Card>

      <Card title="One-Click Export">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <button className="btn btn-primary" onClick={exportJSON}><Icons.download /> Export JSON report</button>
          <button className="btn" onClick={exportCSV}><Icons.download /> Export events CSV</button>
          <button className="btn" onClick={() => window.print()}><Icons.report /> Print / Save as PDF</button>
          <p className="muted" style={{ fontSize: '0.78rem', lineHeight: 1.6 }}>
            JSON contains the full incident summary from the backend. CSV exports the live event feed.
            Use the browser print dialog for a formatted PDF of the current page.
          </p>
        </div>
      </Card>
    </div>
  )
}
