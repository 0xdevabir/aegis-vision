const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

export function getToken() {
  return localStorage.getItem('ai_sss_token');
}

export function setToken(token) {
  localStorage.setItem('ai_sss_token', token);
}

export function clearToken() {
  localStorage.removeItem('ai_sss_token');
}

async function apiFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body && !headers['Content-Type'] && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    if (res.status === 401 && !path.includes('/auth/login')) {
      // Dispatch auth_expired event instead of abruptly reloading
      window.dispatchEvent(new Event('auth_expired'));
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const d = err.detail;
    throw new Error((typeof d === 'object' && d ? d.message : d) || 'Request failed');
  }
  return res.json();
}

export async function login(username, password) {
  const data = await apiFetch('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  setToken(data.access_token);
  return data;
}

/** Swap the current token for a fresh one. Ignored if it fails: the next real request reports expiry. */
export async function refreshSession() {
  try {
    const data = await apiFetch('/auth/refresh', { method: 'POST' });
    setToken(data.access_token);
  } catch { /* handled by the 401 flow */ }
}

export async function fetchAlerts(limit = 20) {
  return apiFetch(`/alerts/?limit=${limit}`);
}

export async function fetchAlertsFiltered({ reviewStatus, dismissed, acknowledged, limit = 100 } = {}) {
  const q = new URLSearchParams({ limit });
  if (reviewStatus) q.set('review_status', reviewStatus);
  if (dismissed !== undefined) q.set('dismissed', dismissed);
  if (acknowledged !== undefined) q.set('acknowledged', acknowledged);
  return apiFetch(`/alerts/?${q}`);
}

export async function fetchAlertContext(alertId) {
  return apiFetch(`/alerts/${alertId}/context`);
}

export async function fetchReviewCount() {
  return apiFetch('/alerts/review-queue-count');
}

export async function searchEvents({ since, until, eventTypes, cameraId, limit = 500 } = {}) {
  const q = new URLSearchParams({ limit });
  if (since) q.set('since', since);
  if (until) q.set('until', until);
  if (eventTypes) q.set('event_types', eventTypes);
  if (cameraId) q.set('camera_id', cameraId);
  return apiFetch(`/events/search?${q}`);
}

export async function fetchThresholdSpecs() {
  return apiFetch('/config/thresholds/specs');
}

export async function fetchSystemStatus() {
  return apiFetch('/system/status');
}

export async function fetchCameras() {
  return apiFetch('/cameras/');
}

export async function resolveIp(url) {
  return apiFetch(`/cameras/resolve-ip?url=${encodeURIComponent(url)}`);
}

export async function addCamera(data) {
  return apiFetch('/cameras/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateCamera(cameraId, patch) {
  return apiFetch(`/cameras/${cameraId}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export async function fetchKnownPersons() {
  return apiFetch('/faces/known-persons');
}

export function personImageUrl(imageId) {
  const token = getToken();
  return `${API_BASE}/faces/images/${imageId}${token ? `?token=${encodeURIComponent(token)}` : ''}`;
}

export async function enrollPerson({ name, category, criminalStatus, threatLevel, notes, files }) {
  const fd = new FormData();
  fd.append('name', name);
  fd.append('category', category);
  fd.append('criminal_status', criminalStatus);
  fd.append('threat_level', String(threatLevel));
  if (notes) fd.append('notes', notes);
  files.forEach((f) => fd.append('files', f));
  return apiFetch('/faces/persons', { method: 'POST', body: fd });
}

export async function addPersonImages(personId, files) {
  const fd = new FormData();
  files.forEach((f) => fd.append('files', f));
  return apiFetch(`/faces/persons/${encodeURIComponent(personId)}/images`, { method: 'POST', body: fd });
}

export async function fetchPersonDetail(personId) {
  return apiFetch(`/faces/persons/${encodeURIComponent(personId)}`);
}

export async function updatePerson(personId, patch) {
  return apiFetch(`/faces/persons/${encodeURIComponent(personId)}`, { method: 'PATCH', body: JSON.stringify(patch) });
}

export async function deletePerson(personId) {
  return apiFetch(`/faces/persons/${encodeURIComponent(personId)}`, { method: 'DELETE' });
}

export async function deletePersonImage(imageId) {
  return apiFetch(`/faces/images/${imageId}`, { method: 'DELETE' });
}

export async function verifyFace(file, personId) {
  const fd = new FormData();
  fd.append('file', file);
  if (personId) fd.append('person_id', personId);
  return apiFetch('/faces/verify', { method: 'POST', body: fd });
}

export async function verifyEvidence(evidenceId) {
  return apiFetch(`/faces/verify-evidence/${evidenceId}`, { method: 'POST' });
}

export async function fetchFaceEncodings() {
  return apiFetch('/faces/');
}

export async function fetchEvidence(limit = 30) {
  return apiFetch(`/evidence/?limit=${limit}`);
}

export async function fetchMapCameras() {
  return apiFetch('/map/cameras');
}

export async function fetchMapEvents(hours = 24, types = '') {
  const q = new URLSearchParams({ hours: String(hours) });
  if (types) q.set('types', types);
  return apiFetch(`/map/events?${q}`);
}

export async function fetchIncidentReport(hours = 24) {
  return apiFetch(`/reports/incident?hours=${hours}`);
}

export async function fetchAnalyticsSummary(hours = 24) {
  return apiFetch(`/analytics/summary?hours=${hours}`);
}

export async function fetchAnalyticsTrends(days = 7) {
  return apiFetch(`/analytics/trends?days=${days}`);
}

export async function fetchAnalyticsLocations(hours = 24) {
  return apiFetch(`/analytics/locations?hours=${hours}`);
}

export async function fetchVehiclePlates(watchlistedOnly = false) {
  return apiFetch(`/vehicles/plates?watchlisted_only=${watchlistedOnly}`);
}

export async function addVehiclePlate(plateNumber, reason) {
  return apiFetch('/vehicles/plates', {
    method: 'POST',
    body: JSON.stringify({ plate_number: plateNumber, reason }),
  });
}

export async function fetchVehicleDetections(limit = 50) {
  return apiFetch(`/vehicles/detections?limit=${limit}`);
}

export async function fetchAuditLogs(limit = 100) {
  return apiFetch(`/audit/?limit=${limit}`);
}

export async function acknowledgeAlert(alertId, { acknowledged = true, dismissed = false, note = null } = {}) {
  return apiFetch(`/alerts/${alertId}/acknowledge`, {
    method: 'PUT',
    body: JSON.stringify({ acknowledged, dismissed, note }),
  });
}

export async function dispatchPolice(alertId) {
  return apiFetch(`/alerts/${alertId}/dispatch`, { method: 'POST' });
}

export async function fetchUsers() {
  return apiFetch('/auth/users');
}

export async function fetchCameraOfficerMap() {
  return apiFetch('/cameras/officers/all');
}

export async function setCameraOfficers(cameraId, userIds) {
  return apiFetch(`/cameras/${encodeURIComponent(cameraId)}/officers`, {
    method: 'PUT',
    body: JSON.stringify({ user_ids: userIds }),
  });
}

export async function createUser({ username, email, password, role, phone }) {
  return apiFetch('/auth/users', {
    method: 'POST',
    body: JSON.stringify({ username, email, password, role, phone: phone || null }),
  });
}

export async function updateUser(userId, patch) {
  return apiFetch(`/auth/users/${userId}`, { method: 'PATCH', body: JSON.stringify(patch) });
}

export async function changePassword(currentPassword, newPassword) {
  return apiFetch('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export async function fetchAssignees() {
  return apiFetch('/auth/assignees');
}

export async function fetchMe() {
  return apiFetch('/auth/me');
}

export async function fetchStreamingCameras() {
  const token = getToken();
  return apiFetch(`/stream/cameras${token ? `?token=${encodeURIComponent(token)}` : ''}`);
}

/* URL builders for <img> tags (JWT passed as query param — imgs can't send headers) */
export function liveStreamUrl(cameraId) {
  const token = getToken();
  return `${API_BASE}/stream/${encodeURIComponent(cameraId)}/live${token ? `?token=${encodeURIComponent(token)}` : ''}`;
}

export function snapshotUrl(cameraId) {
  const token = getToken();
  return `${API_BASE}/stream/${encodeURIComponent(cameraId)}/snapshot${token ? `?token=${encodeURIComponent(token)}` : ''}`;
}

export async function fetchCameraGeometry(cameraId) {
  return apiFetch(`/cameras/${encodeURIComponent(cameraId)}/geometry`);
}

export async function saveCameraGeometry(cameraId, { zones, lines }) {
  return apiFetch(`/cameras/${encodeURIComponent(cameraId)}/geometry`, {
    method: 'PUT',
    body: JSON.stringify({ zones, lines }),
  });
}

export function evidenceImageUrl(evidenceId, kind = 'frame') {
  const token = getToken();
  return `${API_BASE}/evidence/${evidenceId}/image?kind=${kind}${token ? `&token=${encodeURIComponent(token)}` : ''}`;
}

/* ---- Incidents ---- */
export async function fetchIncidents({ status, priority, limit = 50 } = {}) {
  const qs = new URLSearchParams({ limit: String(limit) });
  if (status) qs.set('status', status);
  if (priority) qs.set('priority', priority);
  return apiFetch(`/incidents/?${qs}`);
}
export async function fetchIncidentStats() {
  return apiFetch('/incidents/stats');
}
export async function fetchIncident(id) {
  return apiFetch(`/incidents/${id}`);
}
export async function updateIncident(id, patch) {
  return apiFetch(`/incidents/${id}`, { method: 'PUT', body: JSON.stringify(patch) });
}
export async function addIncidentNote(id, body) {
  return apiFetch(`/incidents/${id}/notes`, { method: 'POST', body: JSON.stringify({ body }) });
}
export async function createIncidentFromAlert(alertId) {
  return apiFetch(`/incidents/from-alert/${alertId}`, { method: 'POST' });
}
export async function createIncident(payload) {
  return apiFetch('/incidents/', { method: 'POST', body: JSON.stringify(payload) });
}

/* ---- Custody ---- */
export async function fetchCustody(evidenceId) {
  return apiFetch(`/custody/evidence/${evidenceId}`);
}
export async function verifyCustody(evidenceId) {
  return apiFetch(`/custody/evidence/${evidenceId}/verify`, { method: 'POST' });
}

/* ---- Recordings / timeline ---- */
export async function fetchRecordings({ cameraId, hours = 24 } = {}) {
  const qs = new URLSearchParams({ hours: String(hours) });
  if (cameraId) qs.set('camera_id', cameraId);
  return apiFetch(`/recordings/?${qs}`);
}
export async function fetchTimeline({ cameraId, hours = 24 } = {}) {
  const qs = new URLSearchParams({ hours: String(hours) });
  if (cameraId) qs.set('camera_id', cameraId);
  return apiFetch(`/recordings/timeline?${qs}`);
}
export function recordingFileUrl(clipId) {
  return `${API_BASE}/recordings/${clipId}/file`;
}

/* ---- Re-ID ---- */
export async function fetchReidPersons(hours = 24) {
  return apiFetch(`/reid/persons?hours=${hours}`);
}
export async function fetchReidVehicles(hours = 24) {
  return apiFetch(`/reid/vehicles?hours=${hours}`);
}

/* ---- Integrations ---- */
export async function fetchIntegrationStatus() {
  return apiFetch('/integrations/status');
}
export async function testIntegration(channel, message) {
  return apiFetch('/integrations/test', {
    method: 'POST',
    body: JSON.stringify({ channel, message }),
  });
}

/* ---- Calibration ---- */
export async function fetchCalibrationMetrics(hours = 168) {
  return apiFetch(`/calibration/metrics?hours=${hours}`);
}
export async function addCalibrationLabel(payload) {
  return apiFetch('/calibration/labels', { method: 'POST', body: JSON.stringify(payload) });
}

/* ---- Professional VMS ---- */
export async function fetchVmsStatus() {
  return apiFetch('/vms/status');
}
export async function fetchVmsTimeline({ cameraId, hours = 24, trigger } = {}) {
  const qs = new URLSearchParams({ hours: String(hours) });
  if (cameraId) qs.set('camera_id', cameraId);
  if (trigger) qs.set('trigger', trigger);
  return apiFetch(`/vms/timeline?${qs}`);
}
export async function fetchPtz(cameraId) {
  return apiFetch(`/vms/ptz/${encodeURIComponent(cameraId)}`);
}
export async function ptzMove(cameraId, { pan = 0, tilt = 0, zoom = 0 } = {}) {
  return apiFetch(`/vms/ptz/${encodeURIComponent(cameraId)}/move`, {
    method: 'POST', body: JSON.stringify({ pan, tilt, zoom }),
  });
}
export async function ptzStop(cameraId) {
  return apiFetch(`/vms/ptz/${encodeURIComponent(cameraId)}/stop`, { method: 'POST' });
}
export async function ptzHome(cameraId) {
  return apiFetch(`/vms/ptz/${encodeURIComponent(cameraId)}/home`, { method: 'POST' });
}
export async function ptzSetMode(cameraId, mode) {
  return apiFetch(`/vms/ptz/${encodeURIComponent(cameraId)}/mode`, {
    method: 'POST', body: JSON.stringify({ mode }),
  });
}
export async function ptzSavePreset(cameraId, name) {
  return apiFetch(`/vms/ptz/${encodeURIComponent(cameraId)}/presets`, {
    method: 'POST', body: JSON.stringify({ name }),
  });
}
export async function ptzGotoPreset(cameraId, name) {
  return apiFetch(`/vms/ptz/${encodeURIComponent(cameraId)}/presets/${encodeURIComponent(name)}/goto`, {
    method: 'POST',
  });
}
export function vmsPlaybackUrl(cameraId, isoTime) {
  const token = getToken();
  const qs = new URLSearchParams({ camera_id: cameraId, t: isoTime });
  if (token) qs.set('token', token);
  // playback uses Authorization header via fetch; this URL is for reference
  return `${API_BASE}/vms/playback?camera_id=${encodeURIComponent(cameraId)}&t=${encodeURIComponent(isoTime)}`;
}
export async function openVmsPlayback(cameraId, isoTime) {
  const token = getToken();
  const url = `${API_BASE}/vms/playback?camera_id=${encodeURIComponent(cameraId)}&t=${encodeURIComponent(isoTime)}`;
  const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new Error('No recording at this time');
  const blob = await res.blob();
  const seek = res.headers.get('X-Seek-Offset-Seconds');
  return { blobUrl: URL.createObjectURL(blob), seekOffset: seek ? Number(seek) : 0, segmentId: res.headers.get('X-Segment-Id') };
}

export function wsUrl(channel = 'alerts') {
  const base = import.meta.env.VITE_WS_URL
    || `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;
  const token = getToken();
  const qs = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${base}/api/v1/ws/${channel}${qs}`;
}




export async function fetchConfigThresholds() {
  return apiFetch('/config/thresholds/all');
}

export async function saveConfigThreshold(key, value) {
  return apiFetch(`/config/threshold.${key}`, {
    method: 'PUT',
    body: JSON.stringify({ value: String(value) }),
  });
}

export async function deleteCamera(cameraId) {
  return apiFetch(`/cameras/${encodeURIComponent(cameraId)}`, { method: 'DELETE' });
}

export async function deleteVehiclePlate(plate) {
  return apiFetch(`/vehicles/plates/${encodeURIComponent(plate)}`, { method: 'DELETE' });
}

export async function fetchLiveAnalytics() {
  return apiFetch('/analytics/live');
}

export async function fetchEvidenceBundle(hours = 24) {
  return apiFetch(`/reports/evidence-bundle?hours=${hours}`);
}
