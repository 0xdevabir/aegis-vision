import { useCallback, useEffect, useMemo, useState } from 'react'
import { Card, Empty, Icons, Seg, Tag, timeAgo, SEVERITY_TONE, useConfirm } from '../components/ui'
import { OpsMap } from '../components/OpsMap'
import { groupEvents, spreadCameras } from '../lib/mapGeo'
import { eventGroup, eventLabel, GROUPS } from '../lib/events'
import { parseTs } from '../lib/time'
import { can } from '../lib/permissions'
import { useToast } from '../components/Toast'
import { fetchMapCameras, fetchMapEvents, fetchCameraOfficerMap, updateCamera } from '../services/api'

const RANGES = [
  { value: 1, label: '1h' },
  { value: 24, label: '24h' },
  { value: 168, label: '7d' },
]
const MAP_GROUPS = GROUPS.filter((g) => g.id !== 'all')

export function MapPage({ ctx }) {
  const { systemStatus, events: liveEvents, me, setPage, mapFocus } = ctx
  const { push: toast } = useToast()
  const [ask, confirmDialog] = useConfirm()
  const isAdmin = can(me?.role, 'camera.manage')

  const [cameras, setCameras] = useState([])
  const [events, setEvents] = useState([])
  const [officers, setOfficers] = useState({})
  const [loadError, setLoadError] = useState('')
  const [hours, setHours] = useState(24)
  const [groupsOn, setGroupsOn] = useState(() => new Set(MAP_GROUPS.map((g) => g.id).concat('other')))
  const [layers, setLayers] = useState({ alerts: true, heat: false, coverage: true })
  const [replay, setReplay] = useState(false)
  const [replayPct, setReplayPct] = useState(100)
  const [selectedCam, setSelectedCam] = useState(mapFocus?.cameraId || null)
  const [selectedGroup, setSelectedGroup] = useState(null)
  const [editId, setEditId] = useState(null)       // camera whose marker can be dragged
  const [placingId, setPlacingId] = useState(null) // camera waiting for a map click
  const [localFocus, setLocalFocus] = useState(null)
  const [seenFocus, setSeenFocus] = useState(mapFocus || null)
  const [loadedAt, setLoadedAt] = useState(() => Date.now())
  const [fitKick, setFitKick] = useState(0)
  const [search, setSearch] = useState('')
  const [covDraft, setCovDraft] = useState(null)   // {id, heading, fov, range_m} while editing

  const load = useCallback(() => {
    Promise.all([fetchMapCameras(), fetchMapEvents(hours), fetchCameraOfficerMap()])
      .then(([c, e, o]) => { setCameras(c); setEvents(e); setOfficers(o); setLoadError(''); setLoadedAt(Date.now()) })
      .catch((e) => setLoadError(e.message || 'Could not load map data'))
  }, [hours])

  useEffect(() => {
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [load])
  // a new live alert arrived: refresh right away
  useEffect(() => { if (liveEvents?.length) load() }, [liveEvents?.length, load])
  // "View on map" / a critical alert while this page is open: adopt the new focus request during render
  if (mapFocus !== seenFocus) {
    setSeenFocus(mapFocus)
    if (mapFocus?.cameraId) { setSelectedCam(mapFocus.cameraId); setSelectedGroup(null) }
  }
  const focus = mapFocus && (!localFocus || (mapFocus.t || 0) >= (localFocus.t || 0)) ? mapFocus : localFocus
  const fitKey = fitKick * 1000 + cameras.length

  const liveIds = useMemo(() => new Set(Object.keys(systemStatus?.cameras || {})), [systemStatus])
  const statusOf = useCallback((c) => (liveIds.has(c.camera_id) ? 'live' : c.active ? 'idle' : 'off'), [liveIds])

  const located = useMemo(() => spreadCameras(cameras.filter((c) => c.lat != null && c.lng != null)), [cameras])
  const noGps = cameras.filter((c) => c.lat == null || c.lng == null)

  const visible = useMemo(() => {
    let list = events.filter((e) => groupsOn.has(eventGroup(e.event_type)))
    if (replay) {
      const cutoff = loadedAt - hours * 3600e3 + (replayPct / 100) * hours * 3600e3
      list = list.filter((e) => (parseTs(e.timestamp)?.getTime() ?? 0) <= cutoff)
    }
    return list
  }, [events, groupsOn, replay, replayPct, hours, loadedAt])
  const groups = useMemo(() => groupEvents(visible, located), [visible, located])
  const unlocated = visible.length - groups.reduce((n, g) => n + g.events.length, 0)

  const cam = cameras.find((c) => c.camera_id === selectedCam) || null
  const camGroup = groups.find((g) => g.cameraId === selectedCam)
  const group = groups.find((g) => g.key === selectedGroup) || null

  const cov = covDraft && covDraft.id === cam?.camera_id
    ? covDraft
    : { id: cam?.camera_id, heading: cam?.heading ?? '', fov: cam?.fov ?? '', range_m: cam?.range_m ?? '' }
  const setCov = (next) => setCovDraft({ ...next, id: cam.camera_id })

  const focusOn = (lat, lng) => setLocalFocus({ lat, lng, t: Date.now() })
  const pickCamera = (id) => {
    setSelectedCam(id); setSelectedGroup(null)
    const c = located.find((x) => x.camera_id === id)
    if (c) focusOn(c.plat, c.plng)
  }
  const pickGroup = (key) => {
    setSelectedGroup(key); setSelectedCam(null)
    const g = groups.find((x) => x.key === key)
    if (g) focusOn(g.lat, g.lng)
  }

  const savePosition = async (c, lat, lng) => {
    try {
      await updateCamera(c.camera_id, { camera_id: c.camera_id, name: c.name, lat, lng })
      toast(`Location saved for ${c.name || c.camera_id}`, 'ok')
      setPlacingId(null); setEditId(null)
      load(); ctx.reloadCameras?.()
    } catch (e) {
      toast(e.message || 'Could not save location', 'danger')
    }
  }
  const onPlace = (lat, lng) => {
    if (!placingId) return
    const c = cameras.find((x) => x.camera_id === placingId)
    if (c) savePosition(c, Number(lat.toFixed(6)), Number(lng.toFixed(6)))
  }
  const onMove = async (id, lat, lng) => {
    const c = cameras.find((x) => x.camera_id === id)
    if (!c) return
    const ok = await ask({ title: 'Move camera', message: `Save the new location for ${c.name || id}? (${lat.toFixed(5)}, ${lng.toFixed(5)})`, confirmLabel: 'Save location' })
    if (ok) savePosition(c, Number(lat.toFixed(6)), Number(lng.toFixed(6)))
    else load()
  }
  const saveCoverage = async () => {
    const num = (v) => (v === '' || v == null ? null : Number(v))
    try {
      await updateCamera(cam.camera_id, { camera_id: cam.camera_id, name: cam.name, heading: num(cov.heading), fov: num(cov.fov), range_m: num(cov.range_m) })
      toast('Coverage saved', 'ok')
      load()
    } catch (e) {
      toast(e.message || 'Could not save coverage', 'danger')
    }
  }

  const toggleGroup = (id) => setGroupsOn((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n })
  const toggleLayer = (k) => setLayers((l) => ({ ...l, [k]: !l[k] }))
  const filteredCams = cameras.filter((c) => `${c.name} ${c.camera_id} ${c.location || ''}`.toLowerCase().includes(search.toLowerCase()))
  const counts = {
    live: cameras.filter((c) => statusOf(c) === 'live').length,
    off: cameras.filter((c) => statusOf(c) === 'off').length,
  }
  const officerLine = (id) => (officers[id] || []).map((o) => o.name).join(', ') || 'none assigned'

  return (
    <>
      {loadError && <div className="login-error" role="alert" style={{ marginBottom: 12 }}>{loadError} <button className="link-btn" onClick={load}>Retry</button></div>}
      <div className="ops-layout">
        <Card title="Operations map" sub={`${located.length} of ${cameras.length} cameras placed · ${counts.live} streaming · ${visible.length} alerts shown`}>
          <div className="ops-toolbar">
            <Seg options={RANGES} value={hours} onChange={setHours} />
            <div className="chip-row" role="group" aria-label="Alert types">
              {MAP_GROUPS.concat([{ id: 'other', label: 'Other' }]).map((g) => (
                <button key={g.id} type="button" className={`chip ${groupsOn.has(g.id) ? 'on' : ''}`} aria-pressed={groupsOn.has(g.id)} onClick={() => toggleGroup(g.id)}>{g.label}</button>
              ))}
            </div>
            <div className="chip-row" role="group" aria-label="Layers">
              <button type="button" className={`chip ${layers.alerts ? 'on' : ''}`} aria-pressed={layers.alerts} onClick={() => toggleLayer('alerts')}>Alerts</button>
              <button type="button" className={`chip ${layers.heat ? 'on' : ''}`} aria-pressed={layers.heat} onClick={() => toggleLayer('heat')}>Heat</button>
              <button type="button" className={`chip ${layers.coverage ? 'on' : ''}`} aria-pressed={layers.coverage} onClick={() => toggleLayer('coverage')}>Coverage</button>
              <button type="button" className={`chip ${replay ? 'on' : ''}`} aria-pressed={replay} onClick={() => { setReplay((r) => !r); setReplayPct(100) }}>Replay</button>
              <button type="button" className="chip" onClick={() => setFitKick((k) => k + 1)}>Fit all</button>
            </div>
          </div>
          {replay && (
            <label className="ops-replay">
              <span>Replay: alerts up to {replayPct}% of the last {hours === 168 ? '7 days' : `${hours}h`}</span>
              <input type="range" min={0} max={100} value={replayPct} onChange={(e) => setReplayPct(Number(e.target.value))} aria-label="Replay position" />
            </label>
          )}
          {placingId && <div className="ops-hint" role="status">Click the map to place <b>{cameras.find((c) => c.camera_id === placingId)?.name}</b>. <button className="link-btn" onClick={() => setPlacingId(null)}>Cancel</button></div>}
          {editId && <div className="ops-hint" role="status">Drag the highlighted camera marker to its real position. <button className="link-btn" onClick={() => setEditId(null)}>Done</button></div>}
          <OpsMap
            cameras={located} statusOf={statusOf} groups={groups} layers={layers}
            selectedId={selectedCam} focus={focus} editId={editId} placingId={placingId} fitKey={fitKey}
            onSelectCamera={pickCamera} onSelectGroup={pickGroup} onMoveCamera={onMove} onPlace={onPlace}
          />
          <div className="map-legend" style={{ marginTop: 10 }}>
            <span className="key"><span className="swatch" style={{ background: 'var(--ok)' }} /> Streaming</span>
            <span className="key"><span className="swatch" style={{ background: 'var(--warn)' }} /> Enabled, no signal</span>
            <span className="key"><span className="swatch" style={{ background: 'var(--text-3)' }} /> Off</span>
            <span className="key"><span className="swatch" style={{ background: 'var(--danger)' }} /> Alerts (number = count)</span>
          </div>
          {unlocated > 0 && <p className="muted" style={{ fontSize: 12 }}>{unlocated} alert(s) come from cameras without a location and are not drawn.</p>}
        </Card>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0 }}>
          {(cam || group) && (
            <Card title={cam ? (cam.name || cam.camera_id) : `${group.name || 'Location'} · ${group.events.length} alert(s)`} sub={cam ? `${cam.location || 'no location name'}` : 'alerts at this point'}>
              {cam && (
                <div style={{ display: 'grid', gap: 8 }}>
                  <div className="row"><span>Status</span><Tag tone={{ live: 'ok', idle: 'warn', off: 'danger' }[statusOf(cam)]}>{{ live: 'Streaming', idle: 'Enabled, no signal', off: 'Off' }[statusOf(cam)]}</Tag></div>
                  <div className="row"><span>GPS</span><span className="mono">{cam.lat != null ? `${cam.lat.toFixed(5)}, ${cam.lng.toFixed(5)}` : 'not set'}</span></div>
                  <div className="row"><span>Officer</span><span>{officerLine(cam.camera_id)}</span></div>
                  <div className="row"><span>Alerts in range</span><span>{camGroup ? camGroup.events.length : 0}</span></div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <button className="btn btn-sm btn-primary" onClick={() => setPage('live')}>View live</button>
                    {isAdmin && <button className="btn btn-sm" onClick={() => { setPlacingId(cam.camera_id); setEditId(null) }}>{cam.lat != null ? 'Move (click map)' : 'Set location'}</button>}
                    {isAdmin && cam.lat != null && <button className="btn btn-sm" onClick={() => { setEditId(cam.camera_id); setPlacingId(null) }}>Drag to adjust</button>}
                  </div>
                  {isAdmin && cam.lat != null && (
                    <fieldset className="ops-cov">
                      <legend>Coverage cone</legend>
                      <label>Heading°<input className="input" type="number" min={0} max={360} value={cov.heading} onChange={(e) => setCov({ ...cov, heading: e.target.value })} /></label>
                      <label>FOV°<input className="input" type="number" min={10} max={360} value={cov.fov} onChange={(e) => setCov({ ...cov, fov: e.target.value })} /></label>
                      <label>Range m<input className="input" type="number" min={5} max={500} value={cov.range_m} onChange={(e) => setCov({ ...cov, range_m: e.target.value })} /></label>
                      <button className="btn btn-sm" onClick={saveCoverage}>Save</button>
                    </fieldset>
                  )}
                </div>
              )}
              {group && group.events.slice(0, 10).map((ev) => (
                <div key={ev.alert_id} className="row">
                  <div>
                    <b>{eventLabel(ev.event_type)}</b>
                    <div className="meta">{ev.person_name ? `${ev.person_name} · ` : ''}{timeAgo(ev.timestamp)}{ev.acknowledged ? ' · acknowledged' : ''}</div>
                  </div>
                  <Tag tone={SEVERITY_TONE[ev.severity] || 'info'}>{ev.severity}</Tag>
                </div>
              ))}
              {group && <button className="btn btn-sm" style={{ marginTop: 8 }} onClick={() => setPage('alerts')}>Open in Alerts</button>}
            </Card>
          )}

          <Card title="Cameras" sub={`${counts.off} off · ${noGps.length} without location`}>
            <input className="input" placeholder="Search cameras" aria-label="Search cameras" value={search} onChange={(e) => setSearch(e.target.value)} style={{ marginBottom: 8 }} />
            {cameras.length === 0 && <Empty icon={Icons.camera}>No cameras registered</Empty>}
            <div className="ops-camlist">
              {filteredCams.map((c) => (
                <button key={c.camera_id} type="button" className={`row ops-camrow ${c.camera_id === selectedCam ? 'on' : ''}`} onClick={() => (c.lat != null ? pickCamera(c.camera_id) : setSelectedCam(c.camera_id))}>
                  <span style={{ textAlign: 'left' }}>
                    <b>{c.name || c.camera_id}</b>
                    <span className="meta" style={{ display: 'block' }}>{c.lat != null ? `${c.lat.toFixed(4)}, ${c.lng.toFixed(4)}` : 'No location set'} · {officerLine(c.camera_id)}</span>
                  </span>
                  <Tag tone={{ live: 'ok', idle: 'warn', off: 'danger' }[statusOf(c)]}>{{ live: 'Live', idle: 'No signal', off: 'Off' }[statusOf(c)]}</Tag>
                </button>
              ))}
            </div>
          </Card>

          <Card title="Latest alerts" sub={`last ${hours === 168 ? '7 days' : `${hours}h`}`}>
            {visible.length === 0 && <Empty icon={Icons.eye}>No alerts in this window</Empty>}
            {visible.slice(0, 8).map((ev) => (
              <button key={ev.alert_id} type="button" className="row ops-camrow" onClick={() => {
                const g = groups.find((x) => x.events.some((e) => e.alert_id === ev.alert_id))
                if (g) pickGroup(g.key)
              }}>
                <span style={{ textAlign: 'left' }}>
                  <b>{eventLabel(ev.event_type)}</b>
                  <span className="meta" style={{ display: 'block' }}>{ev.camera_name || ev.camera_id} · {timeAgo(ev.timestamp)}</span>
                </span>
                <Tag tone={SEVERITY_TONE[ev.severity] || 'info'}>{ev.severity}</Tag>
              </button>
            ))}
          </Card>
        </div>
      </div>
      {confirmDialog}
    </>
  )
}
