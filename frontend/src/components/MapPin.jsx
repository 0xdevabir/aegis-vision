/** Embedded map showing pinpoint camera GPS location. */

export function MapPin({ lat, lng, label, height = 220 }) {
  if (lat == null || lng == null) return null

  const d = 0.004
  const bbox = `${lng - d},${lat - d * 0.7},${lng + d},${lat + d * 0.7}`
  const embedSrc = `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${lat}%2C${lng}`
  const googleMaps = `https://www.google.com/maps?q=${lat},${lng}`
  const osmLink = `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=18/${lat}/${lng}`

  return (
    <div className="map-pin">
      <div className="map-pin-header">
        <span>📍 Pinpoint Location</span>
        <span className="map-coords">{Number(lat).toFixed(5)}, {Number(lng).toFixed(5)}</span>
      </div>
      {label && <p className="map-label">{label}</p>}
      <iframe
        title="Camera location map"
        className="map-iframe"
        src={embedSrc}
        style={{ height }}
      />
      <div className="map-links">
        <a href={googleMaps} target="_blank" rel="noreferrer">Google Maps</a>
        <a href={osmLink} target="_blank" rel="noreferrer">OpenStreetMap</a>
      </div>
    </div>
  )
}
