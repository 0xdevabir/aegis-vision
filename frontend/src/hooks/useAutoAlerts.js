import { useEffect } from 'react'
import { playAlertSound, showBrowserNotification, flashDocumentTitle, requestNotificationPermission } from './alertNotifications'

const CRITICAL_TYPES = new Set(['CRIMINAL_DETECTED', 'WEAPON_DETECTED'])

export function useAutoAlerts(onCriticalAlert) {
  useEffect(() => {
    requestNotificationPermission()
  }, [])

  const handleAlert = (data) => {
    const type = data.alert_type || data.event_type
    if (!type || type === 'PIPELINE_HEARTBEAT') return

    const severity = data.severity || 'info'
    const msg = data.message || data.person_name || type.replace(/_/g, ' ')
    const camera = data.camera_location || data.camera_id || 'Unknown camera'

    if (CRITICAL_TYPES.has(type) || severity === 'critical') {
      playAlertSound('critical')
      showBrowserNotification(
        `🚨 ${type.replace(/_/g, ' ')}`,
        `${msg} — ${camera}${data.camera_lat ? ` @ ${data.camera_lat.toFixed(5)}, ${data.camera_lng.toFixed(5)}` : ''}`,
      )
      flashDocumentTitle(`${type.replace(/_/g, ' ')}`)
      onCriticalAlert?.({
        type,
        alertId: data.alert_id ?? data.data?.alert_id,
        message: msg,
        camera: data.camera_location || data.camera_id || 'Unknown camera',
        cameraId: data.camera_id,
        cameraName: data.camera_name || data.data?.camera_name,
        personName: data.person_name,
        timestamp: data.timestamp,
        severity,
        lat: data.camera_lat ?? data.data?.camera_lat,
        lng: data.camera_lng ?? data.data?.camera_lng,
        mapsUrl: data.maps_url ?? data.data?.maps_url,
        assignedOfficers: data.assigned_officers ?? data.data?.assigned_officers ?? [],
      })
    } else if (severity === 'high') {
      playAlertSound('high')
    }
  }

  return { handleAlert }
}
