import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { fovPolygon } from '../lib/mapGeo'

// Self-hosted tiles can be set at build time: VITE_MAP_TILES=https://tiles.example/{z}/{x}/{y}.png
const TILE_URL = import.meta.env.VITE_MAP_TILES || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const SEV_COLOR = { critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#3b82f6', info: '#3b82f6' }

const camIcon = (status, selected) => L.divIcon({
  className: '',
  html: `<div class="ops-cam ops-cam--${status}${selected ? ' ops-cam--sel' : ''}"></div>`,
  iconSize: [22, 22], iconAnchor: [11, 11],
})

const alertIcon = (g, fresh) => L.divIcon({
  className: '',
  html: `<div class="ops-alert${fresh ? ' ops-alert--pulse' : ''}" style="--c:${SEV_COLOR[g.severity] || SEV_COLOR.low}">${g.events.length}</div>`,
  iconSize: [30, 30], iconAnchor: [15, 15],
})

export function OpsMap({
  cameras, statusOf, groups, layers, selectedId, focus, editId, placingId,
  onSelectCamera, onSelectGroup, onMoveCamera, onPlace, fitKey,
}) {
  const hostRef = useRef(null)
  const mapRef = useRef(null)
  const layerRef = useRef({ cams: null, alerts: null, heat: null, fov: null })
  const cbRef = useRef({})
  const tiles = useRef({ ok: 0, err: 0 })
  const [offline, setOffline] = useState(false)

  useEffect(() => { cbRef.current = { onSelectCamera, onSelectGroup, onMoveCamera, onPlace } })

  // create the map once
  useEffect(() => {
    const map = L.map(hostRef.current, { zoomControl: true, attributionControl: true }).setView([23.8103, 90.4125], 13)
    const tl = L.tileLayer(TILE_URL, { maxZoom: 19, attribution: '© OpenStreetMap contributors' }).addTo(map)
    tl.on('tileload', () => { tiles.current.ok += 1; setOffline(false) })
    tl.on('tileerror', () => { tiles.current.err += 1; if (tiles.current.ok === 0 && tiles.current.err >= 3) setOffline(true) })
    const lr = layerRef.current
    lr.heat = L.layerGroup().addTo(map)
    lr.fov = L.layerGroup().addTo(map)
    lr.cams = L.layerGroup().addTo(map)
    lr.alerts = L.layerGroup().addTo(map)
    map.on('click', (e) => cbRef.current.onPlace?.(e.latlng.lat, e.latlng.lng))
    mapRef.current = map
    return () => { map.remove(); mapRef.current = null }
  }, [])

  // cameras + coverage cones
  useEffect(() => {
    const lr = layerRef.current
    lr.cams.clearLayers(); lr.fov.clearLayers()
    cameras.forEach((c) => {
      const status = statusOf(c)
      const m = L.marker([c.plat, c.plng], { icon: camIcon(status, c.camera_id === selectedId), draggable: c.camera_id === editId, zIndexOffset: 100 })
      m.bindTooltip(c.name || c.camera_id, { direction: 'top', offset: [0, -10] })
      m.on('click', () => cbRef.current.onSelectCamera?.(c.camera_id))
      m.on('dragend', () => { const p = m.getLatLng(); cbRef.current.onMoveCamera?.(c.camera_id, p.lat, p.lng) })
      m.addTo(lr.cams)
      if (layers.coverage && c.heading != null) {
        L.polygon(fovPolygon(c), { color: '#22c55e', weight: 1, fillOpacity: 0.12, interactive: false }).addTo(lr.fov)
      }
    })
  }, [cameras, statusOf, selectedId, editId, layers.coverage])

  // alerts + heat
  useEffect(() => {
    const lr = layerRef.current
    lr.alerts.clearLayers(); lr.heat.clearLayers()
    groups.forEach((g) => {
      if (layers.heat) {
        L.circle([g.lat, g.lng], { radius: 25 + 18 * g.events.length, color: SEV_COLOR[g.severity], weight: 0, fillOpacity: 0.22, interactive: false }).addTo(lr.heat)
      }
      if (layers.alerts) {
        const newest = Math.max(...g.events.map((e) => new Date(/Z|[+-]\d\d:?\d\d$/.test(e.timestamp) ? e.timestamp : `${e.timestamp}Z`).getTime()))
        const fresh = Date.now() - newest < 5 * 60 * 1000 && g.events.some((e) => !e.acknowledged && e.severity === 'critical')
        L.marker([g.lat, g.lng], { icon: alertIcon(g, fresh), zIndexOffset: 500 })
          .on('click', () => cbRef.current.onSelectGroup?.(g.key))
          .addTo(lr.alerts)
      }
    })
  }, [groups, layers.alerts, layers.heat])

  // fit everything when asked
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const pts = [...cameras.map((c) => [c.plat, c.plng]), ...groups.map((g) => [g.lat, g.lng])]
    if (pts.length === 1) map.setView(pts[0], 16)
    else if (pts.length > 1) map.fitBounds(pts, { padding: [40, 40], maxZoom: 17 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey])

  // fly to a requested camera / alert
  useEffect(() => {
    const map = mapRef.current
    if (map && focus?.lat != null && focus?.lng != null) map.flyTo([focus.lat, focus.lng], 17, { duration: 0.8 })
  }, [focus])

  // placing mode: crosshair cursor
  useEffect(() => {
    if (hostRef.current) hostRef.current.style.cursor = placingId ? 'crosshair' : ''
  }, [placingId])

  return (
    <div className="ops-map-wrap">
      <div ref={hostRef} className={`ops-map ${offline ? 'ops-map--offline' : ''}`} role="application" aria-label="Operations map" />
      {offline && (
        <div className="ops-map-note">Map tiles are unavailable (offline). Camera and alert markers still work.</div>
      )}
    </div>
  )
}
