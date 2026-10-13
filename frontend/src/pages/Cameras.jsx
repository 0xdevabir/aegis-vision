import { useEffect, useState } from 'react'
import { Card, Icons, Tag, Empty, Seg, Modal, Stat, useConfirm } from '../components/ui'
import { resolveIp, addCamera, updateCamera, liveStreamUrl, deleteCamera, fetchUsers, fetchCameraOfficerMap, setCameraOfficers } from '../services/api'
import { useToast } from '../components/Toast'
import { can } from '../lib/permissions'

// Status comes only from what the system really knows: the pipeline heartbeat and the enabled flag.
function healthOf(cam, live) {
  if (live) return { label: 'Streaming', tone: 'ok' }
  if (cam.active) return { label: 'No signal', tone: 'warn' }
  return { label: 'Turned off', tone: 'danger' }
}

const slug = (s) => (s || '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40)
const EMPTY_FORM = { camera_id: '', name: '', location: '', lat: '', lng: '', rtsp_url: '' }

// '' → null (not set); anything else must be a number inside the range.
function parseCoord(value, limit) {
  if (String(value).trim() === '') return { value: null }
  const n = Number(value)
  return Number.isFinite(n) && Math.abs(n) <= limit ? { value: n } : { error: true }
}

const fmtGps = (cam) => (cam.lat != null && cam.lng != null ? `${Number(cam.lat).toFixed(4)}, ${Number(cam.lng).toFixed(4)}` : '—')

export function Cameras({ ctx }) {
  const { cameras, systemStatus, reloadCameras, me } = ctx
  const { push: toast } = useToast()
  const [ask, confirmDialog] = useConfirm()
  const [view, setView] = useState('grid')
  const isAdmin = me?.role === 'admin'
  const canManage = can(me?.role, 'camera.manage')

  const [showAdd, setShowAdd] = useState(false)
  const [addForm, setAddForm] = useState(EMPTY_FORM)
  const [addLoading, setAddLoading] = useState(false)
  const [addError, setAddError] = useState('')
  const setField = (key) => (e) => setAddForm((f) => ({ ...f, [key]: e.target.value }))
  const closeAdd = () => { setShowAdd(false); setAddForm(EMPTY_FORM); setAddError('') }

  const lookUpLocation = async () => {
    setAddLoading(true); setAddError('')
    try {
      const res = await resolveIp(addForm.rtsp_url)
      setAddForm((f) => ({
        ...f,
        location: f.location || res.location || '',
        lat: f.lat !== '' ? f.lat : (res.lat ?? ''),
        lng: f.lng !== '' ? f.lng : (res.lng ?? ''),
      }))
      if (res.error === 'private range') setAddError('This is a local network address, so its location cannot be looked up. Enter it by hand.')
      else if (res.error) setAddError(`Could not look up the location: ${res.error}`)
    } catch (e) {
      setAddError(`Could not look up the location: ${e.message}`)
    } finally {
      setAddLoading(false)
    }
  }

  const saveCamera = async () => {
    const lat = parseCoord(addForm.lat, 90)
    const lng = parseCoord(addForm.lng, 180)
    if (lat.error || lng.error) { setAddError('Latitude must be between -90 and 90, and longitude between -180 and 180.'); return }
    if ((lat.value == null) !== (lng.value == null)) { setAddError('Enter both latitude and longitude, or leave both empty.'); return }
    const cameraId = slug(addForm.camera_id || addForm.name)
    if (!cameraId) { setAddError('The camera ID needs at least one letter or number.'); return }
    setAddLoading(true); setAddError('')
    try {
      await addCamera({
        camera_id: cameraId,
        name: addForm.name.trim(),
        location: addForm.location.trim(),
        lat: lat.value,
        lng: lng.value,
        rtsp_url: addForm.rtsp_url.trim(),
      })
      toast(`Camera "${addForm.name.trim()}" added`, 'ok')
      closeAdd()
      reloadCameras?.()
    } catch (e) {
      setAddError(e.message || 'Could not add the camera')
    } finally {
      setAddLoading(false)
    }
  }

  const handleDelete = async (cam) => {
    if (!(await ask({ title: 'Delete camera', message: `Delete camera ${cam.camera_id}? Its history stays, but it stops being monitored.`, confirmLabel: 'Delete', danger: true }))) return
    try {
      await deleteCamera(cam.camera_id)
      toast('Camera deleted', 'ok')
      reloadCameras?.()
    } catch (e) {
      toast(e.message || 'Delete failed', 'danger')
    }
  }

  // Police officer assignment (camera -> officers). The first selected officer is primary.
  const [officerMap, setOfficerMap] = useState({})
  const [policeUsers, setPoliceUsers] = useState([])
  const [assignCam, setAssignCam] = useState(null)
  const [assignIds, setAssignIds] = useState([])
  const loadOfficers = () => fetchCameraOfficerMap().then(setOfficerMap).catch(() => {})
  useEffect(() => {
    loadOfficers()
    if (isAdmin) fetchUsers().then((u) => setPoliceUsers(u.filter((x) => x.role === 'police' && x.is_active))).catch(() => {})
  }, [isAdmin, cameras.length])
  const openAssign = (cam) => { setAssignCam(cam); setAssignIds((officerMap[cam.camera_id] || []).map((o) => o.id)) }
  const saveAssign = async () => {
    try {
      await setCameraOfficers(assignCam.camera_id, assignIds)
      toast('Officers assigned', 'ok')
      setAssignCam(null)
      loadOfficers()
    } catch (e) {
      toast(e.message || 'Assign failed', 'danger')
    }
  }
  const officerNames = (cam) => (officerMap[cam.camera_id] || []).map((o) => o.name).join(', ') || 'None assigned'

  const handleToggle = async (cam) => {
    if (cam.active && !(await ask({ title: 'Turn off camera', message: `Turn off "${cam.name || cam.camera_id}"? Detection and recording stop until it is turned back on.`, confirmLabel: 'Turn off', danger: true }))) return
    try {
      await updateCamera(cam.camera_id, {
        camera_id: cam.camera_id,
        name: cam.name,
        active: !cam.active,
      })
      toast(cam.active ? 'Camera turned off' : 'Camera turned on', 'ok')
      reloadCameras?.()
    } catch (e) {
      toast(`Could not change the camera: ${e.message}`, 'danger')
    }
  }

  const liveIds = new Set(Object.keys(systemStatus?.cameras || {}))

  const rows = cameras.map((c) => {
    const live = liveIds.has(c.camera_id)
    return {
      ...c,
      live,
      health: healthOf(c, live),
      fps: live ? systemStatus.cameras[c.camera_id]?.fps ?? null : null,
      threat: live ? systemStatus.cameras[c.camera_id]?.threat_score ?? null : null,
    }
  }).sort((a, b) => (b.live - a.live) || (b.active - a.active))

  const enabled = rows.filter((r) => r.active).length
  const streaming = rows.filter((r) => r.live).length

  const actions = (cam) => (
    <>
      {isAdmin && <button className="btn btn-sm" onClick={() => handleToggle(cam)}>{cam.active ? 'Turn off' : 'Turn on'}</button>}
      {isAdmin && <button className="btn btn-sm" onClick={() => openAssign(cam)}>Assign officers</button>}
      {canManage && <button className="btn btn-sm btn-ghost" onClick={() => handleDelete(cam)}>Delete</button>}
    </>
  )

  return (
    <>
      <div className="grid grid-4 mb">
        <Stat label="Cameras" value={rows.length} delta="Registered in the system" accent="primary" icon={Icons.camera} />
        <Stat label="Streaming" value={streaming} delta="Sending video to detection now" accent="ok" icon={Icons.live} />
        <Stat label="No signal" value={enabled - streaming} delta="Turned on but not sending video" accent={enabled - streaming ? 'warn' : 'ok'} icon={Icons.alert} />
        <Stat label="Turned off" value={rows.length - enabled} delta="Not monitored" accent={rows.length - enabled ? 'danger' : 'ok'} icon={Icons.eye} />
      </div>

      <Card
        title="Cameras"
        sub="Status, location and assigned officers"
        actions={
          <div style={{ display: 'flex', gap: 8 }}>
            <Seg value={view} onChange={setView} options={[{ value: 'grid', label: 'Grid' }, { value: 'list', label: 'List' }]} />
            {canManage && (
              <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
                <Icons.camera /> Add camera
              </button>
            )}
          </div>
        }
        flush={view === 'list' && rows.length > 0}
      >
        {rows.length === 0 && (
          <Empty icon={Icons.camera}>{canManage ? 'No cameras yet. Use "Add camera" to register the first one.' : 'No cameras have been registered yet.'}</Empty>
        )}

        {rows.length > 0 && view === 'grid' && (
          <div className="grid grid-3">
            {rows.map((cam) => (
              <div key={cam.camera_id} className="fleet-card">
                <div className="fleet-media">
                  <div className="fleet-state"><Icons.camera /><span>{cam.health.label}</span></div>
                  {cam.live && (
                    <img
                      src={liveStreamUrl(cam.camera_id)}
                      alt={`Live view from ${cam.name || cam.camera_id}`}
                      onError={(e) => { e.target.style.display = 'none' }}
                    />
                  )}
                  {cam.live && cam.fps != null && <span className="cam-chip">{Number(cam.fps).toFixed(1)} fps</span>}
                </div>
                <div className="fleet-body">
                  <div className="fleet-head">
                    <b title={cam.name || cam.camera_id}>{cam.name || cam.camera_id}</b>
                    <Tag tone={cam.health.tone}>{cam.health.label}</Tag>
                  </div>
                  <div className="fleet-meta">{cam.location || 'No location set'}</div>
                  <div className="fleet-meta">Officers: {officerNames(cam)}</div>
                  {(isAdmin || canManage) && <div className="fleet-actions">{actions(cam)}</div>}
                </div>
              </div>
            ))}
          </div>
        )}

        {rows.length > 0 && view === 'list' && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Camera</th><th>Location</th><th>Status</th><th>Frame rate</th><th>Threat score</th><th>Officers</th><th>GPS</th>{(isAdmin || canManage) && <th />}</tr>
              </thead>
              <tbody>
                {rows.map((cam) => (
                  <tr key={cam.camera_id}>
                    <td><b>{cam.name || cam.camera_id}</b><div className="meta mono">{cam.camera_id}</div></td>
                    <td>{cam.location || '—'}</td>
                    <td><Tag tone={cam.health.tone}>{cam.health.label}</Tag></td>
                    <td>{cam.fps != null ? `${Number(cam.fps).toFixed(1)} fps` : '—'}</td>
                    <td>{cam.threat != null ? cam.threat : '—'}</td>
                    <td>{officerNames(cam)}</td>
                    <td className="mono">{fmtGps(cam)}</td>
                    {(isAdmin || canManage) && <td><div className="cell-actions">{actions(cam)}</div></td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {assignCam && (
        <Modal
          title={`Assign officers to ${assignCam.name || assignCam.camera_id}`}
          onClose={() => setAssignCam(null)}
          footer={<div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button className="btn" onClick={() => setAssignCam(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={saveAssign}>Save</button>
          </div>}
        >
          {policeUsers.length === 0 && <div className="muted">No police users yet. Create one on the Users page with the Police role and a phone number.</div>}
          {policeUsers.map((u) => (
            <label key={u.id} className="row" style={{ cursor: 'pointer' }}>
              <span>
                <input type="checkbox" checked={assignIds.includes(u.id)}
                  onChange={(e) => setAssignIds((ids) => (e.target.checked ? [...ids, u.id] : ids.filter((i) => i !== u.id)))} />
                {' '}<b>{u.username}</b> <span className="muted">{u.phone || 'No phone number, so no SMS'}</span>
                {assignIds[0] === u.id && <> <Tag tone="ok">Primary</Tag></>}
              </span>
            </label>
          ))}
          <p className="note">The first officer you select is the primary and receives the incident. Every selected officer is alerted.</p>
        </Modal>
      )}

      {showAdd && (
        <Modal
          title="Add camera"
          onClose={closeAdd}
          footer={
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button className="btn" onClick={closeAdd}>Cancel</button>
              <button className="btn btn-primary" onClick={saveCamera} disabled={addLoading || !addForm.name.trim()}>
                {addLoading ? 'Saving…' : 'Add camera'}
              </button>
            </div>
          }
        >
          <div className="form-grid">
            {addError && <div className="login-error" role="alert">{addError}</div>}

            <label className="field">
              Name
              <input type="text" className="input" placeholder="Front gate" value={addForm.name} autoFocus
                onChange={(e) => setAddForm((f) => ({ ...f, name: e.target.value, camera_id: f.camera_id === slug(f.name) ? slug(e.target.value) : f.camera_id }))} />
            </label>

            <label className="field">
              Camera ID
              <input type="text" className="input mono" placeholder="front_gate" value={addForm.camera_id} onChange={setField('camera_id')} />
              <span className="field-hint">Filled in from the name. Lowercase letters, numbers and underscores; it cannot be changed later.</span>
            </label>

            <div className="field">
              <label htmlFor="cam-url">Video address</label>
              <div className="input-row">
                <input id="cam-url" type="text" className="input" placeholder="rtsp://192.168.0.103:554/stream or http://…/video"
                  value={addForm.rtsp_url} onChange={setField('rtsp_url')} />
                <button type="button" className="btn" disabled={addLoading || !addForm.rtsp_url.trim()} onClick={lookUpLocation}>Look up location</button>
              </div>
              <span className="field-hint">The RTSP or HTTP stream of the camera. "Look up location" fills the fields below for public addresses.</span>
            </div>

            <label className="field">
              Location
              <input type="text" className="input" placeholder="Building A, main entrance" value={addForm.location} onChange={setField('location')} />
            </label>

            <div className="two">
              <label className="field">
                Latitude
                <input type="number" step="any" min="-90" max="90" className="input" placeholder="23.8103" value={addForm.lat} onChange={setField('lat')} />
              </label>
              <label className="field">
                Longitude
                <input type="number" step="any" min="-180" max="180" className="input" placeholder="90.4125" value={addForm.lng} onChange={setField('lng')} />
              </label>
            </div>
          </div>
        </Modal>
      )}
      {confirmDialog}
    </>
  )
}
