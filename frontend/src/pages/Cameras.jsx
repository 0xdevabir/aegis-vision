import { useEffect, useState } from 'react'
import { Card, Icons, Tag, Empty, Seg, Modal, useConfirm } from '../components/ui'
import { resolveIp, addCamera, updateCamera, liveStreamUrl, deleteCamera, fetchUsers, fetchCameraOfficerMap, setCameraOfficers } from '../services/api'
import { useToast } from '../components/Toast'
import { can } from '../lib/permissions'

// Status comes only from what the system really knows: the pipeline heartbeat and the enabled flag.
function healthOf(cam, live) {
  if (live) return { label: 'Streaming', tone: 'ok' }
  if (cam.active) return { label: 'Enabled, no signal', tone: 'warn' }
  return { label: 'Off', tone: 'danger' }
}

const slug = (s) => (s || '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40)

export function Cameras({ ctx }) {
  const { cameras, systemStatus, reloadCameras, me } = ctx
  const { push: toast } = useToast()
  const [ask, confirmDialog] = useConfirm()
  const [view, setView] = useState('grid')
  
  // Add Camera State
  const [showAdd, setShowAdd] = useState(false)
  const [addForm, setAddForm] = useState({ ipLink: '', camera_id: '', name: '', location: '', lat: '', lng: '', rtsp_url: '' })
  const [addLoading, setAddLoading] = useState(false)
  const [addError, setAddError] = useState('')

  const handleDelete = async (cam) => {
    if (me?.role !== 'admin') { toast('Admin only', 'danger'); return }
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
    if (me?.role === 'admin') fetchUsers().then((u) => setPoliceUsers(u.filter((x) => x.role === 'police' && x.is_active))).catch(() => {})
  }, [me?.role, cameras.length])
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
  const officerNames = (cam) => (officerMap[cam.camera_id] || []).map((o) => o.name).join(', ') || 'none'

  const handleToggle = async (cam) => {
    if (me?.role !== 'admin') { toast('Admin only', 'danger'); return }
    if (cam.active && !(await ask({ title: 'Turn off camera', message: `Turn off "${cam.name || cam.camera_id}"? Detection and recording stop until it is turned back on.`, confirmLabel: 'Turn off', danger: true }))) return
    try {
      await updateCamera(cam.camera_id, {
        camera_id: cam.camera_id,
        name: cam.name,
        active: !cam.active,
      })
      toast(cam.active ? 'Camera turned off' : 'Camera turned on', 'ok')
      if (reloadCameras) reloadCameras()
    } catch (e) {
      toast(`Failed to toggle: ${e.message}`, 'danger')
    }
  }

  const liveIds = new Set(Object.keys(systemStatus?.cameras || {}))

  const rows = cameras.map((c) => {
    const live = liveIds.has(c.camera_id)
    const h = healthOf(c, live)
    return {
      ...c,
      live,
      health: h,
      fps: live ? systemStatus.cameras[c.camera_id]?.fps ?? null : null,
      threat: live ? systemStatus.cameras[c.camera_id]?.threat_score ?? null : null,
    }
  }).sort((a, b) => (b.live - a.live) || (b.active - a.active))

  const online = rows.filter((r) => r.active).length

  return (
    <>
      <div className="grid grid-4" style={{ marginBottom: 14 }}>
        <div className="stat accent-primary"><span className="label">Registered</span><span className="value">{rows.length}</span></div>
        <div className="stat accent-ok"><span className="label">Online</span><span className="value">{online}</span></div>
        <div className="stat accent-danger"><span className="label">Offline</span><span className="value">{rows.length - online}</span></div>
        <div className="stat accent-cyan"><span className="label">Streaming to AI</span><span className="value">{rows.filter((r) => r.live).length}</span></div>
      </div>

      <Card
        title="Camera Fleet"
        sub="health, network & stream metrics"
        actions={
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
              <Icons.camera /> Add Camera
            </button>
            <Seg value={view} onChange={setView} options={[{ value: 'grid', label: 'Grid' }, { value: 'list', label: 'List' }]} />
          </div>
        }
        flush={view === 'list'}
      >
        {rows.length === 0 && <Empty icon={Icons.camera}>No cameras registered. Add one using the button above.</Empty>}

        {view === 'grid' ? (
          <div className="grid grid-3">
            {rows.map((cam) => (
              <div key={cam.camera_id} className="card" style={{ boxShadow: 'none' }}>
                <div className="cam-tile" style={{ borderRadius: 0, border: 'none', position: 'relative' }}>
                  {cam.live && (
                    <img
                      src={liveStreamUrl(cam.camera_id)}
                      alt={cam.name || cam.camera_id}
                      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.85 }}
                      onError={(e) => { e.target.style.display = 'none' }}
                    />
                  )}
                  <div className="scanline" />
                  <div className="cam-label" style={{ position: 'relative', zIndex: 2 }}>{cam.live && <span className="rec-dot" />}{cam.name || cam.camera_id}</div>
                  {cam.active
                    ? <div className="cam-stats" style={{ position: 'relative', zIndex: 2 }}><span>{cam.fps != null ? `${Number(cam.fps).toFixed(1)} FPS` : 'Waiting for signal'}</span>{cam.threat != null && <span>Threat {cam.threat}</span>}</div>
                    : <div className="cam-offline" style={{ position: 'relative', zIndex: 2 }}><div>Signal lost</div></div>}
                </div>
                <div style={{ padding: '12px 14px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <b style={{ fontSize: '0.86rem' }}>{cam.name || cam.camera_id}</b>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <Tag tone={cam.health.tone}>{cam.health.label}</Tag>
                      {can(me?.role, 'camera.manage') && <button className="btn btn-sm btn-ghost" onClick={() => handleDelete(cam)}>Delete</button>}
                  {me?.role === 'admin' && (
                        <button className="btn btn-sm" onClick={() => handleToggle(cam)}>
                          {cam.active ? 'Turn off' : 'Turn on'}
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="meta muted" style={{ fontSize: '0.74rem' }}>{cam.location || 'No location set'}</div>
                  <div className="meta muted" style={{ fontSize: '0.74rem' }}>
                    Officer: {officerNames(cam)}
                    {me?.role === 'admin' && <button className="btn btn-sm btn-ghost" style={{ marginLeft: 6 }} onClick={() => openAssign(cam)}>Assign</button>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Camera</th><th>Location</th><th>Health</th><th>FPS</th><th>Threat</th><th>Officer</th><th>GPS</th><th>Action</th></tr>
            </thead>
            <tbody>
              {rows.map((cam) => (
                <tr key={cam.camera_id}>
                  <td><b>{cam.name || cam.camera_id}</b><div className="meta mono">{cam.camera_id}</div></td>
                  <td>{cam.location || '—'}</td>
                  <td><Tag tone={cam.health.tone}>{cam.health.label}</Tag></td>
                  <td>{cam.fps != null ? Number(cam.fps).toFixed(1) : '—'}</td>
                  <td>{cam.threat != null ? cam.threat : '—'}</td>
                  <td>{officerNames(cam)}</td>
                  <td className="mono">{cam.lat != null ? `${cam.lat.toFixed(4)}, ${cam.lng.toFixed(4)}` : '—'}</td>
                  <td>
                    {can(me?.role, 'camera.manage') && <button className="btn btn-sm btn-ghost" onClick={() => handleDelete(cam)}>Delete</button>}
                  {me?.role === 'admin' && (
                      <button className="btn btn-sm" onClick={() => handleToggle(cam)}>
                        {cam.active ? 'Turn off' : 'Turn on'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {assignCam && (
        <Modal
          title={`Assign police officers: ${assignCam.name || assignCam.camera_id}`}
          onClose={() => setAssignCam(null)}
          footer={<div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button className="btn" onClick={() => setAssignCam(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={saveAssign}>Save</button>
          </div>}
        >
          {policeUsers.length === 0 && <div className="muted">No police users yet. Create one in Users (role: Police) with a phone number.</div>}
          {policeUsers.map((u) => (
            <label key={u.id} className="row" style={{ cursor: 'pointer' }}>
              <span>
                <input type="checkbox" checked={assignIds.includes(u.id)}
                  onChange={(e) => setAssignIds((ids) => (e.target.checked ? [...ids, u.id] : ids.filter((i) => i !== u.id)))} />
                {' '}<b>{u.username}</b> <span className="muted">{u.phone || 'no phone: SMS skipped'}</span>
                {assignIds[0] === u.id && <Tag tone="ok">primary</Tag>}
              </span>
            </label>
          ))}
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>The first selected officer is primary and gets the incident ticket. All selected officers are alerted.</div>
        </Modal>
      )}

      {showAdd && (
        <Modal 
          title="Add New Camera" 
          onClose={() => setShowAdd(false)}
          footer={
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button className="btn" onClick={() => setShowAdd(false)}>Cancel</button>
              <button 
                className="btn btn-primary" 
                onClick={async () => {
                  try {
                    setAddLoading(true)
                    setAddError('')
                    await addCamera({
                      camera_id: addForm.camera_id,
                      name: addForm.name,
                      location: addForm.location,
                      lat: parseFloat(addForm.lat) || null,
                      lng: parseFloat(addForm.lng) || null,
                      rtsp_url: addForm.rtsp_url
                    })
                    setShowAdd(false)
                    if (reloadCameras) reloadCameras()
                  } catch (e) {
                    setAddError(e.message)
                  } finally {
                    setAddLoading(false)
                  }
                }}
                disabled={addLoading || !addForm.camera_id || !addForm.name}
              >
                {addLoading ? 'Saving...' : 'Save Camera'}
              </button>
            </div>
          }
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {addError && <div className="alert alert-danger">{addError}</div>}
            
            <div className="form-group">
              <label>IP Link (URL)</label>
              <div style={{ display: 'flex', gap: '8px' }}>
                <input 
                  type="text" 
                  className="input" 
                  style={{ flex: 1 }}
                  placeholder="e.g. http://192.168.0.103:8080/video" 
                  value={addForm.ipLink}
                  onChange={(e) => {
                    const val = e.target.value
                    setAddForm({ 
                      ...addForm, 
                      ipLink: val,
                      rtsp_url: val 
                    })
                  }}
                />
                <button 
                  className="btn" 
                  disabled={addLoading || !addForm.ipLink}
                  onClick={async () => {
                    try {
                      setAddLoading(true)
                      const res = await resolveIp(addForm.ipLink)
                      setAddForm({
                        ...addForm,
                        camera_id: addForm.camera_id || slug(addForm.name),
                        name: addForm.name || 'New Camera',
                        location: res.location || '',
                        lat: res.lat || '',
                        lng: res.lng || '',
                        rtsp_url: addForm.ipLink
                      })
                      if (res.error && res.error !== 'private range') {
                        setAddError(`Location fetch note: ${res.error}`)
                      }
                    } catch (e) {
                      setAddError('Failed to fetch IP details: ' + e.message)
                    } finally {
                      setAddLoading(false)
                    }
                  }}
                >
                  Fetch Details
                </button>
              </div>
              <small className="muted" style={{ display: 'block', marginTop: '4px' }}>
                Enter the IP link to auto-fill details and fetch geolocation.
              </small>
            </div>

            <div className="form-group">
              <label>Camera ID</label>
              <input type="text" className="input" value={addForm.camera_id} onChange={(e) => setAddForm({...addForm, camera_id: e.target.value})} />
            </div>
            
            <div className="form-group">
              <label>Name</label>
              <input type="text" className="input" value={addForm.name} onChange={(e) => setAddForm({...addForm, name: e.target.value})} />
            </div>

            <div className="form-group">
              <label>Location</label>
              <input type="text" className="input" value={addForm.location} onChange={(e) => setAddForm({...addForm, location: e.target.value})} />
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <div className="form-group" style={{ flex: 1 }}>
                <label>Latitude</label>
                <input type="number" step="any" className="input" value={addForm.lat} onChange={(e) => setAddForm({...addForm, lat: e.target.value})} />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>Longitude</label>
                <input type="number" step="any" className="input" value={addForm.lng} onChange={(e) => setAddForm({...addForm, lng: e.target.value})} />
              </div>
            </div>

            <div className="form-group">
              <label>RTSP / Video URL</label>
              <input type="text" className="input" value={addForm.rtsp_url} onChange={(e) => setAddForm({...addForm, rtsp_url: e.target.value})} />
            </div>
          </div>
        </Modal>
      )}
      {confirmDialog}
    </>
  )
}
