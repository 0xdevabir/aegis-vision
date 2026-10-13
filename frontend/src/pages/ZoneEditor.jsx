import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Card, Icons, Tag, Seg, useConfirm } from '../components/ui'
import { fetchCameraGeometry, saveCameraGeometry, snapshotUrl } from '../services/api'
import { useToast } from '../components/Toast'
import { clamp01, centroid, core, dist, nextName, validateNames } from '../lib/geometry'

const TOOL_HINT = {
  select: 'Click a shape to edit it. Drag its white handles to reshape.',
  zone: 'Click to place corners. Click the first corner or press Enter to close the zone.',
  line: 'Click the start, then the end. Crossings are recorded with a direction (+ or −).',
}

export function ZoneEditor({ ctx }) {
  const { cameras = [], streamingCams = [], me } = ctx
  const { push: toast } = useToast()
  const [ask, confirmDialog] = useConfirm()
  const canEdit = me?.role === 'admin' || me?.role === 'supervisor'

  const firstCam = useMemo(() => {
    const ids = cameras.map((c) => c.camera_id)
    return ids.find((id) => streamingCams.includes(id)) || ids[0] || ''
  }, [cameras, streamingCams])
  const [camId, setCamId] = useState('')
  const activeCam = camId || firstCam

  const [zones, setZones] = useState([])
  const [lines, setLines] = useState([])
  const [saved, setSaved] = useState(core([], []))
  const [loaded, setLoaded] = useState(false)
  const [sel, setSel] = useState(null)               // {kind:'zone'|'line', i}
  const [tool, setTool] = useState('select')
  const [draft, setDraft] = useState([])             // points of the shape being drawn
  const [cursor, setCursor] = useState(null)
  const [saving, setSaving] = useState(false)
  const [imgKey, setImgKey] = useState(() => Date.now())
  const [imgOk, setImgOk] = useState(false)
  const [aspect, setAspect] = useState(16 / 9)
  const canvasRef = useRef(null)
  const drag = useRef(null)

  const dirty = core(zones, lines) !== saved
  const nameError = validateNames(zones, lines)

  /* Load the saved geometry whenever the camera changes. */
  useEffect(() => {
    if (!activeCam) return undefined
    let alive = true
    fetchCameraGeometry(activeCam)
      .then((g) => {
        if (!alive) return
        setZones(g.zones || []); setLines(g.lines || [])
        setSaved(core(g.zones || [], g.lines || []))
        setSel(null); setDraft([]); setTool('select'); setLoaded(true)
      })
      .catch((e) => { if (alive) { toast(e.message || 'Could not load zones', 'danger'); setLoaded(true) } })
    return () => { alive = false }
  }, [activeCam, toast])

  /* Warn before leaving with unsaved work. */
  useEffect(() => {
    if (!dirty) return undefined
    const h = (e) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', h)
    return () => window.removeEventListener('beforeunload', h)
  }, [dirty])

  const toNorm = (e) => {
    const r = canvasRef.current.getBoundingClientRect()
    return [clamp01((e.clientX - r.left) / r.width), clamp01((e.clientY - r.top) / r.height)]
  }

  const allNames = [...zones, ...lines].map((s) => s.name)

  const finishZone = useCallback((points) => {
    if (points.length < 3) { toast('A zone needs at least 3 corners', 'danger'); return }
    const name = nextName('Zone', [...zones, ...lines].map((s) => s.name))
    setZones((z) => [...z, { name, type: 'monitor', polygon: points }])
    setSel({ kind: 'zone', i: zones.length })
    setDraft([]); setTool('select')
  }, [zones, lines, toast])

  const onCanvasClick = (e) => {
    if (!canEdit) return
    if (tool === 'select') { setSel(null); return }
    const p = toNorm(e)
    if (tool === 'zone') {
      if (draft.length >= 3 && dist(p, draft[0]) < 0.03) { finishZone(draft); return }
      if (draft.length && dist(p, draft[draft.length - 1]) < 0.006) return   // dblclick duplicate
      setDraft((d) => [...d, p])
    } else if (tool === 'line') {
      if (!draft.length) { setDraft([p]); return }
      if (dist(p, draft[0]) < 0.01) return
      const name = nextName('Line', allNames)
      setLines((l) => [...l, { name, p1: draft[0], p2: p }])
      setSel({ kind: 'line', i: lines.length })
      setDraft([]); setTool('select')
    }
  }

  const movePoint = (e, kind, i, j) => {
    if (!drag.current) return
    const p = toNorm(e)
    if (kind === 'zone') {
      setZones((zs) => zs.map((z, zi) => (zi !== i ? z : { ...z, polygon: z.polygon.map((q, qi) => (qi === j ? p : q)) })))
    } else {
      setLines((ls) => ls.map((l, li) => (li !== i ? l : { ...l, [j === 0 ? 'p1' : 'p2']: p })))
    }
  }

  const remove = useCallback((s) => {
    if (!s) return
    if (s.kind === 'zone') setZones((z) => z.filter((_, i) => i !== s.i))
    else setLines((l) => l.filter((_, i) => i !== s.i))
    setSel(null)
  }, [])

  const keys = useRef(null)
  useEffect(() => { keys.current = { tool, draft, sel, finishZone, remove } }, [tool, draft, sel, finishZone, remove])
  useEffect(() => {
    const onKey = (e) => {
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return
      const k = keys.current
      if (e.key === 'Enter' && k.tool === 'zone' && k.draft.length) { e.preventDefault(); k.finishZone(k.draft) }
      else if (e.key === 'Escape') { setDraft([]); setSel(null); setTool('select') }
      else if ((e.key === 'Delete' || e.key === 'Backspace') && k.sel) { e.preventDefault(); k.remove(k.sel) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const switchCamera = async (id) => {
    if (dirty && !(await ask({ title: 'Unsaved changes', message: 'Discard unsaved changes to this camera?', confirmLabel: 'Discard', danger: true }))) return
    setLoaded(false); setCamId(id); setImgOk(false); setImgKey(Date.now())
  }

  const save = async () => {
    if (nameError) { toast(nameError, 'danger'); return }
    setSaving(true)
    try {
      const g = await saveCameraGeometry(activeCam, { zones, lines })
      setZones(g.zones); setLines(g.lines); setSaved(core(g.zones, g.lines))
      toast('Saved — the camera applies it within about 30 seconds', 'ok')
    } catch (e) {
      toast(e.message || 'Could not save', 'danger')
    } finally {
      setSaving(false)
    }
  }

  const revert = () => {
    const g = JSON.parse(saved)
    setZones(g.zones); setLines(g.lines); setSel(null); setDraft([])
  }

  const selShape = sel && (sel.kind === 'zone' ? zones[sel.i] : lines[sel.i])
  const rename = (name) => {
    if (sel.kind === 'zone') setZones((z) => z.map((s, i) => (i === sel.i ? { ...s, name } : s)))
    else setLines((l) => l.map((s, i) => (i === sel.i ? { ...s, name } : s)))
  }
  const pct = (v) => `${v * 100}%`

  if (!cameras.length) {
    return (
      <>
        <div className="page-head"><div><h2>Zones &amp; Lines</h2></div></div>
        <Card><p className="muted">No cameras yet. Add one under Camera Management first.</p></Card>
      </>
    )
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h2>Zones &amp; Lines</h2>
          <p>Draw restricted areas and counting lines over the camera view.</p>
        </div>
        <div className="head-actions">
          <label className="field inline">
            <span className="sr-only">Camera</span>
            <select value={activeCam} onChange={(e) => switchCamera(e.target.value)} aria-label="Camera">
              {cameras.map((c) => <option key={c.camera_id} value={c.camera_id}>{c.name || c.camera_id}</option>)}
            </select>
          </label>
          {dirty && <Tag tone="warn">Unsaved changes</Tag>}
          <button type="button" className="btn btn-primary" disabled={!canEdit || !dirty || saving || !!nameError} onClick={save}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="btn" disabled={!dirty} onClick={revert}>Revert</button>
        </div>
      </div>

      <div className="ze">
        <Card flush>
          <div
            ref={canvasRef}
            className={`ze-canvas ${tool !== 'select' ? 'drawing' : ''} ${imgOk ? '' : 'nofeed'}`}
            style={{ aspectRatio: aspect }}
            onClick={onCanvasClick}
            onDoubleClick={() => { if (tool === 'zone' && draft.length >= 3) finishZone(draft) }}
            onMouseMove={(e) => { if (tool !== 'select' && draft.length) setCursor(toNorm(e)) }}
            onMouseLeave={() => setCursor(null)}
            role="application"
            aria-label="Zone drawing canvas"
          >
            <img
              key={`${activeCam}-${imgKey}`}
              src={`${snapshotUrl(activeCam)}${snapshotUrl(activeCam).includes('?') ? '&' : '?'}t=${imgKey}`}
              alt="" draggable={false}
              onLoad={(e) => { setImgOk(true); setAspect(e.target.naturalWidth / e.target.naturalHeight || 16 / 9) }}
              onError={() => setImgOk(false)}
              style={{ display: imgOk ? 'block' : 'none' }}
            />
            {!imgOk && (
              <div className="ze-nofeed">
                <Icons.camera />
                <div>No live frame from this camera.<br />Start the pipeline to draw on the real view — you can still place shapes on this grid.</div>
              </div>
            )}

            <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="ze-svg" style={{ pointerEvents: tool === 'select' ? 'auto' : 'none' }}>
              {zones.map((z, i) => (
                <polygon
                  key={`z${i}`}
                  points={z.polygon.map((p) => `${p[0] * 100},${p[1] * 100}`).join(' ')}
                  className={`ze-zone ${z.type} ${sel?.kind === 'zone' && sel.i === i ? 'on' : ''}`}
                  onClick={(e) => { e.stopPropagation(); setSel({ kind: 'zone', i }) }}
                />
              ))}
              {lines.map((l, i) => (
                <line
                  key={`l${i}`} x1={l.p1[0] * 100} y1={l.p1[1] * 100} x2={l.p2[0] * 100} y2={l.p2[1] * 100}
                  className={`ze-line ${sel?.kind === 'line' && sel.i === i ? 'on' : ''}`}
                  onClick={(e) => { e.stopPropagation(); setSel({ kind: 'line', i }) }}
                />
              ))}
              {draft.length > 0 && tool === 'zone' && (
                <polyline className="ze-draft" fill="none"
                  points={[...draft, ...(cursor ? [cursor] : [])].map((p) => `${p[0] * 100},${p[1] * 100}`).join(' ')} />
              )}
              {draft.length === 1 && tool === 'line' && cursor && (
                <line className="ze-draft" x1={draft[0][0] * 100} y1={draft[0][1] * 100} x2={cursor[0] * 100} y2={cursor[1] * 100} />
              )}
            </svg>

            {zones.map((z, i) => {
              const c = centroid(z.polygon)
              return <span key={`zl${i}`} className={`ze-label ${z.type}`} style={{ left: pct(c[0]), top: pct(c[1]) }}>{z.name}</span>
            })}
            {lines.map((l, i) => (
              <span key={`ll${i}`} className="ze-label line" style={{ left: pct((l.p1[0] + l.p2[0]) / 2), top: pct((l.p1[1] + l.p2[1]) / 2) }}>{l.name}</span>
            ))}
            {draft.map((p, i) => <span key={`d${i}`} className="ze-dot" style={{ left: pct(p[0]), top: pct(p[1]) }} />)}

            {canEdit && sel && tool === 'select' && selShape && (sel.kind === 'zone' ? selShape.polygon : [selShape.p1, selShape.p2]).map((p, j) => (
              <button
                key={`h${sel.kind}${sel.i}-${j}`} type="button" className="ze-handle"
                style={{ left: pct(p[0]), top: pct(p[1]) }}
                aria-label={`Move point ${j + 1} of ${selShape.name}`}
                onClick={(e) => e.stopPropagation()}
                onPointerDown={(e) => { e.stopPropagation(); e.currentTarget.setPointerCapture(e.pointerId); drag.current = true }}
                onPointerMove={(e) => movePoint(e, sel.kind, sel.i, j)}
                onPointerUp={(e) => { e.currentTarget.releasePointerCapture(e.pointerId); drag.current = null }}
              >{sel.kind === 'line' ? (j === 0 ? 'A' : 'B') : ''}</button>
            ))}
          </div>
        </Card>

        <div className="ze-side">
          <Card title="Tools">
            <Seg
              value={tool}
              onChange={(t) => { if (canEdit) { setTool(t); setDraft([]); if (t !== 'select') setSel(null) } }}
              options={[{ value: 'select', label: 'Select' }, { value: 'zone', label: 'Draw zone' }, { value: 'line', label: 'Draw line' }]}
            />
            <p className="muted ze-hint">{canEdit ? TOOL_HINT[tool] : 'Read-only: only supervisors and admins can change zones.'}</p>
            <div className="a-actions">
              <button type="button" className="btn btn-sm" onClick={() => { setImgKey(Date.now()); setImgOk(false) }}>Refresh view</button>
            </div>
          </Card>

          <Card title="Shapes" sub={`${zones.length} zone${zones.length === 1 ? '' : 's'} · ${lines.length} line${lines.length === 1 ? '' : 's'}`}>
            {loaded && !zones.length && !lines.length && (
              <p className="muted">
                None yet. With no zones the frame is split into four quadrants (crowd and dwell checks only).
              </p>
            )}
            {zones.map((z, i) => (
              <button key={`zi${i}`} type="button" className={`ze-item ${sel?.kind === 'zone' && sel.i === i ? 'on' : ''}`}
                onClick={() => { setSel({ kind: 'zone', i }); setTool('select') }}>
                <span className={`ze-swatch ${z.type}`} /> <b>{z.name}</b>
                <Tag tone={z.type === 'restricted' ? 'danger' : 'info'}>{z.type}</Tag>
              </button>
            ))}
            {lines.map((l, i) => (
              <button key={`li${i}`} type="button" className={`ze-item ${sel?.kind === 'line' && sel.i === i ? 'on' : ''}`}
                onClick={() => { setSel({ kind: 'line', i }); setTool('select') }}>
                <span className="ze-swatch line" /> <b>{l.name}</b><Tag tone="muted">line</Tag>
              </button>
            ))}
          </Card>

          {selShape && (
            <Card title="Selected">
              <label className="field">
                <span>Name</span>
                <input value={selShape.name} disabled={!canEdit} maxLength={50} onChange={(e) => rename(e.target.value)} />
              </label>
              {sel.kind === 'zone' && (
                <label className="field">
                  <span>Type</span>
                  <select value={selShape.type} disabled={!canEdit}
                    onChange={(e) => setZones((z) => z.map((s, i) => (i === sel.i ? { ...s, type: e.target.value } : s)))}>
                    <option value="monitor">Monitor — crowd and dwell checks</option>
                    <option value="restricted">Restricted — alert when anyone enters</option>
                  </select>
                </label>
              )}
              {nameError && <p className="login-error" role="alert">{nameError}</p>}
              {canEdit && <button type="button" className="btn btn-sm" onClick={() => remove(sel)}><Icons.close /> Delete <kbd>Del</kbd></button>}
            </Card>
          )}
        </div>
      </div>
      {confirmDialog}
    </>
  )
}
