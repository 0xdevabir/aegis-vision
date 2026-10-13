/* The backend sends UTC timestamps without a zone suffix (e.g. "2026-10-04T12:00:00").
   JavaScript would read those as LOCAL time and show alerts hours off, so treat a
   zone-less ISO string as UTC. */
export function parseTs(ts) {
  if (ts == null || ts === '') return null
  if (ts instanceof Date) return ts
  let s = String(ts)
  if (/^\d{4}-\d{2}-\d{2}T[\d:.]+$/.test(s)) s += 'Z'
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}
