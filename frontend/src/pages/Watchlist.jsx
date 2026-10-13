import { useEffect, useState } from 'react'
import { Card, Icons, Tag, Empty, Stat, timeAgo } from '../components/ui'
import { fetchReidPersons, personImageUrl } from '../services/api'

// The recogniser reports a person's ID (e.g. P-1A2B3C4D); older records may hold the name.
const isPerson = (p, label) => !!label && (label === p.person_id || label === p.name)

const THREAT_TONE = (lvl) => (lvl >= 4 ? 'danger' : lvl >= 2 ? 'warn' : 'ok')

export function Watchlist({ ctx }) {
  const { knownPersons, events, evidence, setPage } = ctx
  const [reid, setReid] = useState([])

  useEffect(() => {
    fetchReidPersons(72).then((r) => setReid(r.persons || [])).catch(() => {})
  }, [evidence.length])

  const lastSeen = (p) => {
    const hit = events.find((e) => isPerson(p, e.personName))
      || evidence.find((ev) => isPerson(p, ev.person_name))
    return hit ? (hit.time || hit.timestamp) : null
  }

  const detections = (p) =>
    events.filter((e) => isPerson(p, e.personName)).length +
    evidence.filter((ev) => isPerson(p, ev.person_name)).length

  return (
    <>
      <div className="grid grid-3 mb">
        <Stat label="People on the watchlist" value={knownPersons.length} delta="Matched live by every camera" accent="primary" icon={Icons.watchlist} />
        <Stat label="Wanted or suspect" value={knownPersons.filter((p) => ['wanted', 'suspect'].includes(p.criminal_status)).length} delta="Raise a critical alert when seen" accent="danger" icon={Icons.alert} />
        <Stat label="Seen on more than one camera" value={reid.filter((t) => t.cross_camera).length} delta="Last 72 hours" accent="cyan" icon={Icons.map} />
      </div>

      <div className="toolbar mb">
        <span className="muted">Photos are added and removed on the Faces page.</span>
        <span className="spacer" />
        <button className="btn btn-primary btn-sm" onClick={() => setPage('faces')}><Icons.watchlist /> Manage faces</button>
      </div>

      {knownPersons.length === 0 ? (
        <Card><Empty icon={Icons.watchlist}>No face records yet. Add one on the Faces page.</Empty></Card>
      ) : (
        <div className="grid grid-3 mb">
          {knownPersons.map((p) => {
            const seen = lastSeen(p)
            const count = detections(p)
            return (
              <Card key={p.id}>
                <div style={{ display: 'flex', gap: 14, alignItems: 'center', marginBottom: 12 }}>
                  {p.first_image_id ? (
                    <img src={personImageUrl(p.first_image_id)} alt={p.name}
                      style={{ width: 52, height: 52, borderRadius: '50%', objectFit: 'cover' }} />
                  ) : (
                    <div className="avatar" style={{ width: 52, height: 52, fontSize: '1.2rem' }}>
                      {p.name?.[0]?.toUpperCase() || '?'}
                    </div>
                  )}
                  <div style={{ minWidth: 0 }}>
                    <b style={{ fontSize: '0.95rem' }}>{p.name}</b>
                    <div className="meta mono">{p.person_id}</div>
                  </div>
                  <span className="spacer" />
                  <Tag tone={['wanted', 'convicted', 'suspect'].includes(p.criminal_status) ? 'danger' : 'ok'}>{p.criminal_status}</Tag>
                </div>
                <dl className="kv">
                  <dt>Category</dt><dd>{p.category || '—'}</dd>
                  <dt>Risk level</dt><dd><Tag tone={THREAT_TONE(p.threat_level)}>Level {p.threat_level}</Tag></dd>
                  <dt>Last seen</dt><dd>{seen ? timeAgo(seen) : 'Not in recent alerts'}</dd>
                  <dt>Detections</dt><dd>{count}</dd>
                  <dt>Photos</dt><dd>{p.image_count}{p.encoding_count ? '' : ' · no usable face found'}</dd>
                </dl>

              </Card>
            )
          })}
        </div>
      )}

      <Card title="Movement between cameras" sub="Where each recognised person was seen · last 72 hours">
        {reid.length === 0 && <Empty icon={Icons.map}>Nobody on the watchlist has been seen in the last 72 hours.</Empty>}
        {reid.slice(0, 15).map((t) => (
          <div key={t.person_name} className="row">
            <div>
              <b>{t.person_name}</b>
              <div className="meta">{t.sightings} sightings · {t.cameras.join(' → ')}</div>
            </div>
            <Tag tone={t.cross_camera ? 'info' : 'muted'}>{t.cross_camera ? 'Several cameras' : 'One camera'}</Tag>
          </div>
        ))}
      </Card>
    </>
  )
}
