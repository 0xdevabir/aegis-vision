/* Zone-editor helpers. All coordinates are normalized 0–1 (resolution independent). */

export const clamp01 = (v) => Math.min(1, Math.max(0, v))

export function centroid(points) {
  const n = points.length || 1
  return [points.reduce((s, p) => s + p[0], 0) / n, points.reduce((s, p) => s + p[1], 0) / n]
}

export function nextName(prefix, names) {
  const taken = new Set(names.map((n) => n.toLowerCase()))
  let i = 1
  while (taken.has(`${prefix} ${i}`.toLowerCase())) i += 1
  return `${prefix} ${i}`
}

export const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1])

/* Client-side checks mirroring the server, so errors appear before saving. */
export function validateNames(zones, lines) {
  const seen = new Set()
  for (const s of [...zones, ...lines]) {
    const name = (s.name || '').trim()
    if (!name) return 'Every zone and line needs a name'
    if (seen.has(name.toLowerCase())) return `"${name}" is used twice — names must be unique`
    seen.add(name.toLowerCase())
  }
  return null
}

export const core = (zones, lines) => JSON.stringify({ zones, lines })
