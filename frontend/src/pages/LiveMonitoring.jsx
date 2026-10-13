import { can } from '../lib/permissions'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Card, Icons, Seg, Pill, Stat, Tag, Empty, timeAgo } from '../components/ui'
import {
  liveStreamUrl,
  fetchVmsTimeline, fetchPtz, ptzMove, ptzStop, ptzHome, ptzSetMode,
  ptzSavePreset, ptzGotoPreset, openVmsPlayback,
} from '../services/api'

const STATUS = {
  live: { label: 'LIVE', tone: 'ok' },
  online: { label: 'NO VIDEO', tone: 'warn' },
  offline: { label: 'OFFLINE', tone: 'muted' },
}

const ExpandIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7" />
  </svg>
)
const Chevron = ({ dir }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"
    style={{ transform: `rotate(${{ up: 0, right: 90, down: 180, left: 270 }[dir]}deg)` }}>
    <path d="M6 15l6-6 6 6" />
  </svg>
)

const HomeIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 11l9-8 9 8M5 10v10h14V10" />
  </svg>
)

function CamFeed({ cam, objectFit = 'cover' }) {
  const [failed, setFailed] = useState(false)
  const showVideo = cam.status === 'live' && !failed
  const st = STATUS[showVideo ? 'live' : (cam.status === 'live' ? 'online' : cam.status)]

  return (
    <>
      {showVideo && (
        <img className="cam-video" src={liveStreamUrl(cam.camera_id)} alt={cam.name}
          style={{ objectFit }} onError={() => { setFailed(true); setTimeout(() => setFailed(false), 5000) }} />
      )}
      {!showVideo && (
        <div className="cam-offline">
          <Icons.camera />
          <b>{st.label === 'NO VIDEO' ? 'Connected, waiting for video' : 'No signal'}</b>
        </div>
      )}
      <div className="cam-top">
        <span className={`cam-badge ${st.tone}`}>
          <span className="dot" />{st.label}
        </span>
        {showVideo && cam.dvr && <span className="cam-badge rec"><span className="dot" />REC</span>}
        <span className="spacer" />
        {showVideo && cam.fps != null && <span className="cam-chip">{cam.fps} FPS</span>}
        {cam.threat_score > 0 && <span className={`cam-chip ${cam.threat_score >= 40 ? 'danger' : 'warn'}`}>THREAT {cam.threat_score}</span>}
      </div>
      <div className="cam-bottom">
        <div className="cam-name">{cam.name}</div>
        {cam.location && cam.location !== cam.name && <div className="cam-loc">{cam.location}</div>}
      </div>
    </>
  )
}

function CamTile({ cam, selected, alerting, onSelect, onExpand }) {
  if (!cam) {
    return <div className="cam-tile empty"><span>Empty slot</span></div>
  }
  return (
    <div
      className={`cam-tile ${cam.status} ${alerting ? 'alerting' : ''} ${selected ? 'selected' : ''}`}
      onClick={onSelect}
      onDoubleClick={onExpand}
      role="button"
      tabIndex={0}
      aria-label={`${cam.name}, ${STATUS[cam.status].label}`}
      onKeyDown={(e) => { if (e.key === 'Enter') onSelect(); if (e.key === 'f') onExpand() }}
    >
      <CamFeed cam={cam} />
      <button type="button" className="cam-expand" title="Full screen (double-click)" aria-label="Full screen"
        onClick={(e) => { e.stopPropagation(); onExpand() }}>
        <ExpandIcon />
      </button>
    </div>
  )
}

function CamFullscreen({ cam, alerting, onClose }) {
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = prev
      window.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  return (
    <div className="cam-fullscreen-overlay" role="dialog" aria-modal="true" aria-label={`Live feed — ${cam.name}`}>
      <div className="cam-fullscreen-bar">
        <div className="cam-fullscreen-title">
          {cam.name}
          {alerting && <Tag tone="danger">THREAT</Tag>}
        </div>
        <button type="button" className="icon-btn cam-fullscreen-close" onClick={onClose} aria-label="Close full-screen view">
          <Icons.close />
        </button>
      </div>
      <div className={`cam-tile cam-fullscreen-tile ${cam.status} ${alerting ? 'alerting' : ''}`}>
        <CamFeed cam={cam} objectFit="contain" />
      </div>
    </div>
  )
}

function PtzPad({ cameraId }) {
  const [state, setState] = useState(null)
  const [presetName, setPresetName] = useState('Gate')

  useEffect(() => {
    if (!cameraId) return
    fetchPtz(cameraId).then(setState).catch(() => {})
  }, [cameraId])

  const move = async (pan, tilt, zoom = 0) => {
    try {
      setState(await ptzMove(cameraId, { pan, tilt, zoom }))
    } catch { /* offline */ }
  }
  const stop = async () => { try { setState(await ptzStop(cameraId)) } catch { /* */ } }

  if (!cameraId) return <Empty icon={Icons.camera}>Select a camera tile</Empty>

  const mode = state?.mode || 'digital'
  const dig = state?.digital || { pan: 0, tilt: 0, zoom: 1 }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <Seg
          value={mode}
          onChange={async (m) => setState(await ptzSetMode(cameraId, m))}
          options={[{ value: 'digital', label: 'Digital PTZ' }, { value: 'onvif', label: 'ONVIF' }]}
        />
        <Tag tone={state?.onvif?.configured ? 'ok' : 'muted'}>
          {state?.onvif?.configured ? `ONVIF ${state.onvif.host}` : 'ONVIF simulator'}
        </Tag>
      </div>

      <div className="ptz-pad">
        <button className="ptz-btn" onMouseDown={() => move(0, 1)} onMouseUp={stop} onMouseLeave={stop} aria-label="Tilt up"><Chevron dir="up" /></button>
        <div className="ptz-mid">
          <button className="ptz-btn" onMouseDown={() => move(-1, 0)} onMouseUp={stop} onMouseLeave={stop} aria-label="Pan left"><Chevron dir="left" /></button>
          <button className="ptz-btn ptz-home" onClick={async () => setState(await ptzHome(cameraId))} aria-label="Home" title="Home"><HomeIcon /></button>
          <button className="ptz-btn" onMouseDown={() => move(1, 0)} onMouseUp={stop} onMouseLeave={stop} aria-label="Pan right"><Chevron dir="right" /></button>
        </div>
        <button className="ptz-btn" onMouseDown={() => move(0, -1)} onMouseUp={stop} onMouseLeave={stop} aria-label="Tilt down"><Chevron dir="down" /></button>
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center' }}>
        <span className="muted" style={{ fontSize: '0.75rem' }}>Zoom</span>
        <button className="btn btn-sm" onMouseDown={() => move(0, 0, -0.5)} onMouseUp={stop}>−</button>
        <input
          type="range" min="1" max="8" step="0.1" value={dig.zoom}
          readOnly
          style={{ flex: 1 }}
        />
        <button className="btn btn-sm" onMouseDown={() => move(0, 0, 0.5)} onMouseUp={stop}>+</button>
        <b style={{ fontSize: '0.8rem', width: 36 }}>{Number(dig.zoom).toFixed(1)}×</b>
      </div>

      <div style={{ display: 'flex', gap: 6, marginTop: 12, flexWrap: 'wrap' }}>
        <input className="input" style={{ width: 100, padding: '4px 8px' }} value={presetName} onChange={(e) => setPresetName(e.target.value)} />
        <button className="btn btn-sm" onClick={async () => setState(await ptzSavePreset(cameraId, presetName || 'Preset'))}>Save preset</button>
        {(state?.presets || []).map((p) => (
          <button key={p} className="btn btn-sm btn-primary" onClick={async () => setState(await ptzGotoPreset(cameraId, p))}>{p}</button>
        ))}
      </div>
      {state?.last_error && <p className="muted" style={{ fontSize: '0.72rem', marginTop: 8, color: 'var(--warn)' }}>ONVIF: {state.last_error} (simulator active)</p>}
      <p className="muted" style={{ fontSize: '0.72rem', marginTop: 8 }}>
        Digital PTZ crops the live stream; ONVIF drives a physical camera.
      </p>
    </div>
  )
}

export function LiveMonitoring({ ctx }) {
  const { systemStatus, cameras, threatLevel, streamingCams = [], me } = ctx
  const [layout, setLayout] = useState('auto')
  const [selectedId, setSelectedId] = useState(null)
  const [fullscreenId, setFullscreenId] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [coverageHrs, setCoverageHrs] = useState(0)
  const [scrub, setScrub] = useState(100)
  const [replayUrl, setReplayUrl] = useState(null)
  const [replayBusy, setReplayBusy] = useState(false)
  const [replayError, setReplayError] = useState('')

  // One list: registered cameras, overlaid with live heartbeat + stream state.
  const camList = useMemo(() => {
    const streaming = new Set(streamingCams)
    const beats = systemStatus?.cameras || {}
    const byId = new Map()
    // cam_0 / video_0 are placeholder identities for single-camera runs: only show them when active.
    const placeholder = (id) => id === 'cam_0' || id === 'video_0'
    cameras.forEach((c) => {
      const reporting = streaming.has(c.camera_id) || beats[c.camera_id]
      if (reporting || (c.active && !placeholder(c.camera_id))) {
        byId.set(c.camera_id, { camera_id: c.camera_id, name: c.name || c.location || c.camera_id, location: c.location })
      }
    })
    Object.keys(beats).forEach((id) => {
      if (!byId.has(id)) byId.set(id, { camera_id: id, name: beats[id].camera_location || id, location: beats[id].camera_location })
    })
    return [...byId.values()].map((c) => {
      const beat = beats[c.camera_id]
      return {
        ...c,
        status: streaming.has(c.camera_id) ? 'live' : beat ? 'online' : 'offline',
        fps: beat?.fps ?? null,
        threat_score: beat?.threat_score ?? 0,
        dvr: Boolean(beat?.recording),   // only claim REC when the pipeline reports it
      }
    }).sort((x, y) => (y.status === 'live') - (x.status === 'live') || x.name.localeCompare(y.name))
  }, [cameras, systemStatus, streamingCams])

  const counts = {
    live: camList.filter((c) => c.status === 'live').length,
    online: camList.filter((c) => c.status !== 'offline').length,
  }

  const slots = layout === 'auto' ? camList.length : Number(layout)
  const cols = layout === 'auto'
    ? (slots <= 1 ? 1 : slots <= 4 ? 2 : slots <= 9 ? 3 : 4)
    : ({ 1: 1, 4: 2, 9: 3, 16: 4 }[slots])
  const tiles = Array.from({ length: Math.max(slots, 0) }, (_, i) => camList[i] || null)

  const activeCam = camList.find((c) => c.camera_id === selectedId)?.camera_id || camList[0]?.camera_id
  const activeInfo = camList.find((c) => c.camera_id === activeCam)
  const alertingId = threatLevel === 'critical' ? camList.find((c) => c.threat_score >= 40)?.camera_id : null
  const fullscreenCam = camList.find((c) => c.camera_id === fullscreenId)

  const loadTimeline = useCallback(() => {
    if (!activeCam) return
    fetchVmsTimeline({ cameraId: activeCam, hours: 24 }).then((r) => {
      setTimeline(r.segments || [])
      setCoverageHrs(r.continuous_coverage_hours || 0)
    }).catch(() => {})
  }, [activeCam])
  useEffect(() => { loadTimeline() }, [loadTimeline, streamingCams.length])

  const scrubToReplay = async () => {
    if (!activeCam || !timeline.length) return
    setReplayBusy(true)
    setReplayError('')
    try {
      const idx = Math.min(timeline.length - 1, Math.floor((scrub / 100) * timeline.length))
      const t = timeline[idx]?.start || new Date().toISOString()
      const { blobUrl } = await openVmsPlayback(activeCam, t)
      if (replayUrl) URL.revokeObjectURL(replayUrl)
      setReplayUrl(blobUrl)
    } catch (e) {
      setReplayError(e.message || 'No recording at this time')
    } finally {
      setReplayBusy(false)
    }
  }

  const pipelineLabel = systemStatus?.online ? 'Pipeline online' : 'Pipeline offline'

  return (
    <>
      <div className="grid grid-4 live-stats">
        <Stat label="Live streams" value={`${counts.live}/${camList.length}`} accent={counts.live ? 'ok' : 'warn'}
          delta={counts.live ? 'receiving video' : 'no video received'} />
        <Stat label="Cameras reporting" value={counts.online} accent="primary" delta="heartbeat or video" />
        <Stat label="Threat level" value={(threatLevel || 'low').toUpperCase()}
          accent={threatLevel === 'critical' ? 'danger' : threatLevel === 'high' ? 'warn' : 'ok'} delta="last 15 minutes" />
        <Stat label="DVR coverage" value={`${coverageHrs.toFixed(1)} h`} accent="primary" delta="selected camera · 24 h" />
      </div>

      <div className="live-layout">
        <div className="live-main">
        <Card
          title="Live view"
          sub={activeInfo ? `selected: ${activeInfo.name}` : undefined}
          actions={
            <div className="cam-controls">
              <Seg value={layout} onChange={setLayout}
                options={[{ value: 'auto', label: 'Auto' }, { value: 1, label: '1' }, { value: 4, label: '2×2' }, { value: 9, label: '3×3' }]} />
              <Pill tone={systemStatus?.online ? 'ok' : 'warn'}>{pipelineLabel}</Pill>
            </div>
          }
        >
          {camList.length === 0 ? (
            <Empty icon={Icons.camera}>No cameras configured. Add one under Camera Management.</Empty>
          ) : (
            <div className="cam-grid" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
              {tiles.map((cam, i) => (
                <CamTile
                  key={cam?.camera_id || `empty-${i}`}
                  cam={cam}
                  selected={cam && cam.camera_id === activeCam && tiles.length > 1}
                  alerting={cam && cam.camera_id === alertingId}
                  onSelect={() => cam && setSelectedId(cam.camera_id)}
                  onExpand={() => cam && setFullscreenId(cam.camera_id)}
                />
              ))}
            </div>
          )}
          {!systemStatus?.online && camList.length > 0 && (
            <p className="live-hint">The analysis pipeline is not reporting. Cameras stay offline until it is running.</p>
          )}
        </Card>

      <Card title="Recordings" sub={`${timeline.length} segments · 24 h · ${activeInfo?.name || '—'}`}
        actions={<button className="btn btn-sm" onClick={loadTimeline}>Refresh</button>}>
        {timeline.length === 0 ? (
          <Empty icon={Icons.clock}>No recordings for this camera yet. Segments are saved every 60 seconds while video is flowing.</Empty>
        ) : (
          <>
            <div className="vms-rail">
              {timeline.map((s) => (
                <div key={s.id} className={`vms-seg ${s.trigger === 'event' ? 'event' : 'cont'}`}
                  title={`${s.trigger} · ${s.start}`} style={{ flex: Math.max(0.5, s.duration || 1) }} />
              ))}
            </div>
            <div className="vms-legend">
              <span><i className="cont" />Continuous</span><span><i className="event" />Alert event</span>
            </div>
            <div className="vms-controls">
              <input type="range" min="0" max="100" value={scrub} aria-label="Scrub position"
                onChange={(e) => setScrub(Number(e.target.value))} />
              <button className="btn btn-primary" disabled={replayBusy} onClick={scrubToReplay}>
                <Icons.eye /> {replayBusy ? 'Loading…' : 'Play'}
              </button>
            </div>
            {replayError && <div className="login-error" role="alert" style={{ marginTop: 10 }}>{replayError}</div>}
            {replayUrl && <video src={replayUrl} controls autoPlay className="vms-player" />}
            <div className="vms-list">
              {timeline.slice().reverse().slice(0, 6).map((s) => (
                <div key={s.id} className="row">
                  <div>
                    <b>{s.alert_type || (s.trigger === 'event' ? 'Event' : 'Continuous recording')}</b>
                    <div className="meta">{timeAgo(s.start)} · {Math.round(s.duration || 0)}s</div>
                  </div>
                  <Tag tone={s.trigger === 'event' ? 'danger' : 'ok'}>{s.trigger}</Tag>
                </div>
              ))}
            </div>
          </>
        )}
      </Card>
        </div>

        <div className="live-rail">
          <Card title="Cameras" sub={`${camList.length}`} flush>
            <div className="cam-list">
              {camList.map((c) => (
                <button key={c.camera_id} type="button"
                  className={`cam-row ${c.camera_id === activeCam ? 'active' : ''}`}
                  onClick={() => setSelectedId(c.camera_id)}>
                  <span className={`status-dot ${STATUS[c.status].tone}`} />
                  <span className="cam-row-main">
                    <b>{c.name}</b>
                    <span>{c.location || c.camera_id}</span>
                  </span>
                  <Tag tone={STATUS[c.status].tone}>{STATUS[c.status].label}</Tag>
                </button>
              ))}
              {camList.length === 0 && <div className="live-hint" style={{ padding: 14 }}>None</div>}
            </div>
          </Card>
          {can(me?.role, 'ptz') && (
            <Card title="PTZ control" sub={activeInfo?.name || '—'}>
              <PtzPad cameraId={activeCam} />
            </Card>
          )}
        </div>
      </div>

      {fullscreenCam && (
        <CamFullscreen cam={fullscreenCam} alerting={fullscreenCam.camera_id === alertingId}
          onClose={() => setFullscreenId(null)} />
      )}
    </>
  )
}
