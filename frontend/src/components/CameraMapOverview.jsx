import { MapPin } from './MapPin'

export function CameraMapOverview({ cameras = [], events = [] }) {
  const primary = cameras[0]
  const eventPins = (events || []).filter((e) => e.lat != null && e.lng != null).slice(0, 5)

  if (!primary) return null

  return (
    <div>
      <MapPin lat={primary.lat} lng={primary.lng} label={primary.name || primary.location} height={280} />
      <div className="map-legend" style={{ marginTop: 10 }}>
        <span className="key"><span className="swatch" style={{ background: 'var(--ok)' }} /> Camera</span>
        <span className="key"><span className="swatch" style={{ background: 'var(--danger)' }} /> Detection</span>
      </div>
      {cameras.length > 1 && (
        <div style={{ marginTop: 12, fontSize: 12 }}>
          {cameras.map((c) => (
            <div key={c.camera_id} className="meta">
              {c.name || c.camera_id}: {c.lat?.toFixed(4)}, {c.lng?.toFixed(4)}
            </div>
          ))}
        </div>
      )}
      {eventPins.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <b style={{ fontSize: 12 }}>Recent event locations</b>
          {eventPins.map((ev, i) => (
            <div key={i} className="meta">{ev.description || ev.event_type} @ {Number(ev.lat).toFixed(4)}, {Number(ev.lng).toFixed(4)}</div>
          ))}
        </div>
      )}
    </div>
  )
}
