import { useEffect, useState } from 'react'
import { isAlertSoundMuted, playAlertSound, setAlertSoundMuted } from '../hooks/alertNotifications'

const REPEAT_MS = 8000

// The backend message also carries GPS and a map link; the card shows those as separate fields.
const headline = (m) => (m || '').split(' — GPS')[0].split(' | ')[0]

/** Floating critical-alert card. It stays (and the tone repeats) until someone acknowledges it. */
export function CriticalAlertBanner({ alert, onDismiss, onAcknowledge, onViewMap, onOpenAlerts, repeatSound = true }) {
  const [muted, setMuted] = useState(isAlertSoundMuted)

  useEffect(() => {
    if (!alert || muted || !repeatSound) return undefined
    const t = setInterval(() => playAlertSound('critical'), REPEAT_MS)
    return () => clearInterval(t)
  }, [alert, muted, repeatSound])

  if (!alert) return null
  const hasGps = alert.lat != null && alert.lng != null
  const officers = alert.assignedOfficers || []
  const toggleMute = () => { setAlertSoundMuted(!muted); setMuted(!muted) }

  return (
    <div className="critical-alert-banner" role="alert" aria-live="assertive">
      <div className="critical-head">
        <span aria-hidden="true">🚨</span>
        <strong>{alert.type?.replace(/_/g, ' ')}</strong>
        <button className="critical-x" onClick={toggleMute} aria-label={muted ? 'Unmute alert sound' : 'Mute alert sound'} title={muted ? 'Sound off' : 'Sound on'}>
          {muted ? '🔕' : '🔔'}
        </button>
        <button className="critical-x" onClick={onDismiss} aria-label="Hide alert">×</button>
      </div>
      <div className="critical-body">
        <div className="critical-title">{headline(alert.message)}</div>
        <dl className="critical-grid">
          <dt>Camera</dt><dd>{alert.cameraName || alert.camera}{alert.cameraId ? ` (${alert.cameraId})` : ''}</dd>
          {hasGps && (<><dt>GPS</dt><dd className="mono">{Number(alert.lat).toFixed(5)}, {Number(alert.lng).toFixed(5)}</dd></>)}
          <dt>Officer</dt>
          <dd>{officers.length ? `${officers.map((o) => o.name).join(', ')} alerted` : 'None assigned to this camera'}</dd>
        </dl>
      </div>
      <div className="critical-actions">
        {onAcknowledge && alert.alertId != null && <button className="btn btn-sm btn-primary" onClick={onAcknowledge}>Acknowledge</button>}
        {onOpenAlerts && <button className="btn btn-sm" onClick={onOpenAlerts}>Review</button>}
        {hasGps && onViewMap && <button className="btn btn-sm" onClick={onViewMap}>View on map</button>}
      </div>
    </div>
  )
}
