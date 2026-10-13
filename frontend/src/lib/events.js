/* Event/alert taxonomy shared by Triage, Detection Center and Overview. */

export const EVENT_META = {
  CRIMINAL_DETECTED: { label: 'Watchlist match', group: 'faces', icon: 'watchlist' },
  WEAPON_DETECTED: { label: 'Weapon detected', group: 'weapon', icon: 'alert' },
  SUSPICIOUS_VEHICLE: { label: 'Watchlisted vehicle', group: 'vehicle', icon: 'vehicle' },
  SUSPICIOUS_BEHAVIOR: { label: 'Suspicious behavior', group: 'behavior', icon: 'eye' },
  ANOMALY_DETECTED: { label: 'Zone anomaly', group: 'behavior', icon: 'eye' },
  INTRUSION: { label: 'Restricted-zone entry', group: 'behavior', icon: 'shield' },
  FIRE_SMOKE_DETECTED: { label: 'Fire / smoke', group: 'fire', icon: 'fire' },
  FALL_SUSPECTED: { label: 'Possible fall', group: 'fall', icon: 'users' },
}

export const GROUPS = [
  { id: 'all', label: 'All' },
  { id: 'faces', label: 'Watchlist' },
  { id: 'weapon', label: 'Weapons' },
  { id: 'vehicle', label: 'Vehicles' },
  { id: 'behavior', label: 'Behavior' },
  { id: 'fire', label: 'Fire & smoke' },
  { id: 'fall', label: 'Falls' },
]

export function eventLabel(type = '') {
  const t = String(type).toUpperCase()
  return EVENT_META[t]?.label || t.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase())
}

export function eventGroup(type = '') {
  return EVENT_META[String(type).toUpperCase()]?.group || 'other'
}

export function eventIconKey(type = '') {
  return EVENT_META[String(type).toUpperCase()]?.icon || 'eye'
}

export const REVIEW_LABEL = {
  pending: 'Needs review',
  confirmed: 'Confirmed',
  rejected: 'Rejected',
  not_required: '',
}

export const REJECT_REASONS = [
  { value: 'false_detection', label: 'False detection' },
  { value: 'known_person', label: 'Known / authorised person' },
  { value: 'duplicate', label: 'Duplicate of another alert' },
  { value: 'test', label: 'Test or drill' },
  { value: 'other', label: 'Other' },
]

/* API alert row → UI model */
export function fromAlertRow(a) {
  return {
    id: a.id,
    type: a.alert_type,
    severity: a.severity || 'info',
    time: a.timestamp,
    camera: a.camera_location || a.camera_id,
    cameraId: a.camera_id,
    trackId: a.track_id,
    personName: a.person_name,
    plate: a.plate_number,
    msg: a.message,
    acknowledged: a.acknowledged,
    dismissed: a.dismissed,
    reviewStatus: a.review_status || 'not_required',
    reviewNote: a.review_note,
  }
}

/* Plain-language "why did this fire" — shown to operators so they can judge it. */
export const EXPLAIN = {
  CRIMINAL_DETECTED: 'A face matched an enrolled person in at least 2 frames. A match is a lead, not an identification — compare the snapshot with the enrolled photos before confirming.',
  WEAPON_DETECTED: 'A weapon-like object overlapped a person in at least 3 of the last 5 processed frames. Check the snapshot: tools, phones and umbrellas are common false positives.',
  FIRE_SMOKE_DETECTED: 'Fire or smoke was seen in at least 5 of the last 8 frames. Steam, fog and bright lights can look similar.',
  FALL_SUSPECTED: 'A person was upright, then stayed horizontal for 2 seconds or more. They may be resting or exercising — check the camera.',
  INTRUSION: "A person's feet entered a zone marked restricted for this camera.",
  ANOMALY_DETECTED: 'A zone rule fired (crowding or long dwell time).',
  SUSPICIOUS_BEHAVIOR: 'Movement or posture matched a behaviour rule (loitering, rapid or erratic movement, raised arms). These rules are heuristics and do produce false alarms.',
  SUSPICIOUS_VEHICLE: 'A plate read matched the vehicle watchlist. OCR misreads are common — verify the plate in the snapshot.',
}
