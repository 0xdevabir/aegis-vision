// Pure geometry/grouping helpers for the operations map.
const M_PER_DEG = 111320
const SEV_RANK = { critical: 3, high: 2, medium: 1, low: 0, info: 0 }

/** Cameras sharing identical coordinates are fanned out on a tiny circle so every one stays clickable. */
export function spreadCameras(cameras) {
  const groups = new Map()
  cameras.forEach((c) => {
    const key = `${c.lat.toFixed(5)},${c.lng.toFixed(5)}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(c)
  })
  const out = []
  groups.forEach((list) => {
    list.forEach((c, i) => {
      if (list.length === 1) { out.push({ ...c, plat: c.lat, plng: c.lng, spread: false }); return }
      const ang = (2 * Math.PI * i) / list.length
      const r = 0.00018
      out.push({ ...c, plat: c.lat + r * Math.cos(ang), plng: c.lng + r * Math.sin(ang), spread: true })
    })
  })
  return out
}

/** Pie-slice polygon for a camera's field of view. */
export function fovPolygon(cam) {
  const range = cam.range_m || 40
  const half = (cam.fov || 70) / 2
  const pts = [[cam.plat, cam.plng]]
  for (let a = -half; a <= half; a += 5) {
    const bearing = ((cam.heading + a) * Math.PI) / 180
    const dLat = (range * Math.cos(bearing)) / M_PER_DEG
    const dLng = (range * Math.sin(bearing)) / (M_PER_DEG * Math.cos((cam.plat * Math.PI) / 180))
    pts.push([cam.plat + dLat, cam.plng + dLng])
  }
  return pts
}

/** Alerts grouped by camera so each camera shows one badge with a count. */
export function groupEvents(events, cams) {
  const byCam = new Map(cams.map((c) => [c.camera_id, c]))
  const groups = new Map()
  events.forEach((e) => {
    const cam = byCam.get(e.camera_id)
    const lat = cam ? cam.plat : e.lat
    const lng = cam ? cam.plng : e.lng
    if (lat == null || lng == null) return
    const key = cam ? cam.camera_id : `${Number(lat).toFixed(5)},${Number(lng).toFixed(5)}`
    if (!groups.has(key)) groups.set(key, { key, cameraId: cam?.camera_id || null, name: cam?.name || e.camera_name, lat, lng, events: [] })
    groups.get(key).events.push(e)
  })
  return [...groups.values()].map((g) => ({
    ...g,
    severity: g.events.reduce((m, e) => (SEV_RANK[e.severity] > SEV_RANK[m] ? e.severity : m), 'low'),
  }))
}

