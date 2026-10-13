import { useState, useEffect, useCallback, useMemo } from 'react'
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
import { canViewPage } from './lib/permissions'
import { Card, Empty, Icons, Pill } from './components/ui'
import { CommandPalette } from './components/CommandPalette'
import { NotificationDrawer } from './components/NotificationDrawer'
import { Copilot } from './components/Copilot'
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

const NAV = [
  {
    group: 'Operations',
    pages: [
      { id: 'overview', label: 'Executive Overview', icon: Icons.overview },
      { id: 'live', label: 'Live Monitoring', icon: Icons.live },
      { id: 'map', label: 'GIS Map', icon: Icons.map },
      { id: 'detection', label: 'AI Detection Center', icon: Icons.ai },
    ],
  },
  {
    group: 'Response',
    pages: [
      { id: 'alerts', label: 'Alert Triage', icon: Icons.alert },
      { id: 'incidents', label: 'Incidents', icon: Icons.incident },
      { id: 'evidence', label: 'Evidence Center', icon: Icons.evidence },
    ],
  },
  {
    group: 'Intelligence',
    pages: [
      { id: 'faces', label: 'Face Registry', icon: Icons.users },
      { id: 'watchlist', label: 'Watchlist', icon: Icons.watchlist },
      { id: 'vehicles', label: 'Vehicle Intelligence', icon: Icons.vehicle },
      { id: 'analytics', label: 'Analytics', icon: Icons.chart },
      { id: 'reports', label: 'Reports', icon: Icons.report },
    ],
  },
  {
    group: 'Administration',
    pages: [
      { id: 'cameras', label: 'Camera Management', icon: Icons.camera },
      { id: 'zones', label: 'Zones & Lines', icon: Icons.zone },
      { id: 'users', label: 'Users & Roles', icon: Icons.users },
      { id: 'settings', label: 'Settings', icon: Icons.settings },
    ],
  },
]
const ALL_PAGES = NAV.flatMap((g) => g.pages)

function filterNavByRole(role) {
  // While the profile loads (role unknown) show no navigation instead of flashing the admin menu.
  return NAV.map((g) => ({ ...g, pages: g.pages.filter((p) => canViewPage(role, p.id)) })).filter((g) => g.pages.length)
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

function LoginForm({ onLogin, theme, setTheme, notice }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(notice || '')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      await onLogin(username, password)
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setLoading(false)
    }
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
        <h1><span className="brand-logo">AG</span> Aegis Command Center</h1>
        <p className="login-sub">AI Smart Surveillance · threat detection · GPS dispatch</p>
        {error && <div className="login-error" role="alert">{error}</div>}
        <label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
        <button type="submit" className="btn btn-primary" disabled={loading || !username || !password}>{loading ? 'Signing in…' : 'Sign in'}</button>
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
  const [sidebarOpen, setSidebarOpen] = useState(false)

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
    const onHash = () => setPageState(pageFromHash())
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

  const handleWsMessage = useCallback((data) => {
    if (data.alert_type === 'PIPELINE_HEARTBEAT') return
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
        setShowPalette(false); setShowNotifs(false); setShowCopilot(false)
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



  const ctx = {
    events, setEvents, systemStatus, threatLevel, wsConnected,
    knownPersons, reloadKnownPersons, evidence, mapCameras, mapEvents, cameras,
    report, summary, trends, locations,
    plates, vehicleDetections, auditLogs, reloadVehicles,
    me, streamingCams, reloadCameras, setPage, mapFocus,
    reviewPending, refreshReviewCount,
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
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="brand">
          <span className="brand-logo">AG</span>
          <div>Aegis<small>COMMAND CENTER</small></div>
        </div>
        <div className="nav-scroll">
          {filterNavByRole(me?.role).map((group) => (
            <div className="nav-group" key={group.group}>
              <div className="nav-group-label">{group.group}</div>
              {group.pages.map((p) => {
                const Icon = p.icon
                return (
                  <button
                    key={p.id}
                    type="button"
                    className={`nav-item ${page === p.id ? 'active' : ''}`}
                    aria-current={page === p.id ? 'page' : undefined}
                    data-alert-nav={p.id === 'alerts' && criticalEvents.length > 0 ? 'true' : undefined}
                    onClick={() => { setPage(p.id); setSidebarOpen(false) }}
                  >
                    <Icon />
                    {p.label}
                    {p.id === 'alerts' && (reviewPending > 0 || criticalEvents.length > 0) && (
                      <span className="nav-badge" aria-label={`${reviewPending || criticalEvents.length} need attention`}>
                        {reviewPending || criticalEvents.length}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
        <div className="sidebar-footer">
          <div className="session-chip">
            <span className="avatar">{(me?.username || 'AD').slice(0, 2).toUpperCase()}</span>
            <div className="who"><b>{me?.username || '…'}</b><span>{me?.role || ''}</span></div>
            <button className="icon-btn" title="My account" aria-label="My account" onClick={() => setShowProfile(true)}>
              <Icons.users />
            </button>
            <button className="icon-btn" title="Sign out" aria-label="Sign out" onClick={() => { clearToken(); setAuthed(false) }}>
              <Icons.logout />
            </button>
          </div>
        </div>
      </aside>

      <main className="main">


        <header className="topbar">
          <button type="button" className="icon-btn hamburger" onClick={() => setSidebarOpen(!sidebarOpen)} aria-label="Menu">
            <Icons.menu />
          </button>
          <div className="topbar-title">
            <span className="crumb">Command Center</span>
            <h1>{activePage?.label}</h1>
          </div>
          <button
            type="button"
            className="searchbox"
            onClick={() => setShowPalette(true)}
            aria-label="Open command palette"
          >
            <Icons.search />
            <span>Search pages and actions…</span>
            <kbd>⌘K</kbd>
          </button>
          <div className="topbar-right">
            <div className="status-rail" aria-label="System status">

              <Pill tone={pipelineOnline ? 'ok' : 'warn'}>{pipelineOnline ? 'AI online' : 'AI offline'}</Pill>
              <Pill tone={wsConnected && statusWsConnected ? 'ok' : 'danger'}>
                {wsConnected && statusWsConnected ? 'Live updates' : 'Reconnecting…'}
              </Pill>
            </div>
            <div className="topbar-actions">
              <button type="button" className="icon-btn" title="Command Assistant" aria-label="Command Assistant" onClick={() => setShowCopilot(true)}><Icons.bot /></button>
              <button type="button" className="icon-btn" title="Notifications" aria-label="Notifications" onClick={() => setShowNotifs(true)} style={{ position: 'relative' }}>
                <Icons.bell />
                {criticalEvents.length > 0 && (
                  <span className="nav-badge" style={{ position: 'absolute', top: 2, right: 2 }}>{criticalEvents.length}</span>
                )}
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
          </div>
        </header>

        {(apiDown || loadFailed.length > 0) && (
          <div className="conn-banner" role="status">
            <span>
              {apiDown
                ? 'Cannot reach the backend. Showing the last data received; retrying automatically.'
                : `Some data could not be loaded (${loadFailed.join(', ')}).`}
            </span>
            <button className="btn btn-sm" onClick={() => { setLoadFailed([]); setReloadTick((t) => t + 1) }}>Retry now</button>
          </div>
        )}

        <div className="page">
          {me && !canViewPage(me.role, page) ? (
            <Card title="Access restricted" sub={`The ${me.role} role cannot open this page`}>
              <Empty icon={Icons.shield}>Ask an administrator if you need access.</Empty>
            </Card>
          ) : (
            <PageComponent ctx={ctx} />
          )}
        </div>
      </main>

      {showPalette && (
        <CommandPalette
          pages={ALL_PAGES.filter((p) => canViewPage(me?.role, p.id))}
          actions={[
            { id: 'act-theme', label: `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`, icon: theme === 'dark' ? Icons.sun : Icons.moon, hint: 'Action', run: () => setTheme(theme === 'dark' ? 'light' : 'dark') },
            { id: 'act-copilot', label: 'Open Command Assistant', icon: Icons.bot, hint: 'Action', run: () => setShowCopilot(true) },
            { id: 'act-notifs', label: 'Open Notification Center', icon: Icons.bell, hint: 'Action', run: () => setShowNotifs(true) },
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
        <Copilot ctx={{ events, summary, cameras, threatLevel, locations }} onClose={() => setShowCopilot(false)} />
      )}
    </div>
  )
}

export default App


