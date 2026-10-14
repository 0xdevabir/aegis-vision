import { useEffect, useState } from 'react'
import { Empty, Icons, Modal, Tag } from './ui'
import { fetchCameraDevices } from '../services/api'

/** "Add camera": every camera connected to this computer, with Connect for the ones not in use yet.
    Polls while open, so a camera plugged in now shows up by itself. `onNetwork` adds an RTSP/HTTP camera instead. */
export function AddCameraModal({ cameras = [], onConnect, onNetwork, onClose }) {
  const [devices, setDevices] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  const load = () => fetchCameraDevices()
    .then((r) => { setDevices(r.devices || []); setError('') })
    .catch((e) => setError(e.message || 'Could not list the connected cameras'))

  useEffect(() => {
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [])

  const connect = async (d) => {
    setBusy(d.source)
    try { await onConnect(d) } finally { setBusy(''); load() }
  }

  return (
    <Modal
      title="Add camera"
      onClose={onClose}
      footer={
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
          {onNetwork ? <button className="btn" onClick={onNetwork}>Add a network camera</button> : <span />}
          <button className="btn" onClick={onClose}>Close</button>
        </div>
      }
    >
      {error && <div className="login-error" role="alert">{error}</div>}
      {devices === null && !error && <div className="muted">Looking for cameras…</div>}
      {devices?.length === 0 && (
        <Empty icon={Icons.camera}>No camera is connected to this computer. Plug one in and it appears here.</Empty>
      )}
      {devices?.map((d) => {
        const cam = cameras.find((c) => c.camera_id === d.camera_id)
        return (
          <div key={d.source} className="row">
            <div>
              <b>{d.name}</b>
              <div className="meta">{cam ? `Used by ${cam.name || cam.camera_id}` : 'Detected, not in use'}</div>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Tag tone={!cam ? 'info' : cam.active ? 'ok' : 'danger'}>{!cam ? 'New' : cam.active ? 'In use' : 'Paused'}</Tag>
              {!cam && onConnect && (
                <button className="btn btn-sm btn-primary" disabled={busy === d.source} onClick={() => connect(d)}>
                  {busy === d.source ? 'Connecting…' : 'Connect'}
                </button>
              )}
            </div>
          </div>
        )
      })}
    </Modal>
  )
}
