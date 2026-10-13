// One place that says what each role may see and do. The backend still enforces every rule;
// this keeps the UI honest (no buttons that only fail after a click).

export const ROLE_PAGES = {
  viewer: new Set(['overview', 'live', 'map', 'alerts']),
  operator: new Set(['overview', 'live', 'map', 'detection', 'alerts', 'incidents', 'evidence', 'faces', 'analytics', 'reports', 'cameras']),
  police: new Set(['overview', 'live', 'map', 'alerts', 'incidents']),
  investigator: new Set(['overview', 'alerts', 'incidents', 'evidence', 'faces', 'watchlist', 'vehicles', 'analytics', 'reports']),
  supervisor: null,   // null = every page
  admin: null,
}

const ACTIONS = {
  'camera.manage': ['admin'],
  'ptz': ['operator', 'supervisor', 'admin', 'police'],
  'triage.act': ['operator', 'supervisor', 'admin', 'police', 'investigator'],
  'incident.edit': ['operator', 'supervisor', 'admin', 'police', 'investigator'],
  'evidence.label': ['operator', 'supervisor', 'admin', 'investigator'],
  'vehicle.edit': ['operator', 'supervisor', 'admin'],
  'user.manage': ['admin'],
}

export function canViewPage(role, pageId) {
  if (!role) return false
  const allowed = ROLE_PAGES[role]
  return allowed === undefined ? false : allowed === null || allowed.has(pageId)
}

export function can(role, action) {
  return !!role && (ACTIONS[action] || []).includes(role)
}
