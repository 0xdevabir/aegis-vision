export const slug = (s) => (s || '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40)

/** addCamera() body for a camera detected on the computer: a free id, bound to that exact device. */
export function cameraForDevice(d, cameras = []) {
  const taken = new Set(cameras.map((c) => c.camera_id))
  const base = slug(d.name) || 'camera'
  let cameraId = base
  for (let n = 2; taken.has(cameraId); n += 1) cameraId = `${base}_${n}`
  return { camera_id: cameraId, name: d.name, location: 'Local', rtsp_url: d.source }
}

// One camera list for the whole dashboard: registered cameras, overlaid with the live
// heartbeat and stream state. `power` is the per-camera on/off map where the page has it.
// `unplugged`: ids of local webcams whose device is not connected; they are left out.
export function buildCamList(cameras = [], systemStatus, streamingCams = [], power = {}, unplugged = []) {
  const streaming = new Set(streamingCams)
  const beats = systemStatus?.cameras || {}
  const away = new Set(unplugged)
  const byId = new Map()
  // cam_0 / video_0 are placeholder identities for single-camera runs: only show them when active.
  const placeholder = (id) => id === 'cam_0' || id === 'video_0'
  cameras.forEach((c) => {
    const reporting = streaming.has(c.camera_id) || beats[c.camera_id]
    if (away.has(c.camera_id) && !reporting) return
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
      status: power[c.camera_id] === false ? 'off' : streaming.has(c.camera_id) ? 'live' : beat ? 'online' : 'offline',
      fps: beat?.fps ?? null,
      threat_score: beat?.threat_score ?? 0,
      flags: beat?.flags || [],
      dvr: Boolean(beat?.recording),   // only claim REC when the pipeline reports it
    }
  }).sort((x, y) => (y.status === 'live') - (x.status === 'live') || x.name.localeCompare(y.name))
}
