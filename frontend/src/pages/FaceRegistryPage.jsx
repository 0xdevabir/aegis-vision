import { useMemo, useState } from 'react'
import { Card, Icons, Tag, Empty } from '../components/ui'
import { personImageUrl } from '../services/api'
import { EnrollModal, EvidenceCheck, ManagePersonModal, VerifyPanel } from '../components/FaceRegistry'

const THREAT_TONE = (lvl) => (lvl >= 4 ? 'danger' : lvl >= 2 ? 'warn' : 'ok')

export function FaceRegistryPage({ ctx }) {
  const { knownPersons, reloadKnownPersons, me, evidence = [] } = ctx
  const [enrolling, setEnrolling] = useState(false)
  const [managing, setManaging] = useState(null)
  const [query, setQuery] = useState('')
  const canEdit = me?.role === 'admin' || me?.role === 'supervisor'
  const canDelete = me?.role === 'admin'

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? knownPersons.filter((p) => `${p.name} ${p.person_id}`.toLowerCase().includes(q)) : knownPersons
  }, [knownPersons, query])

  return (
    <>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap' }}>
        <input className="input" style={{ maxWidth: 280 }} placeholder="Search name or ID…"
          value={query} onChange={(e) => setQuery(e.target.value)} />
        <span className="spacer" />
        {canEdit ? (
          <button className="btn btn-primary" onClick={() => setEnrolling(true)}>+ Enroll face</button>
        ) : (
          <span className="meta">Supervisor or admin access is required to enroll faces</span>
        )}
      </div>

      <div className="grid grid-2" style={{ marginBottom: 14, alignItems: 'start' }}>
        <VerifyPanel persons={knownPersons} />
        <Card title="How it works" sub="enroll once, matched everywhere">
          <ol className="meta" style={{ paddingLeft: 18, lineHeight: 1.7 }}>
            <li>Enroll a person with one or more clear, front-facing photos.</li>
            <li>Each photo becomes a face embedding stored in the database.</li>
            <li>Live cameras compare detected faces against every embedding.</li>
            <li>Use Verify to test any photo: you get MATCH, NO MATCH or NO FACE.</li>
          </ol>
          <div className="meta" style={{ marginTop: 8 }}>
            {knownPersons.length} record(s) · {knownPersons.reduce((n, p) => n + (p.encoding_count || 0), 0)} embeddings
          </div>
        </Card>
      </div>

      <div style={{ marginBottom: 14 }}>
        <EvidenceCheck evidence={evidence} />
      </div>

      {shown.length === 0 ? (
        <Card><Empty icon={Icons.watchlist}>{knownPersons.length ? 'No records match your search.' : 'No face records yet. Use “Enroll face” to add one.'}</Empty></Card>
      ) : (
        <div className="grid grid-3">
          {shown.map((p) => (
            <Card key={p.id}>
              <div style={{ display: 'flex', gap: 14, alignItems: 'center', marginBottom: 12 }}>
                {p.first_image_id ? (
                  <img src={personImageUrl(p.first_image_id)} alt={p.name}
                    style={{ width: 52, height: 52, borderRadius: '50%', objectFit: 'cover' }} />
                ) : (
                  <div className="avatar" style={{ width: 52, height: 52, fontSize: '1.2rem' }}>{p.name?.[0]?.toUpperCase() || '?'}</div>
                )}
                <div style={{ minWidth: 0 }}>
                  <b style={{ fontSize: '0.95rem' }}>{p.name}</b>
                  <div className="meta mono">{p.person_id}</div>
                </div>
                <span className="spacer" />
                <Tag tone={['wanted', 'convicted', 'suspect'].includes(p.criminal_status) ? 'danger' : 'ok'}>{p.criminal_status}</Tag>
              </div>
              <dl className="kv">
                <dt>Category</dt><dd>{(p.category || '—').replace(/_/g, ' ')}</dd>
                <dt>Risk Level</dt><dd><Tag tone={THREAT_TONE(p.threat_level)}>Level {p.threat_level}</Tag></dd>
                <dt>Photos</dt><dd>{p.image_count} · {p.encoding_count} embeddings</dd>
              </dl>
              <button className="btn btn-sm" style={{ marginTop: 10 }} onClick={() => setManaging(p)}>
                {canEdit ? 'Manage' : 'View'}
              </button>
            </Card>
          ))}
        </div>
      )}

      {enrolling && <EnrollModal onClose={() => setEnrolling(false)} onDone={reloadKnownPersons} />}
      {managing && (
        <ManagePersonModal person={managing} canEdit={canEdit} canDelete={canDelete}
          onClose={() => setManaging(null)} onChanged={reloadKnownPersons} />
      )}
    </>
  )
}
