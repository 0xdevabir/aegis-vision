/* Face registry UI: enroll photos, verify a probe photo against stored records. */
import { useEffect, useMemo, useState } from 'react'
import { Card, Icons, Modal, Tag, timeAgo, useConfirm } from './ui'
import {
  enrollPerson, addPersonImages, fetchPersonDetail, updatePerson, deletePerson,
  deletePersonImage, verifyFace, verifyEvidence, personImageUrl, evidenceImageUrl,
} from '../services/api'

const CATEGORIES = ['criminal', 'person_of_interest', 'missing_person', 'civilian']
const STATUSES = ['wanted', 'convicted', 'suspect', 'cleared', 'unknown']
const label = (s) => s.replace(/_/g, ' ')

function useObjectUrls(files) {
  const urls = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files])
  useEffect(() => () => urls.forEach((u) => URL.revokeObjectURL(u)), [urls])
  return urls
}

function Thumbs({ files, onRemove }) {
  const urls = useObjectUrls(files)
  if (!files.length) return null
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
      {urls.map((u, i) => (
        <div key={u} style={{ position: 'relative' }}>
          <img src={u} alt={files[i].name} style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: 8 }} />
          {onRemove && (
            <button type="button" className="icon-btn" aria-label="Remove photo"
              style={{ position: 'absolute', top: -6, right: -6 }} onClick={() => onRemove(i)}>
              <Icons.close />
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

function Results({ results }) {
  if (!results?.length) return null
  return (
    <div style={{ marginTop: 12 }}>
      {results.map((r, i) => (
        <div key={i} className="row">
          <div>
            <b>{r.filename || `Photo ${i + 1}`}</b>
            {r.status === 'rejected' && <div className="meta">{r.reason}</div>}
            {r.possible_duplicate_of?.length > 0 && (
              <div className="meta">
                Already resembles: {r.possible_duplicate_of.map((d) => `${d.name} (${d.person_id})`).join(', ')}
              </div>
            )}
          </div>
          <Tag tone={r.status === 'enrolled' ? (r.possible_duplicate_of?.length ? 'warn' : 'ok') : 'danger'}>
            {r.status}
          </Tag>
        </div>
      ))}
    </div>
  )
}

const MAX_PHOTOS = 30   // keep in sync with MAX_FILES in backend/api/face_routes.py
const IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp,image/bmp,.jpg,.jpeg,.png,.webp,.bmp'

export function EnrollModal({ onClose, onDone }) {
  const [form, setForm] = useState({ name: '', category: 'civilian', criminalStatus: 'unknown', threatLevel: 0, notes: '' })
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [results, setResults] = useState(null)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const setCategory = (e) => {
    const category = e.target.value
    // Reset risk fields so a civilian can never carry a leftover "wanted" status.
    setForm((f) => (category === 'criminal'
      ? { ...f, category, criminalStatus: 'wanted', threatLevel: f.threatLevel || 5 }
      : { ...f, category, criminalStatus: 'unknown', threatLevel: 0 }))
  }
  const alerts = form.category === 'criminal' && ['wanted', 'convicted', 'suspect'].includes(form.criminalStatus)

  const submit = async () => {
    setBusy(true); setError(''); setResults(null)
    try {
      const res = await enrollPerson({ ...form, threatLevel: Number(form.threatLevel), files })
      setResults(res.results)
      onDone()
      if (!res.results.some((r) => r.possible_duplicate_of?.length || r.status !== 'enrolled')) onClose()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title="Enroll face record" onClose={onClose} footer={
      <>
        <button className="btn" onClick={onClose}>{results ? 'Close' : 'Cancel'}</button>
        {!results && (
          <button className="btn btn-primary" disabled={busy || !form.name.trim() || !files.length} onClick={submit}>
            {busy ? 'Encoding…' : `Enroll ${files.length || ''} photo${files.length === 1 ? '' : 's'}`}
          </button>
        )}
      </>
    }>
      <div style={{ display: 'grid', gap: 12 }}>
        <label className="field">Full name
          <input className="input" value={form.name} onChange={set('name')} maxLength={100} autoFocus />
        </label>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
          <label className="field">Category
            <select className="input" value={form.category} onChange={setCategory}>
              {CATEGORIES.map((c) => <option key={c} value={c}>{label(c)}</option>)}
            </select>
          </label>
          <label className="field">Status
            <select className="input" value={form.criminalStatus} onChange={set('criminalStatus')}>
              {STATUSES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label className="field">Threat (0-10)
            <input className="input" type="number" min={0} max={10} value={form.threatLevel} onChange={set('threatLevel')} />
          </label>
        </div>
        <div className="muted" style={{ fontSize: 12 }}>
          {alerts
            ? 'This person WILL raise a live criminal alert when seen on camera.'
            : 'Recognised on camera but will NOT raise a criminal alert. Only category Criminal with status wanted, convicted or suspect alerts.'}
        </div>
        <label className="field">Notes
          <textarea className="input" rows={2} value={form.notes} onChange={set('notes')} />
        </label>
        <label className="field">Face photos (JPG/PNG/WEBP, select many at once, up to 30; one clear face each)
          <input className="input" type="file" accept={IMAGE_ACCEPT} multiple
            onChange={(e) => {
              const picked = Array.from(e.target.files)      // read before clearing: the FileList is live
              e.target.value = ''                            // lets the same files be picked again
              setFiles((prev) => {
                const key = (f) => `${f.name}|${f.size}|${f.lastModified}`
                const seen = new Set(prev.map(key))
                const merged = [...prev, ...picked.filter((f) => !seen.has(key(f)))]
                if (merged.length > MAX_PHOTOS) setError(`Only the first ${MAX_PHOTOS} photos are kept.`)
                return merged.slice(0, MAX_PHOTOS)
              })
            }} />
        </label>
        <Thumbs files={files} onRemove={(i) => setFiles((f) => f.filter((_, j) => j !== i))} />
        {error && <div className="login-error" role="alert">{error}</div>}
        <Results results={results} />
      </div>
    </Modal>
  )
}

export function ManagePersonModal({ person, canEdit, canDelete, onClose, onChanged }) {
  const [ask, confirmDialog] = useConfirm()
  const [detail, setDetail] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [results, setResults] = useState(null)
  const [meta, setMeta] = useState(null)

  const load = () => fetchPersonDetail(person.person_id).then((d) => {
    setDetail(d)
    setMeta((m) => m || { category: d.category, criminal_status: d.criminal_status, threat_level: d.threat_level, notes: d.notes || '' })
  }).catch((e) => setError(e.message))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, [person.person_id])

  const run = async (fn) => {
    setBusy(true); setError('')
    try { await fn(); await load(); onChanged() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <>
    <Modal title={`${person.name} · ${person.person_id}`} onClose={onClose}>
      {error && <div className="login-error" role="alert">{error}</div>}
      {!detail || !meta ? <div className="meta">Loading…</div> : (
        <div style={{ display: 'grid', gap: 12 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {detail.images.map((img) => (
              <div key={img.id} style={{ position: 'relative' }}>
                <img src={personImageUrl(img.id)} alt={img.filename || 'enrolled face'}
                  style={{ width: 84, height: 84, objectFit: 'cover', borderRadius: 8 }} />
                {canEdit && detail.images.length > 1 && (
                  <button className="icon-btn" aria-label="Delete photo" disabled={busy}
                    style={{ position: 'absolute', top: -6, right: -6 }}
                    onClick={() => run(() => deletePersonImage(img.id))}><Icons.close /></button>
                )}
              </div>
            ))}
          </div>
          <div className="meta">{detail.encoding_count} face embedding(s) from {detail.image_count} photo(s)</div>

          {canEdit && (
            <>
              <label className="field">Add more photos
                <input className="input" type="file" accept={IMAGE_ACCEPT} multiple disabled={busy}
                  onChange={(e) => {
                    const files = Array.from(e.target.files).slice(0, MAX_PHOTOS)
                    e.target.value = ''
                    run(async () => setResults((await addPersonImages(person.person_id, files)).results))
                  }} />
              </label>
              <Results results={results} />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
                <label className="field">Category
                  <select className="input" value={meta.category} onChange={(e) => setMeta({ ...meta, category: e.target.value })}>
                    {CATEGORIES.map((c) => <option key={c} value={c}>{label(c)}</option>)}
                  </select>
                </label>
                <label className="field">Status
                  <select className="input" value={meta.criminal_status} onChange={(e) => setMeta({ ...meta, criminal_status: e.target.value })}>
                    {STATUSES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </label>
                <label className="field">Threat
                  <input className="input" type="number" min={0} max={10} value={meta.threat_level}
                    onChange={(e) => setMeta({ ...meta, threat_level: Number(e.target.value) })} />
                </label>
              </div>
              <label className="field">Notes
                <textarea className="input" rows={2} value={meta.notes} onChange={(e) => setMeta({ ...meta, notes: e.target.value })} />
              </label>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-primary" disabled={busy} onClick={() => run(() => updatePerson(person.person_id, meta))}>Save changes</button>
                <span className="spacer" />
                {canDelete && (
                  <button className="btn btn-danger" disabled={busy} onClick={async () => {
                    if (await ask({ title: 'Delete record', message: `Delete ${person.name} and all stored photos? This cannot be undone.`, confirmLabel: 'Delete', danger: true })) {
                      run(async () => { await deletePerson(person.person_id); onClose() })
                    }
                  }}>Delete record</button>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </Modal>
    {confirmDialog}
    </>
  )
}

const VERDICT = {
  match: { tone: 'danger', text: 'MATCH' },
  no_match: { tone: 'ok', text: 'NO MATCH' },
  no_face: { tone: 'warn', text: 'NO FACE FOUND' },
}

export function VerifyPanel({ persons }) {
  const [file, setFile] = useState(null)
  const [target, setTarget] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [res, setRes] = useState(null)
  const files = useMemo(() => (file ? [file] : []), [file])
  const [preview] = useObjectUrls(files)
  const byId = useMemo(() => Object.fromEntries(persons.map((p) => [p.person_id, p])), [persons])

  const run = async () => {
    setBusy(true); setError(''); setRes(null)
    try { setRes(await verifyFace(file, target || undefined)) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const best = res?.best_match
  const bestPerson = best && byId[best.person_id]
  const verdict = res && VERDICT[res.status]

  return (
    <Card title="Verify a face" sub="match a photo against enrolled records">
      <div style={{ display: 'grid', gap: 10 }}>
        <input className="input" type="file" accept="image/jpeg,image/png"
          onChange={(e) => { setFile(e.target.files[0] || null); setRes(null); setError('') }} />
        <label className="field">Check against
          <select className="input" value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">All enrolled records (search)</option>
            {persons.map((p) => <option key={p.person_id} value={p.person_id}>{p.name} · {p.person_id}</option>)}
          </select>
        </label>
        <button className="btn btn-primary" disabled={!file || busy} onClick={run}>{busy ? 'Analyzing…' : 'Run match'}</button>
        {error && <div className="login-error" role="alert">{error}</div>}
      </div>

      {(preview || res) && (
        <div style={{ display: 'flex', gap: 14, marginTop: 14, alignItems: 'flex-start' }}>
          {preview && <img src={preview} alt="probe" style={{ width: 120, height: 120, objectFit: 'cover', borderRadius: 10 }} />}
          {res && (
            <div style={{ minWidth: 0, flex: 1 }}>
              <Tag tone={verdict.tone}>{verdict.text}</Tag>
              <div className="meta" style={{ marginTop: 6 }}>
                {res.face_count} face(s) detected · {res.mode} · threshold {res.threshold}
              </div>
              {best && (
                <dl className="kv" style={{ marginTop: 8 }}>
                  <dt>Identity</dt><dd><b>{best.name}</b> <span className="mono">{best.person_id}</span></dd>
                  <dt>Category</dt><dd>{label(best.category)} · {best.criminal_status}</dd>
                  <dt>Risk</dt><dd>Level {best.threat_level}</dd>
                  <dt>Distance</dt><dd>{best.distance} (≤ {res.threshold} = match)</dd>
                  <dt>Confidence</dt><dd>{Math.round(best.confidence * 100)}%</dd>
                </dl>
              )}
              {res.status === 'no_match' && res.faces[0]?.candidates?.[0] && (
                <div className="meta" style={{ marginTop: 6 }}>
                  Closest record: {res.faces[0].candidates[0].name} (distance {res.faces[0].candidates[0].distance}), above threshold
                </div>
              )}
              {res.status === 'no_face' && <div className="meta" style={{ marginTop: 6 }}>Use a sharper, front-facing photo.</div>}
            </div>
          )}
          {bestPerson?.first_image_id && (
            <img src={personImageUrl(bestPerson.first_image_id)} alt="matched record"
              style={{ width: 120, height: 120, objectFit: 'cover', borderRadius: 10 }} />
          )}
        </div>
      )}
      {res?.status === 'match' && res.faces.length > 1 && (
        <div className="meta" style={{ marginTop: 10 }}>
          Multiple faces in photo; other matches: {res.faces.filter((f) => f.best && f.best !== best).map((f) => f.best.name).join(', ') || 'none'}
        </div>
      )}
    </Card>
  )
}

/* ——— Evidence check: does a captured image match an enrolled face? ——— */
function EvidenceRow({ ev, result, busy, onCheck }) {
  const verdict = result && !result.error && VERDICT[result.status]
  return (
    <div className="row" style={{ alignItems: 'flex-start', gap: 12 }}>
      <img src={evidenceImageUrl(ev.id, ev.has_image ? 'roi' : 'frame')} alt={`evidence ${ev.id}`}
        style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: 8, background: '#020617' }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <b>#{ev.id} · {ev.category}</b>
        <div className="meta">{ev.camera_location} · {timeAgo(ev.timestamp)}</div>
        {result?.error && <div className="meta" style={{ color: 'var(--danger)' }}>{result.error}</div>}
        {verdict && (
          <div style={{ marginTop: 6, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <Tag tone={verdict.tone}>{verdict.text}</Tag>
            {result.best_match && (
              <span className="meta">
                <b>{result.best_match.name}</b> ({result.best_match.person_id}) · distance {result.best_match.distance}
                · {Math.round(result.best_match.confidence * 100)}%
              </span>
            )}
            {result.status === 'no_match' && result.faces[0]?.candidates?.[0] && (
              <span className="meta">closest: {result.faces[0].candidates[0].name} ({result.faces[0].candidates[0].distance})</span>
            )}
            {result.status === 'no_face' && <span className="meta">no usable face in this capture</span>}
            {result.agrees_with_live_id === true && <Tag tone="ok">live ID agrees</Tag>}
            {result.agrees_with_live_id === false && <Tag tone="warn">live ID differs: {result.recorded_identity}</Tag>}
          </div>
        )}
      </div>
      <button className="btn btn-sm" disabled={busy} onClick={onCheck}>{busy ? 'Checking…' : result ? 'Re-check' : 'Check'}</button>
    </div>
  )
}

export function EvidenceCheck({ evidence }) {
  const [results, setResults] = useState({})
  const [busyId, setBusyId] = useState(null)
  const [bulk, setBulk] = useState(false)
  const items = useMemo(() => evidence.filter((e) => e.has_image).slice(0, 12), [evidence])

  const check = async (id) => {
    setBusyId(id)
    try {
      const r = await verifyEvidence(id)
      setResults((m) => ({ ...m, [id]: r }))
    } catch (e) {
      setResults((m) => ({ ...m, [id]: { error: e.message } }))
    } finally {
      setBusyId(null)
    }
  }
  const checkAll = async () => {
    setBulk(true)
    for (const ev of items) await check(ev.id)   // sequential: face encoding is CPU heavy
    setBulk(false)
  }
  const counts = Object.values(results).reduce((c, r) => { if (r.status) c[r.status] = (c[r.status] || 0) + 1; return c }, {})

  return (
    <Card title="Evidence check" sub="is a captured image a match or not?"
      actions={<button className="btn btn-sm btn-primary" disabled={bulk || busyId !== null || !items.length} onClick={checkAll}>
        {bulk ? 'Checking…' : `Check latest ${items.length}`}</button>}>
      {Object.keys(results).length > 0 && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
          <Tag tone="danger">{counts.match || 0} match</Tag>
          <Tag tone="ok">{counts.no_match || 0} no match</Tag>
          <Tag tone="warn">{counts.no_face || 0} no face</Tag>
        </div>
      )}
      {items.length === 0
        ? <div className="meta">No evidence images captured yet.</div>
        : items.map((ev) => (
          <EvidenceRow key={ev.id} ev={ev} result={results[ev.id]} busy={busyId === ev.id} onCheck={() => check(ev.id)} />
        ))}
    </Card>
  )
}
