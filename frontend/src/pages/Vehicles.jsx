import { useState } from 'react'
import { Card, Icons, Tag, Empty, timeAgo, useConfirm } from '../components/ui'
import { can } from '../lib/permissions'
import { addVehiclePlate, deleteVehiclePlate } from '../services/api'
import { useToast } from '../components/Toast'

export function Vehicles({ ctx }) {
  const { plates, vehicleDetections, reloadVehicles, me } = ctx
  const { push: toast } = useToast()
  const [ask, confirmDialog] = useConfirm()
  const [newPlate, setNewPlate] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const removePlate = async (plate) => {
    if (me?.role !== 'admin') { toast('Admin only', 'danger'); return }
    if (!(await ask({ title: 'Remove plate', message: `Remove plate ${plate} from the watchlist?`, confirmLabel: 'Remove', danger: true }))) return
    try {
      await deleteVehiclePlate(plate)
      toast('Plate removed', 'ok')
      reloadVehicles?.()
    } catch (e) {
      toast(e.message || 'Remove failed', 'danger')
    }
  }

  const addPlate = async () => {
    if (!newPlate.trim()) return
    setBusy(true); setErr('')
    try {
      await addVehiclePlate(newPlate.trim(), reason.trim() || undefined)
      setNewPlate(''); setReason('')
      reloadVehicles?.()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid grid-23">
      <Card title="Vehicle Detections" sub="ANPR / license plate recognition" flush>
        {(!vehicleDetections || vehicleDetections.length === 0) ? (
          <div style={{ padding: 16 }}>
            <Empty icon={Icons.vehicle}>No vehicle detections yet — ANPR runs automatically in the pipeline</Empty>
          </div>
        ) : (
          <table className="table">
            <thead><tr><th>Plate</th><th>Camera</th><th>Time</th><th>Status</th></tr></thead>
            <tbody>
              {vehicleDetections.map((v, i) => (
                <tr key={v.id || i}>
                  <td className="mono"><b>{v.plate_number || '—'}</b></td>
                  <td>{v.camera_location || v.camera_id || '—'}</td>
                  <td className="muted">{timeAgo(v.timestamp)}</td>
                  <td><Tag tone={v.is_suspicious ? 'danger' : 'ok'}>{v.is_suspicious ? 'Watchlisted' : 'Clear'}</Tag></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {can(me?.role, 'vehicle.edit') && (
        <Card title="Add Watchlisted Plate">
          {err && <div className="login-error" style={{ marginBottom: 10 }}>{err}</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <label className="field">Plate number
              <input className="input" placeholder="DHA-1234" value={newPlate} onChange={(e) => setNewPlate(e.target.value.toUpperCase())} />
            </label>
            <label className="field">Reason
              <input className="input" placeholder="Stolen vehicle…" value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
            <button className="btn btn-primary" disabled={busy || !newPlate.trim()} onClick={addPlate}>
              <Icons.shield /> {busy ? 'Adding…' : 'Add to Watchlist'}
            </button>
          </div>
        </Card>
        )}

        <Card title="Plate Watchlist" sub={`${plates?.length || 0} plates`}>
          {(!plates || plates.length === 0) && <Empty icon={Icons.vehicle}>No watchlisted plates</Empty>}
          {(plates || []).map((p) => (
            <div key={p.id} className="row">
              <div>
                <b className="mono">{p.plate_number}</b>
                <div className="meta">{p.reason || 'No reason recorded'} · added {timeAgo(p.created_at)}</div>
              </div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <Tag tone={p.watchlisted ? 'danger' : 'muted'}>{p.watchlisted ? 'Watchlisted' : 'Cleared'}</Tag>
                {me?.role === 'admin' && (
                  <button className="btn btn-sm btn-ghost" onClick={() => removePlate(p.plate_number)}>Remove</button>
                )}
              </div>
            </div>
          ))}
        </Card>
      </div>
      {confirmDialog}
    </div>
  )
}
