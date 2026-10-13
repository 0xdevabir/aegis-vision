import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  login, clearToken, getToken, fetchAlerts, fetchSystemStatus,
  fetchKnownPersons, fetchEvidence, fetchMapCameras, fetchMapEvents,
  fetchIncidentReport, fetchCameras, fetchAnalyticsSummary,
  fetchAnalyticsTrends, fetchAnalyticsLocations, fetchVehiclePlates,
  fetchVehicleDetections, fetchAuditLogs, fetchMe, fetchStreamingCameras,
  fetchReviewCount, acknowledgeAlert, refreshSession,
} from './services/api'
import { useToast } from './components/Toast'
import { ProfileModal } from './components/ProfileModal'
import { parseTs } from './lib/time'
import { useWebSocket } from './hooks/useWebSocket'
import { useAutoAlerts } from './hooks/useAutoAlerts'
import { can, canViewPage } from './lib/permissions'
import { buildCamList } from './lib/cameras'
import { Card, Empty, Icons, Pill } from './components/ui'
import { CommandPalette } from './components/CommandPalette'
import { NotificationDrawer } from './components/NotificationDrawer'
import { Copilot } from './components/Copilot'
import { AccountMenu, AskBar, CameraPanel, Clock, ResponsePanel } from './components/Workspace'
import { CriticalAlertBanner } from './components/CriticalAlertBanner'
import { Overview } from './pages/Overview'
import { LiveMonitoring } from './pages/LiveMonitoring'
import { MapPage } from './pages/MapPage'
import { DetectionCenter } from './pages/DetectionCenter'
import { Triage } from './pages/Triage'
import { Incidents } from './pages/Incidents'
import { Cameras } from './pages/Cameras'
import { Analytics } from './pages/Analytics'
import { EvidencePage } from './pages/EvidencePage'
import { Watchlist } from './pages/Watchlist'
import { FaceRegistryPage } from './pages/FaceRegistryPage'
import { Vehicles } from './pages/Vehicles'
import { Reports } from './pages/Reports'
import { Users } from './pages/Users'
import { Settings } from './pages/Settings'
import { ZoneEditor } from './pages/ZoneEditor'

// Names are what an operator would call the page; `desc` is the one line shown under its title.
const NAV = [
  {
    group: 'Watch',
    pages: [
      { id: 'overview', label: 'Home', desc: 'What needs you right now, and how the system is doing.', icon: Icons.overview },
      { id: 'live', label: 'Live cameras', desc: 'Watch every camera as it happens.', icon: Icons.live },
      { id: 'map', label: 'Map', desc: 'Where your cameras are and where alerts came from.', icon: Icons.map },
    ],
  },
  {
    group: 'Respond',
    pages: [
      { id: 'alerts', label: 'Alerts', desc: 'Go through alerts one at a time and decide what happens next.', icon: Icons.alert },
      { id: 'incidents', label: 'Incidents', desc: 'Cases opened from alerts, and where each one stands.', icon: Icons.incident },
      { id: 'evidence', label: 'Evidence', desc: 'Snapshots and clips saved from detections.', icon: Icons.evidence },
    ],
  },
  {
    group: 'Investigate',
    pages: [
      { id: 'detection', label: 'Detection history', desc: 'Everything the cameras have detected, newest first.', icon: Icons.ai },
      { id: 'faces', label: 'Faces', desc: 'People the system can recognise.', icon: Icons.users },
      { id: 'watchlist', label: 'Watchlist', desc: 'People who raise an alert when a camera sees them.', icon: Icons.watchlist },
      { id: 'vehicles', label: 'Vehicles', desc: 'Number plates read by the cameras.', icon: Icons.vehicle },
      { id: 'analytics', label: 'Analytics', desc: 'Trends in detections over time and by place.', icon: Icons.chart },
      { id: 'reports', label: 'Reports', desc: 'Summaries you can print or export.', icon: Icons.report },
    ],
  },
  {
    group: 'Set up',
    pages: [
      { id: 'cameras', label: 'Cameras', desc: 'Add cameras and check that each one is streaming.', icon: Icons.camera },
      { id: 'zones', label: 'Zones', desc: 'Draw the areas and lines each camera should watch.', icon: Icons.zone },
      { id: 'users', label: 'Users', desc: 'Who can sign in and what they are allowed to do.', icon: Icons.users },
      { id: 'settings', label: 'Settings', desc: 'Detection, notification and system options.', icon: Icons.settings },
    ],
  },
]
const ALL_PAGES = NAV.flatMap((g) => g.pages)
// The pages used every shift: tabs over the centre panel, and the phone tab bar.
const TAB_PAGES = ['overview', 'live', 'alerts', 'map'].map((id) => ALL_PAGES.find((p) => p.id === id))
// Response panel tiles. The colour only tells the tiles apart; it carries no severity.
const TOOLS = [
  ['incidents', 'orange'], ['evidence', 'cyan'], ['faces', 'purple'], ['watchlist', 'danger'],
  ['vehicles', 'warn'], ['detection', 'primary'], ['analytics', 'ok'], ['reports', 'text-2'],
].map(([id, tone]) => ({ ...ALL_PAGES.find((p) => p.id === id), tone }))
const THREAT = {
  low: { tone: 'ok', label: 'Threat level low' },
  high: { tone: 'warn', label: 'Threat level elevated' },
  critical: { tone: 'danger', label: 'Threat level critical' },
}

function pageFromHash() {
  const id = (window.location.hash || '#/overview').replace('#/', '').split('?')[0]
  return ALL_PAGES.some((p) => p.id === id) ? id : 'overview'
}

function normalizeTheme(t) {
  return t === 'light' ? 'light' : 'dark'
}

function applyTheme(t) {
  const theme = normalizeTheme(t)
  document.documentElement.setAttribute('data-theme', theme)
  document.documentElement.style.colorScheme = theme
  try { localStorage.setItem('ai_sss_theme', theme) } catch { /* ignore */ }
  return theme
}

const PAGE_COMPONENTS = {
  overview: Overview, live: LiveMonitoring, map: MapPage, detection: DetectionCenter,
  alerts: Triage, incidents: Incidents, evidence: EvidencePage,
  faces: FaceRegistryPage, watchlist: Watchlist, vehicles: Vehicles, analytics: Analytics, reports: Reports,
  cameras: Cameras, zones: ZoneEditor, users: Users, settings: Settings,
}

function formatEvent(evt) {
  const type = evt.alert_type || evt.event_type || 'EVENT'
  const msg = evt.message || evt.person_name || evt.data?.criminal_name || type.replace(/_/g, ' ')
  return {
    id: evt.alert_id ?? evt.id ?? null,
    acknowledged: evt.acknowledged ?? false,
    dismissed: evt.dismissed ?? false,
    type, msg,
    severity: evt.severity || 'info',
    time: evt.timestamp,
    camera: evt.camera_location || evt.camera_id,
    cameraId: evt.camera_id,
    cameraName: evt.camera_name || evt.data?.camera_name,
    personName: evt.person_name,
    lat: evt.camera_lat ?? evt.data?.camera_lat,
    lng: evt.camera_lng ?? evt.data?.camera_lng,
    mapsUrl: evt.maps_url ?? evt.data?.maps_url,
    assignedOfficers: evt.assigned_officers ?? evt.data?.assigned_officers ?? [],
  }
}

// Local dev only: credentials come from frontend/.env.development.local (gitignored, never loaded by `vite build`).
const DEMO_LOGIN = import.meta.env.DEV && import.meta.env.VITE_DEMO_USERNAME && import.meta.env.VITE_DEMO_PASSWORD
  ? { username: import.meta.env.VITE_DEMO_USERNAME, password: import.meta.env.VITE_DEMO_PASSWORD }
  : null

function LoginForm({ onLogin, theme, setTheme, notice }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(notice || '')
  const [loading, setLoading] = useState(false)

  const signIn = async (user, pass) => {
    setLoading(true); setError('')
    try {
      await onLogin(user, pass)
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    signIn(username, password)
  }

  return (
    <div className="login-screen">
      <button
        type="button"
        className="icon-btn login-theme-btn"
        title="Toggle theme"
        aria-label="Toggle theme"
        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      >
        {theme === 'dark' ? <Icons.sun /> : <Icons.moon />}
      </button>
      <form className="login-card" onSubmit={handleSubmit}>
        <span className="brand-logo" aria-hidden="true">
          <img src="/logo.svg" alt="" width="46" height="46" />
        </span>
        <h1>Sign in to Aegis</h1>
        <p className="login-sub">Your cameras, alerts and evidence in one place.</p>
        {error && <div className="login-error" role="alert">{error}</div>}
        <label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
        <button type="submit" className="btn btn-primary" disabled={loading || !username || !password}>{loading ? 'Signing in…' : 'Sign in'}</button>
        {DEMO_LOGIN && (
          <button type="button" className="btn login-demo-btn" disabled={loading} onClick={() => signIn(DEMO_LOGIN.username, DEMO_LOGIN.password)}>Use the demo account</button>
        )}
      </form>
    </div>
  )
}

function App() {
  const { push: toast } = useToast()
  const [authed, setAuthed] = useState(!!getToken())
  const [sessionNotice, setSessionNotice] = useState('')
  const [page, setPageState] = useState(pageFromHash())
  const setPage = (id) => {
    setPageState(id)
    window.history.pushState(null, '', `#/${id}`)
  }
  const [theme, setThemeState] = useState(() => {
    try {
      return applyTheme(localStorage.getItem('ai_sss_theme') || 'dark')
    } catch {
      return applyTheme('dark')
    }
  })

  const [events, setEvents] = useState([])
  const [systemStatus, setSystemStatus] = useState(null)

  const [clearedAt, setClearedAt] = useState(0)
  const [nowTick, setNowTick] = useState(() => Date.now())   // re-evaluates the 15-min window
  const [reviewPending, setReviewPending] = useState(0)
  const [knownPersons, setKnownPersons] = useState([])
  const [evidence, setEvidence] = useState([])
  const reloadKnownPersons = useCallback(
    () => fetchKnownPersons().then(setKnownPersons).catch(() => {}), [])
  const [mapCameras, setMapCameras] = useState([])
  const [mapEvents, setMapEvents] = useState([])
  const [cameras, setCameras] = useState([])
  const [report, setReport] = useState(null)
  const [summary, setSummary] = useState(null)
  const [trends, setTrends] = useState([])
  const [locations, setLocations] = useState([])
  const [plates, setPlates] = useState([])
  const [vehicleDetections, setVehicleDetections] = useState([])
  const [auditLogs, setAuditLogs] = useState([])
  const [me, setMe] = useState(null)
  const [streamingCams, setStreamingCams] = useState([])

  const [showPalette, setShowPalette] = useState(false)
  const [showProfile, setShowProfile] = useState(false)
  const [mapFocus, setMapFocus] = useState(null)      // {cameraId, lat, lng, t}: which camera the map should show
  const [showNotifs, setShowNotifs] = useState(false)
  const [showCopilot, setShowCopilot] = useState(false)
  const [askQuery, setAskQuery] = useState('')        // question typed in the Home ask bar
  const [showAccount, setShowAccount] = useState(false)
  const [liveFocus, setLiveFocus] = useState(null)    // {cameraId, t}: camera picked in the cameras panel
  // Side panels: open where there is room, then whatever the operator last chose.
  const [panels, setPanels] = useState(() => {
    const roomy = { left: window.innerWidth >= 1360, right: window.innerWidth >= 1100 }
    try { return { ...roomy, ...JSON.parse(localStorage.getItem('aegis_panels') || '{}') } } catch { return roomy }
  })
  const togglePanel = (side) => {
    const next = { ...panels, [side]: !panels[side] }
    setPanels(next)
    try { localStorage.setItem('aegis_panels', JSON.stringify(next)) } catch { /* ignore */ }
  }
  // One card per (type, camera, person): two cameras alerting at once must both stay on screen.
  const [criticalAlerts, setCriticalAlerts] = useState([])
  const alertKey = (a) => `${a.type}|${a.cameraId ?? a.camera}|${a.personName ?? ''}`
  const dropCritical = (key) => setCriticalAlerts((list) => list.filter((a) => alertKey(a) !== key))

  const setTheme = (t) => {
    setThemeState(applyTheme(t))
  }
  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  useEffect(() => {
    const onHash = () => { setPageState(pageFromHash()) }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    const onAuthExpired = () => {
      clearToken()
      setSessionNotice('Your session expired. Please sign in again.')
      setAuthed(false)
    }
    window.addEventListener('auth_expired', onAuthExpired)
    return () => window.removeEventListener('auth_expired', onAuthExpired)
  }, [])

  const { handleAlert: handleAutoAlert } = useAutoAlerts((alert) => {
    setCriticalAlerts((list) => [alert, ...list.filter((a) => alertKey(a) !== alertKey(alert))].slice(0, 4))
    // If the operator is already looking at the map, take them to the camera that raised the alert.
    if (page === 'map' && alert.lat != null && alert.lng != null) {
      setMapFocus({ cameraId: alert.cameraId, lat: alert.lat, lng: alert.lng, t: Date.now() })
    }
  })

  const [captureEvent, setCaptureEvent] = useState(null)   // newest capture-basket still
  const handleWsMessage = useCallback((data) => {
    if (data.alert_type === 'PIPELINE_HEARTBEAT') return
    // A still for the capture basket, not an alert: it must not ring or fill the event feed.
    if (data.alert_type === 'ALERT_CAPTURE') { if (data.capture) setCaptureEvent(data.capture); return }
    const formatted = formatEvent(data)
    setEvents((prev) => [formatted, ...prev].slice(0, 200))
    // A police officer is only paged for cameras assigned to them (unassigned alerts reach everyone).
    const assigned = data.assigned_officers || data.data?.assigned_officers || []
    if (me?.role === 'police' && assigned.length && !assigned.some((o) => o.id === me.id)) return
    handleAutoAlert(data)
  }, [handleAutoAlert, me])

  const { connected: wsConnected } = useWebSocket('alerts', handleWsMessage, authed)
  const { connected: statusWsConnected } = useWebSocket('status', () => {}, authed)

  const reloadVehicles = useCallback(() => {
    fetchVehiclePlates().then(setPlates).catch(() => {})
    fetchVehicleDetections().then(setVehicleDetections).catch(() => {})
  }, [])

  /* Keep the session alive while the dashboard is open (a wall display must not log itself out) */
  useEffect(() => {
    if (!authed) return undefined
    refreshSession()
    const t = setInterval(refreshSession, 15 * 60 * 1000)
    const onVisible = () => { if (document.visibilityState === 'visible') refreshSession() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', onVisible) }
  }, [authed])

  /* Initial data load + status polling */
  const [loadFailed, setLoadFailed] = useState([])       // labels of preload requests that failed
  const [apiDown, setApiDown] = useState(false)          // status polling failed repeatedly
  const [reloadTick, setReloadTick] = useState(0)

  useEffect(() => {
    if (!authed) return undefined
    const failed = new Set()
    const load = (label, promise, apply) => promise.then(apply).catch(() => {
      failed.add(label)
      setLoadFailed([...failed])
    })
    load('alerts', fetchAlerts(50), (alerts) => setEvents(alerts.map((a) => formatEvent(a))))
    load('profile', fetchMe(), setMe)
    load('cameras', fetchCameras(), setCameras)
    load('map cameras', fetchMapCameras(), setMapCameras)
    load('map events', fetchMapEvents(24), setMapEvents)
    load('persons', fetchKnownPersons(), setKnownPersons)
    load('evidence', fetchEvidence(60), setEvidence)
    load('summary', fetchAnalyticsSummary(24), setSummary)
    load('trends', fetchAnalyticsTrends(7), setTrends)
    load('locations', fetchAnalyticsLocations(24), setLocations)
    load('report', fetchIncidentReport(24), setReport)
    load('audit log', fetchAuditLogs(50), setAuditLogs)
    reloadVehicles()

    let misses = 0
    const poll = () => {
      fetchSystemStatus().then((s) => { misses = 0; setApiDown(false); setSystemStatus(s) }).catch(() => {
        misses += 1
        if (misses >= 2) setApiDown(true)
      })
      fetchStreamingCameras().then((r) => setStreamingCams(r.cameras || [])).catch(() => {})
    }
    poll()
    const interval = setInterval(poll, 3000)
    return () => clearInterval(interval)
  }, [authed, reloadVehicles, reloadTick])

  /* Refresh page-specific data when navigating */
  useEffect(() => {
    if (!authed) return
    if (page === 'watchlist' || page === 'faces') fetchKnownPersons().then(setKnownPersons).catch(() => {})
    if (page === 'evidence' || page === 'watchlist' || page === 'faces') fetchEvidence(60).then(setEvidence).catch(() => {})
    if (page === 'map') {
      fetchMapCameras().then(setMapCameras).catch(() => {})
      fetchMapEvents(24).then(setMapEvents).catch(() => {})
    }
    if (page === 'analytics' || page === 'overview') {
      fetchAnalyticsSummary(24).then(setSummary).catch(() => {})
      fetchAnalyticsTrends(7).then(setTrends).catch(() => {})
      fetchAnalyticsLocations(24).then(setLocations).catch(() => {})
    }
    if (page === 'cameras') fetchCameras().then(setCameras).catch(() => {})
    if (page === 'vehicles') reloadVehicles()
    if (page === 'users') fetchAuditLogs(50).then(setAuditLogs).catch(() => {})
    if (page === 'reports') fetchIncidentReport(24).then(setReport).catch(() => {})
  }, [authed, page, reloadVehicles])

  /* Keyboard shortcuts */
  useEffect(() => {
    const onKey = (e) => {
      // Never hijack typing: plain-letter shortcuts must not fire inside form fields.
      const t = e.target
      const typing = t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)
      if (typing && !((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') && e.key !== 'Escape') return
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setShowPalette((v) => !v)
      } else if (e.key.toLowerCase() === 'n' && !e.metaKey && !e.ctrlKey) {
        setShowNotifs((v) => !v)
      } else if (e.key.toLowerCase() === 'c' && !e.metaKey && !e.ctrlKey) {
        setShowCopilot((v) => !v)
      } else if (e.key === 'Escape') {
        setShowPalette(false); setShowNotifs(false); setShowCopilot(false); setShowAccount(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    const t = setInterval(() => setNowTick(Date.now()), 30000)
    return () => clearInterval(t)
  }, [])

  const refreshReviewCount = useCallback(() => {
    fetchReviewCount().then((r) => setReviewPending(r.pending || 0)).catch(() => {})
  }, [])

  useEffect(() => {
    if (!authed) return undefined
    refreshReviewCount()
    const t = setInterval(refreshReviewCount, 15000)
    return () => clearInterval(t)
  }, [authed, refreshReviewCount])

  const reloadCameras = useCallback(() => {
    fetchCameras().then(setCameras).catch(() => {})
  }, [])

  const camList = useMemo(() => buildCamList(cameras, systemStatus, streamingCams), [cameras, systemStatus, streamingCams])

  /* Page grids follow the centre panel's width (see .center[data-w] in index.css). */
  const centerRef = useRef(null)
  useEffect(() => {
    const el = centerRef.current
    if (!el) return undefined
    const ro = new ResizeObserver(([entry]) => {
      const w = entry.contentRect.width
      el.dataset.w = w < 700 ? 'sm' : w < 1040 ? 'md' : 'lg'
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [authed])

  /* Threat level is derived, so it falls back by itself once alerts are handled:
     unhandled alerts from the last 15 minutes, or a hot camera score from the pipeline. */
  const threatLevel = useMemo(() => {
    const cutoff = Math.max(nowTick - 15 * 60 * 1000, clearedAt)
    const live = events.filter((e) => {
      const t = parseTs(e.time)?.getTime() || 0
      return t >= cutoff && !e.acknowledged && !e.dismissed
    })
    const maxScore = Math.max(0, ...Object.values(systemStatus?.cameras || {}).map((c) => c.threat_score || 0))
    if (live.some((e) => e.severity === 'critical') || maxScore >= 50) return 'critical'
    if (live.some((e) => e.severity === 'high') || maxScore >= 20) return 'high'
    return 'low'
  }, [events, systemStatus, clearedAt, nowTick])

  if (!authed) {
    return (
      <LoginForm
        theme={theme}
        setTheme={setTheme}
        notice={sessionNotice}
        onLogin={async (u, p) => { await login(u, p); setSessionNotice(''); setAuthed(true) }}
      />
    )
  }

  const ackCritical = async (alert) => {
    try {
      await acknowledgeAlert(alert.alertId)
      dropCritical(alertKey(alert))
    } catch (e) {
      toast(e.message || 'Could not acknowledge', 'danger')
    }
  }

  const criticalEvents = events.filter((e) => e.severity === 'critical' && !e.acknowledged && !e.dismissed)
  const pipelineOnline = systemStatus?.online
  const activePage = ALL_PAGES.find((p) => p.id === page)
  const PageComponent = PAGE_COMPONENTS[page] || Overview
  const alertCount = reviewPending || criticalEvents.length
  const allowed = !me || canViewPage(me.role, page)
  // While the profile loads (role unknown) show no tabs instead of flashing the admin set.
  const tabPages = TAB_PAGES.filter((p) => canViewPage(me?.role, p.id))

  const ctx = {
    events, setEvents, systemStatus, threatLevel, wsConnected,
    knownPersons, reloadKnownPersons, evidence, mapCameras, mapEvents, cameras,
    report, summary, trends, locations,
    plates, vehicleDetections, auditLogs, reloadVehicles,
    me, streamingCams, reloadCameras, setPage, mapFocus, liveFocus,
    reviewPending, refreshReviewCount, captureEvent,
    theme, setTheme,
  }

  return (
    <div className={`shell ${threatLevel === 'critical' ? 'threat-critical' : ''}`}>
      {criticalAlerts.length > 0 && (
        <div className="critical-stack">
          {criticalAlerts.map((a, i) => (
            <CriticalAlertBanner key={alertKey(a)} alert={a} repeatSound={i === 0}
              onDismiss={() => dropCritical(alertKey(a))} onViewMap={() => {
                setMapFocus({ cameraId: a.cameraId, lat: a.lat, lng: a.lng, t: Date.now() })
                setPage('map'); dropCritical(alertKey(a))
              }} onOpenAlerts={() => { setPage('alerts'); dropCritical(alertKey(a)) }}
              onAcknowledge={() => ackCritical(a)} />
          ))}
        </div>
      )}
      <header className="appbar">
        <div className="brand">
          <span className="brand-logo" aria-hidden="true">
            <img src="/logo.svg" alt="" width="34" height="34" />
          </span>
          <div>Aegis<small>Surveillance operations</small></div>
        </div>
        <div className="appbar-right">
          <div className="status-rail" aria-label="System status">
            <Pill tone={THREAT[threatLevel].tone}>{THREAT[threatLevel].label}</Pill>
            <Pill tone={pipelineOnline ? 'ok' : 'warn'}>{pipelineOnline ? 'Detection on' : 'Detection off'}</Pill>
            <Pill tone={wsConnected && statusWsConnected ? 'ok' : 'danger'}>
              {wsConnected && statusWsConnected ? 'Live' : 'Reconnecting…'}
            </Pill>
          </div>
          <Clock />
          <button
            type="button"
            className="searchbox"
            onClick={() => setShowPalette(true)}
            aria-label="Search pages and actions"
          >
            <Icons.search />
            <span>Search</span>
            <kbd>⌘K</kbd>
          </button>
          <div className="row" style={{ gap: 2 }}>
            <button type="button" className="icon-btn" title="Ask the assistant" aria-label="Ask the assistant" onClick={() => setShowCopilot(true)}><Icons.bot /></button>
            <button type="button" className="icon-btn has-badge" title="Notifications" aria-label="Notifications" onClick={() => setShowNotifs(true)}>
              <Icons.bell />
              {criticalEvents.length > 0 && <span className="nav-badge">{criticalEvents.length}</span>}
            </button>
            <button
              type="button"
              className="icon-btn"
              title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
              aria-label="Toggle theme"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            >
              {theme === 'dark' ? <Icons.sun /> : <Icons.moon />}
            </button>
          </div>
          <AccountMenu
            me={me} open={showAccount} setOpen={setShowAccount}
            items={[
              { label: 'My account', icon: Icons.users, run: () => setShowProfile(true) },
              ...['users', 'settings'].filter((id) => canViewPage(me?.role, id)).map((id) => {
                const p = ALL_PAGES.find((x) => x.id === id)
                return { label: p.label, icon: p.icon, run: () => setPage(id) }
              }),
            ]}
            onSignOut={() => { clearToken(); setAuthed(false) }}
          />
        </div>
      </header>

      <div className="workspace">
        <CameraPanel
          camList={camList} open={panels.left} onToggle={() => togglePanel('left')}
          canManage={can(me?.role, 'camera.manage')} canZones={canViewPage(me?.role, 'zones')} hasMap={canViewPage(me?.role, 'map')}
          onOpenCamera={canViewPage(me?.role, 'live') ? (c) => { setLiveFocus({ cameraId: c.camera_id, t: Date.now() }); setPage('live') } : null}
          onLocate={(c) => {
            const at = mapCameras.find((m) => m.camera_id === c.camera_id)
            setMapFocus({ cameraId: c.camera_id, lat: at?.lat, lng: at?.lng, t: Date.now() })
            setPage('map')
          }}
          setPage={setPage}
        />

        <main className={`panel center ${page === 'overview' ? 'has-ask' : ''}`} ref={centerRef}>
          <nav className="center-head" aria-label="Views">
            {tabPages.map((p) => {
              const Icon = p.icon
              return (
                <button
                  key={p.id}
                  type="button"
                  className={`view-tab ${page === p.id ? 'active' : ''}`}
                  aria-current={page === p.id ? 'page' : undefined}
                  data-alert-nav={p.id === 'alerts' && criticalEvents.length > 0 ? 'true' : undefined}
                  onClick={() => setPage(p.id)}
                >
                  <Icon />
                  {p.label}
                  {p.id === 'alerts' && alertCount > 0 && (
                    <span className="nav-badge" aria-label={`${alertCount} need attention`}>{alertCount}</span>
                  )}
                </button>
              )
            })}
            {/* A page opened from a side panel shows as one more tab, so you can see where you are. */}
            {activePage && !tabPages.includes(activePage) && (
              <>
                <span className="view-sep" aria-hidden="true" />
                <span className="view-tab active" aria-current="page"><activePage.icon />{activePage.label}</span>
              </>
            )}
          </nav>

          <div className="page" key={page}>
            {(apiDown || loadFailed.length > 0) && (
              <div className="conn-banner" role="status">
                <span>
                  {apiDown
                    ? 'Cannot reach the server. Showing the last data received and retrying.'
                    : `Some data could not be loaded (${loadFailed.join(', ')}).`}
                </span>
                <button className="btn btn-sm" onClick={() => { setLoadFailed([]); setReloadTick((t) => t + 1) }}>Retry now</button>
              </div>
            )}
            <div className="page-view">
              {allowed ? (
                <>
                  <div className="page-title">
                    <h1>{activePage?.label}</h1>
                    <p>{activePage?.desc}</p>
                  </div>
                  <PageComponent ctx={ctx} />
                </>
              ) : (
                <Card title="You don't have access to this page" sub={`The ${me.role} role cannot open it`}>
                  <Empty icon={Icons.shield}>Ask an administrator if you need access.</Empty>
                </Card>
              )}
            </div>
          </div>

          {page === 'overview' && (
            <AskBar liveCount={camList.filter((c) => c.status === 'live').length} onAsk={(q) => { setAskQuery(q); setShowCopilot(true) }} />
          )}

          <nav className="tabbar" aria-label="Main">
            {tabPages.map((p) => {
              const Icon = p.icon
              return (
                <button
                  key={p.id}
                  type="button"
                  className={`tab ${page === p.id ? 'active' : ''}`}
                  aria-current={page === p.id ? 'page' : undefined}
                  data-alert-nav={p.id === 'alerts' && criticalEvents.length > 0 ? 'true' : undefined}
                  onClick={() => setPage(p.id)}
                >
                  <Icon />
                  {p.label.split(' ')[0]}
                  {p.id === 'alerts' && alertCount > 0 && <span className="nav-badge">{alertCount}</span>}
                </button>
              )
            })}
            <button type="button" className="tab" onClick={() => setShowPalette(true)}>
              <Icons.menu />
              More
            </button>
          </nav>
        </main>

        <ResponsePanel
          tools={TOOLS.filter((t) => canViewPage(me?.role, t.id))} page={page} setPage={setPage}
          feed={events.filter((e) => !e.acknowledged && !e.dismissed)} alertCount={alertCount}
          open={panels.right} onToggle={() => togglePanel('right')}
        />
      </div>

      {showPalette && (
        <CommandPalette
          pages={ALL_PAGES.filter((p) => canViewPage(me?.role, p.id))}
          actions={[
            { id: 'act-theme', label: `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`, icon: theme === 'dark' ? Icons.sun : Icons.moon, hint: 'Action', run: () => setTheme(theme === 'dark' ? 'light' : 'dark') },
            { id: 'act-copilot', label: 'Ask the assistant', icon: Icons.bot, hint: 'Action', run: () => setShowCopilot(true) },
            { id: 'act-notifs', label: 'Open notifications', icon: Icons.bell, hint: 'Action', run: () => setShowNotifs(true) },
            { id: 'act-profile', label: 'Change my password', icon: Icons.users, hint: 'Action', run: () => setShowProfile(true) },
            { id: 'act-logout', label: 'Sign out', icon: Icons.logout, hint: 'Action', run: () => { clearToken(); setAuthed(false) } },
          ]}
          onNavigate={setPage}
          onClose={() => setShowPalette(false)}
        />
      )}
      {showProfile && <ProfileModal me={me} onClose={() => setShowProfile(false)} />}
      {showNotifs && (
        <NotificationDrawer events={events} onClose={() => setShowNotifs(false)} onClear={() => { setEvents([]); setClearedAt(Date.now()) }} />
      )}
      {showCopilot && (
        <Copilot ctx={{ events, summary, cameras, threatLevel, locations }} initialQuery={askQuery} onClose={() => { setShowCopilot(false); setAskQuery('') }} />
      )}
    </div>
  )
}

export default App


