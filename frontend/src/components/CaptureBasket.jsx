import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Card, Icons, Modal, Seg, Tag, timeAgo } from './ui'
import { useToast } from './Toast'
import { eventLabel } from '../lib/events'
import { parseTs } from '../lib/time'
import { captureImageUrl, fetchCaptureScope, fetchCaptures, setCaptureScope } from '../services/api'

const DEFAULT_GAP = 5          // seconds between pictures unless the stream shows otherwise
const KEEP = 300
const SUSPICIOUS = 'SUSPICIOUS_BEHAVIOR'

const BasketIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 9h18l-1.6 9.2a2 2 0 0 1-2 1.8H6.6a2 2 0 0 1-2-1.8L3 9z" />
    <path d="M8 9l3-6M16 9l-3-6M9 13v4M12 13v4M15 13v4" />
  </svg>
)

/* Where the subject sits on screen: the tile shows the frame with object-fit: cover. */
function subjectRect(tile, bbox) {
  const t = tile.getBoundingClientRect()
  const [bx, by, bw, bh] = bbox || [0.35, 0.2, 0.3, 0.6]
  const img = tile.querySelector('.cam-video')
  const nw = img?.naturalWidth || t.width
  const nh = img?.naturalHeight || t.height
  const scale = Math.max(t.width / nw, t.height / nh)
  const ox = t.left + (t.width - nw * scale) / 2
  const oy = t.top + (t.height - nh * scale) / 2
  const left = Math.max(t.left, ox + bx * nw * scale)
  const top = Math.max(t.top, oy + by * nh * scale)
  const right = Math.min(t.right, ox + (bx + bw) * nw * scale)
  const bottom = Math.min(t.bottom, oy + (by + bh) * nh * scale)
  return { left, top, width: Math.max(24, right - left), height: Math.max(24, bottom - top), tile: t }
}

function place(el, r) {
  Object.assign(el.style, { left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px` })
}

/* Lock on to the subject, flash, then fly the picture into the basket. Returns a cancel function. */
function playCapture(capture, target, onLand) {
  const tile = document.querySelector(`.cam-grid [data-cam-id="${CSS.escape(capture.camera_id || '')}"]`)
  const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (!tile || !target || still || document.hidden) {
    const t = setTimeout(onLand, 0)
    return () => clearTimeout(t)
  }
  const from = subjectRect(tile, capture.bbox)
  const to = target.getBoundingClientRect()
  const layer = document.createElement('div')
  layer.className = 'cap-fx'
  const reticle = document.createElement('div')
  reticle.className = 'cap-reticle'
  place(reticle, from)
  const flash = document.createElement('div')
  flash.className = 'cap-flash'
  place(flash, from.tile)
  const shot = document.createElement('img')
  shot.className = 'cap-shot'
  shot.alt = ''
  shot.src = captureImageUrl(capture.id, 240)
  place(shot, from)
  layer.append(flash, reticle, shot)
  document.body.appendChild(layer)

  reticle.animate(
    [{ transform: 'scale(1.5)', opacity: 0 }, { transform: 'none', opacity: 1, offset: 0.3 },
      { transform: 'none', opacity: 1, offset: 0.8 }, { transform: 'scale(0.96)', opacity: 0 }],
    { duration: 900, easing: 'ease-out', fill: 'both' },
  )
  flash.animate([{ opacity: 0 }, { opacity: 0.7, offset: 0.25 }, { opacity: 0 }],
    { duration: 320, delay: 300, fill: 'both' })
  const dx = to.left + to.width / 2 - (from.left + from.width / 2)
  const dy = to.top + to.height / 2 - (from.top + from.height / 2)
  const end = Math.max(0.08, Math.min(1, 34 / from.height))
  const fly = shot.animate(
    [{ transform: 'none', opacity: 0 },
      { transform: 'scale(1.06)', opacity: 1, offset: 0.12 },
      { transform: `translate(${dx * 0.55}px, ${dy * 0.5 - 46}px) scale(${(1 + end) / 2}) rotate(-5deg)`, opacity: 1, offset: 0.6 },
      { transform: `translate(${dx}px, ${dy}px) scale(${end}) rotate(4deg)`, opacity: 0.25 }],
    { duration: 1050, delay: 380, easing: 'cubic-bezier(0.5, 0, 0.3, 1)', fill: 'both' },
  )
  let done = false
  const finish = (landed) => {
    if (done) return
    done = true
    layer.remove()
    if (landed) onLand()
  }
  fly.onfinish = () => finish(true)
  fly.oncancel = () => finish(false)
  return () => finish(false)
}

const pct = (v) => (v == null ? null : `${Math.round((v <= 1 ? v * 100 : v))}%`)

function Swatch({ colour }) {
  if (!colour) return null
  return <span className="cap-swatch"><i style={{ background: colour.hex }} />{colour.name}</span>
}

function CaptureDetail({ c }) {
  const { push: toast } = useToast()
  const a = c.attributes || {}
  const when = parseTs(c.timestamp)
  const zoom = c.height && c.source_height ? c.height / c.source_height : null
  const hasGps = c.camera_lat != null && c.camera_lng != null

  const download = async () => {
    try {
      const res = await fetch(captureImageUrl(c.id))
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const url = URL.createObjectURL(await res.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = `aegis-capture-${c.id}.jpg`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      toast(`Could not download the picture: ${e.message || 'request failed'}`, 'danger')
    }
  }

  return (
    <>
      <div className="cap-photo">
        <img key={c.id} src={captureImageUrl(c.id)} alt={`Capture ${c.id}, ${eventLabel(c.alert_type)}`} />
      </div>
      <div className="cap-detail-head">
        <div>
          <b>{eventLabel(c.alert_type)}</b>
          <div className="meta">{when ? when.toLocaleString() : '—'} · {timeAgo(c.timestamp)}</div>
        </div>
        <button type="button" className="btn btn-sm" onClick={download}><Icons.download /> Download</button>
      </div>
      <dl className="kv cap-kv">
        <dt>Alert</dt><dd>{eventLabel(c.alert_type)}{c.alert_id != null && ` · #${c.alert_id}`}</dd>
        {(c.alert_type === 'CRIMINAL_DETECTED' || (c.alert_type === 'PERSON_TRACKED' && c.person_name)) && (
          <>
            <dt>Subject</dt>
            <dd>
              {c.subject?.name || c.person_name || 'Unknown'}
              {c.subject?.criminal_status && <> <Tag tone="danger">{c.subject.criminal_status}</Tag></>}
              {c.subject?.threat_level && <> <Tag tone="warn">{c.subject.threat_level} threat</Tag></>}
            </dd>
          </>
        )}
        {c.confidence != null && <><dt>Confidence</dt><dd>{pct(c.confidence)}</dd></>}
        <dt>Camera</dt><dd>{c.camera_name || c.camera_id || '—'}</dd>
        {c.camera_location && <><dt>Location</dt><dd>{c.camera_location}</dd></>}
        {hasGps && (
          <>
            <dt>GPS</dt>
            <dd>
              {c.camera_lat.toFixed(5)}, {c.camera_lng.toFixed(5)}{' '}
              <a href={c.maps_url} target="_blank" rel="noreferrer">Open map</a>
            </dd>
          </>
        )}
        {c.track_id != null && <><dt>Track</dt><dd>#{c.track_id}</dd></>}
        {a.gender && (
          <>
            <dt>Gender (estimate)</dt>
            <dd>{a.gender === 'undetermined' ? 'Not clear enough to say' : `${a.gender} · ${pct(a.gender_confidence)}`}</dd>
          </>
        )}
        {a.age_estimate != null && <><dt>Age (rough estimate)</dt><dd>around {a.age_estimate}</dd></>}
        {a.face_visible === false && <><dt>Face</dt><dd>Not visible in this picture</dd></>}
        {(a.upper_colour || a.lower_colour) && (
          <>
            <dt>Clothing</dt>
            <dd className="cap-clothes">
              {a.upper_colour && <span>Top <Swatch colour={a.upper_colour} /></span>}
              {a.lower_colour && <span>Bottom <Swatch colour={a.lower_colour} /></span>}
            </dd>
          </>
        )}
        <dt>Picture</dt>
        <dd>
          {c.width}×{c.height} px
          {zoom > 1.05 && ` · enlarged ${zoom.toFixed(1)}×`}
          {c.source_width && ` · subject was ${c.source_width}×${c.source_height} px in the frame`}
        </dd>
        {c.content_sha256 && <><dt>SHA-256</dt><dd className="cap-hash" title={c.content_sha256}>{c.content_sha256}</dd></>}
      </dl>
      {(a.gender || a.upper_colour || a.lower_colour) && (
        <p className="cap-note">
          Gender, age and clothing colour are automatic estimates to help describe the subject. They can be wrong and are not an identification.
        </p>
      )}
    </>
  )
}

function BasketModal({ items, selectedId, onSelect, onClose }) {
  const groups = useMemo(() => {
    const byAlert = new Map()
    items.forEach((c) => {
      const key = c.alert_id ?? `none-${c.id}`
      if (!byAlert.has(key)) byAlert.set(key, [])
      byAlert.get(key).push(c)
    })
    return [...byAlert.entries()]
  }, [items])
  const selected = items.find((c) => c.id === selectedId) || items[0]

  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
      const i = items.findIndex((c) => c.id === selected?.id)
      const next = items[i + (e.key === 'ArrowRight' ? 1 : -1)]
      if (next) { e.preventDefault(); onSelect(next.id) }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [items, selected, onSelect])

  return (
    <Modal className="modal-wide" title={`Capture basket · ${items.length} ${items.length === 1 ? 'picture' : 'pictures'}`} onClose={onClose}>
      {items.length === 0 ? (
        <p className="muted">No pictures yet. During a red alert the system takes a zoomed picture of the subject every few seconds and drops it here.</p>
      ) : (
        <div className="cap-modal">
          <div className="cap-list">
            {groups.map(([key, list]) => (
              <section key={key}>
                <header>
                  <b>{eventLabel(list[0].alert_type)}</b>
                  <span>{list[0].alert_id != null ? `#${list[0].alert_id} · ` : ''}{list.length} · {timeAgo(list[0].timestamp)}</span>
                </header>
                <div className="cap-thumbs">
                  {list.map((c) => (
                    <button type="button" key={c.id} className={`cap-thumb ${c.id === selected?.id ? 'active' : ''}`}
                      onClick={() => onSelect(c.id)} aria-label={`Picture taken ${timeAgo(c.timestamp)}`} aria-pressed={c.id === selected?.id}>
                      <img src={captureImageUrl(c.id, 240)} alt="" loading="lazy" />
                      <span>{parseTs(c.timestamp)?.toLocaleTimeString() || ''}</span>
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
          <div className="cap-detail">{selected && <CaptureDetail c={selected} />}</div>
        </div>
      )}
    </Modal>
  )
}

/** Live-page card: red-alert pictures fly from the camera tile into the basket as they are taken. */
export function CaptureBasket({ captureEvent }) {
  const [items, setItems] = useState([])
  const [live, setLive] = useState(null)            // { id, gap, label } while pictures keep arriving
  const [openId, setOpenId] = useState(undefined)   // undefined = closed, null = open on the newest
  const dropRef = useRef(null)
  const handled = useRef(captureEvent?.id ?? null)
  const lastArrival = useRef(0)
  const liveTimer = useRef(null)
  const running = useRef(new Set())
  const [scope, setScope] = useState('red')         // 'red' = red alerts only, 'suspicious' = suspicious people too
  const { push: toast } = useToast()

  const loadCaptures = useCallback(() => {
    fetchCaptures(120).then((rows) => {
      setItems((prev) => {
        const have = new Set(prev.map((c) => c.id))
        return [...prev, ...rows.filter((c) => !have.has(c.id))].sort((x, y) => y.id - x.id).slice(0, KEEP)
      })
    }).catch(() => {})
  }, [])

  useEffect(() => {
    loadCaptures()
    fetchCaptureScope().then((r) => setScope(r.scope)).catch(() => {})
  }, [loadCaptures])

  const changeScope = useCallback((next) => {
    const prev = scope
    setScope(next)
    setCaptureScope(next).then(() => {
      if (next === 'suspicious') loadCaptures()
      else setItems((list) => list.filter((c) => c.alert_type !== SUSPICIOUS))
    }).catch((e) => {
      setScope(prev)
      toast(`Could not change what the basket keeps: ${e.message || 'request failed'}`, 'danger')
    })
  }, [scope, loadCaptures, toast])

  useEffect(() => {
    const active = running.current
    return () => {
      clearTimeout(liveTimer.current)
      active.forEach((cancel) => cancel())
    }
  }, [])

  const land = useCallback((capture, gap) => {
    setItems((prev) => (prev.some((c) => c.id === capture.id) ? prev : [capture, ...prev].slice(0, KEEP)))
    setLive({ id: capture.id, gap, label: eventLabel(capture.alert_type) })
    clearTimeout(liveTimer.current)
    liveTimer.current = setTimeout(() => setLive(null), (gap + 4) * 1000)
    dropRef.current?.animate(
      [{ transform: 'none' }, { transform: 'scale(1.16) rotate(-4deg)' }, { transform: 'none' }],
      { duration: 380, easing: 'cubic-bezier(0.34, 1.36, 0.64, 1)' },
    )
  }, [])

  useEffect(() => {
    if (!captureEvent || captureEvent.id === handled.current) return
    handled.current = captureEvent.id
    if (captureEvent.alert_type === SUSPICIOUS && scope !== 'suspicious') return
    const now = performance.now()
    const since = (now - lastArrival.current) / 1000
    lastArrival.current = now
    const gap = since >= 2 && since <= 30 ? Math.round(since) : DEFAULT_GAP
    const entry = { cancel: () => {} }
    const cancel = () => entry.cancel()
    running.current.add(cancel)
    entry.cancel = playCapture(captureEvent, dropRef.current, () => {
      running.current.delete(cancel)
      land(captureEvent, gap)
    })
  }, [captureEvent, land, scope])

  const newest = items[0]
  const status = live
    ? `${live.label} · a picture every ${live.gap} s`
    : newest ? `Last picture ${timeAgo(newest.timestamp)}`
      : scope === 'suspicious' ? 'Fills by itself during a red alert or for a suspicious person'
        : 'Fills by itself during a red alert'

  return (
    <>
      <Card title="Capture basket" actions={live ? <Tag tone="danger">CAPTURING</Tag> : undefined}>
        <div className="basket-scope" title="Which people get pictures in the basket">
          <Seg value={scope} onChange={changeScope} options={[
            { value: 'red', label: 'Criminals only' },
            { value: 'suspicious', label: '+ Suspicious' },
          ]} />
        </div>
        <button type="button" className={`basket ${live ? 'live' : ''}`} onClick={() => setOpenId(null)}
          aria-label={`Open capture basket, ${items.length} pictures`}>
          <span className="basket-icon" ref={dropRef}>
            <BasketIcon />
            {live && (
              <svg key={live.id} className="basket-ring" viewBox="0 0 60 60" style={{ animationDuration: `${live.gap}s` }} aria-hidden="true">
                <circle cx="30" cy="30" r="27" pathLength="100" />
              </svg>
            )}
            {items.length > 0 && <span className="basket-count">{items.length}</span>}
          </span>
          <span className="basket-text">
            <b>{items.length} {items.length === 1 ? 'picture' : 'pictures'}</b>
            <span aria-live="polite">{status}</span>
          </span>
        </button>
        {items.length > 0 && (
          <div className="basket-strip">
            {items.slice(0, 4).map((c) => (
              <button type="button" key={c.id} className="cap-thumb" onClick={() => setOpenId(c.id)}
                aria-label={`Open picture taken ${timeAgo(c.timestamp)}`}>
                <img src={captureImageUrl(c.id, 240)} alt="" loading="lazy" />
              </button>
            ))}
          </div>
        )}
      </Card>
      {openId !== undefined && (
        <BasketModal items={items} selectedId={openId} onSelect={setOpenId} onClose={() => setOpenId(undefined)} />
      )}
    </>
  )
}
