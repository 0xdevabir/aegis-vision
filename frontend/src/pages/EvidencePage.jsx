import { can } from '../lib/permissions'
import { useState } from 'react'
import { Card, Icons, Tag, Empty, timeAgo, Modal, Seg } from '../components/ui'
import { evidenceImageUrl, fetchCustody, verifyCustody, addCalibrationLabel } from '../services/api'
import { useToast } from '../components/Toast'

const kindIcon = (ev) => (ev.is_criminal ? Icons.watchlist : ev.weapon_present ? Icons.alert : ev.is_suspicious ? Icons.eye : Icons.camera)

export function EvidencePage({ ctx }) {
  const { evidence, me } = ctx
  const { push: toast } = useToast()
  const [busy, setBusy] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState(null)
  const [custody, setCustody] = useState(null)
  const [verifyResult, setVerifyResult] = useState(null)

  const filtered = evidence.filter((ev) => {
    if (filter === 'criminal' && !ev.is_criminal) return false
    if (filter === 'weapon' && !ev.weapon_present) return false
    if (filter === 'suspicious' && !ev.is_suspicious) return false
    if (query) {
      const hay = `${ev.person_name || ''} ${ev.camera_location || ''} ${ev.category || ''} ${ev.reasons || ''}`.toLowerCase()
      if (!hay.includes(query.toLowerCase())) return false
    }
    return true
  })

  const open = async (ev) => {
    setSelected(ev)
    setVerifyResult(null)
    setCustody(null)
    try {
      setCustody(await fetchCustody(ev.id))
    } catch (e) {
      toast(`Could not load the custody chain: ${e.message}`, 'danger')
    }
  }

  const doVerify = async () => {
    try {
      setVerifyResult(await verifyCustody(selected.id))
      setCustody(await fetchCustody(selected.id))
    } catch (e) {
      setVerifyResult({ ok: false, error: e.message })
    }
  }

  const labelFP = async () => {
    setBusy(true)
    try {
      await addCalibrationLabel({
        evidence_id: selected.id,
        detection_type: selected.category || 'unknown',
        predicted_label: selected.category,
        ground_truth: 'false_positive',
        notes: 'Marked false positive from Evidence Center',
      })
      toast('Marked as a false positive', 'ok')
    } catch (e) {
      toast(e.message || 'Could not save the label', 'danger')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="toolbar">
        <label className="search-input">
          <span className="sr-only">Search evidence</span>
          <Icons.search />
          <input className="input" type="search" placeholder="Search by person, camera or category…" value={query}
            onChange={(e) => setQuery(e.target.value)} />
        </label>
        <Seg
          value={filter}
          onChange={setFilter}
          options={[
            { value: 'all', label: 'All' },
            { value: 'criminal', label: 'Watchlist' },
            { value: 'weapon', label: 'Weapon' },
            { value: 'suspicious', label: 'Suspicious' },
          ]}
        />
        <span className="spacer" />
        <span className="muted" style={{ fontSize: '0.8rem' }}>{filtered.length} of {evidence.length} records</span>
      </div>

      {filtered.length === 0 ? (
        <Card><Empty icon={Icons.evidence}>{evidence.length ? 'No evidence matches this search or filter.' : 'No evidence yet. A snapshot is saved automatically whenever a camera detects something.'}</Empty></Card>
      ) : (
        <div className="evi-grid">
          {filtered.map((ev) => {
            const KindIcon = kindIcon(ev)
            return (
            <button type="button" key={ev.id} className="evi-card" onClick={() => open(ev)}
              aria-label={`Open evidence ${ev.id}: ${ev.person_name || `track ${ev.track_id}`}`}>
              <div className="evi-thumb" style={{ position: 'relative', overflow: 'hidden' }}>
                {ev.has_image ? (
                  <img
                    src={evidenceImageUrl(ev.id, 'roi')}
                    alt={ev.person_name || `Track ${ev.track_id}`}
                    loading="lazy"
                    style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }}
                    onError={(e) => { e.target.style.display = 'none' }}
                  />
                ) : <KindIcon />}
                <Tag tone={ev.is_criminal ? 'danger' : ev.weapon_present ? 'orange' : ev.is_suspicious ? 'warn' : 'ok'}>
                  {ev.category}
                </Tag>
              </div>
              <div className="evi-body">
                <b>{ev.person_name || `Track #${ev.track_id}`}</b>
                <div className="meta">{ev.camera_location} · {timeAgo(ev.timestamp)}</div>
                <div className="meta mono">{ev.content_sha256 ? `${ev.content_sha256.slice(0, 16)}…` : 'No hash recorded'}</div>
              </div>
            </button>
            )
          })}
        </div>
      )}

      {selected && (
        <Modal
          title={`Evidence #${selected.id}`}
          onClose={() => setSelected(null)}
          footer={
            <>
              {selected.has_image && (
                <a className="btn" href={evidenceImageUrl(selected.id, 'frame')} download={`evidence-${selected.id}.jpg`} target="_blank" rel="noreferrer">
                  <Icons.download /> Download
                </a>
              )}
              {can(me?.role, 'evidence.label') && <button className="btn" onClick={labelFP} disabled={busy}>Mark as false positive</button>}
              <button className="btn btn-primary" onClick={doVerify}><Icons.check /> Verify integrity</button>
            </>
          }
        >
          <div className="evi-thumb" style={{ borderRadius: 10, marginBottom: 18, fontSize: '2.4rem', position: 'relative', overflow: 'hidden', minHeight: 180 }}>
            {selected.has_image ? (
              <img
                src={evidenceImageUrl(selected.id, 'frame')}
                alt="Evidence frame"
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', background: 'var(--media)' }}
                onError={(e) => { e.target.style.display = 'none' }}
              />
            ) : (() => { const KindIcon = kindIcon(selected); return <KindIcon /> })()}
          </div>
          <dl className="kv" style={{ marginBottom: 18 }}>
            <dt>Subject</dt><dd>{selected.person_name || `Track #${selected.track_id}`}</dd>
            <dt>Category</dt><dd><Tag tone={selected.is_criminal ? 'danger' : 'info'}>{selected.category}</Tag></dd>
            <dt>Camera</dt><dd>{selected.camera_location}</dd>
            <dt>SHA-256</dt><dd className="mono">{selected.content_sha256 || custody?.content_sha256 || '—'}</dd>
            {verifyResult && (
              <>
                <dt>Integrity</dt>
                <dd>
                  <Tag tone={verifyResult.ok ? 'ok' : 'danger'}>
                    {verifyResult.ok ? 'Unchanged since capture' : (verifyResult.error || 'Does not match the recorded hash')}
                  </Tag>
                </dd>
              </>
            )}
          </dl>
          <h4 style={{ marginBottom: 10, fontSize: '0.9rem' }}>Chain of custody</h4>
          <div className="timeline">
            {(custody?.chain || []).length === 0 && (
              <div className="timeline-item"><div className="t-time">{timeAgo(selected.timestamp)}</div>Captured by AI pipeline</div>
            )}
            {(custody?.chain || []).map((c) => (
              <div key={c.id} className="timeline-item">
                <div className="t-time">{timeAgo(c.created_at)} · {c.actor}</div>
                <b>{c.action}</b>
                <div className="meta mono">{(c.record_hash || '').slice(0, 20)}…</div>
              </div>
            ))}
          </div>
        </Modal>
      )}
    </>
  )
}
