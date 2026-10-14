/* The workspace around the page: cameras panel (left), response panel (right),
   live video strip (top of the centre column),
   and the small top-bar and Home pieces that go with them. */
import { useEffect, useState } from 'react'
import { Empty, Icons, SEVERITY_TONE, timeAgo } from './ui'
import { eventLabel } from '../lib/events'
import { liveStreamUrl } from '../services/api'

const CAM_STATUS = {
  live: { label: 'Live', dot: 'ok' },
  online: { label: 'No video', dot: 'warn' },
  offline: { label: 'Offline', dot: '' },
  off: { label: 'Off', dot: '' },
}
const CAM_FILTERS = [
  { id: 'all', label: 'All', test: () => true },
  { id: 'live', label: 'Live', test: (c) => c.status === 'live' },
  { id: 'down', label: 'Not live', test: (c) => c.status !== 'live' },
]

function PanelHead({ title, open, onToggle, side }) {
  const label = `${open ? 'Collapse' : 'Expand'} ${title.toLowerCase()} panel`
  return (
    <div className="panel-head">
      {open && <span>{title}</span>}
      <button type="button" className={`icon-btn panel-toggle ${side}`} title={label} aria-label={label} aria-expanded={open} onClick={onToggle}>
        <Icons.panel />
      </button>
    </div>
  )
}

/** Left panel: every camera and its state. A row opens that camera on the Live page. */
export function CameraPanel({ camList, newDevices = [], onConnect, onAdd, open, onToggle, canManage, canZones, hasMap, onOpenCamera, onLocate, setPage }) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const q = query.trim().toLowerCase()
  const test = CAM_FILTERS.find((f) => f.id === filter).test
  const shown = camList.filter((c) => test(c) && (!q || `${c.name} ${c.location || ''}`.toLowerCase().includes(q)))

  return (
    <aside className={`panel side side-left ${open ? '' : 'collapsed'}`} aria-label="Cameras">
      <PanelHead title="Cameras" open={open} onToggle={onToggle} side="left" />
      {!open ? (
        <div className="rail">
          {camList.map((c) => (
            <button key={c.camera_id} type="button" className="icon-btn rail-cam" title={`${c.name}: ${CAM_STATUS[c.status].label}`}
              aria-label={`${c.name}, ${CAM_STATUS[c.status].label}`} disabled={!onOpenCamera} onClick={() => onOpenCamera(c)}>
              <Icons.camera />
              <span className={`status-dot ${c.threat_score >= 40 ? 'hot' : CAM_STATUS[c.status].dot}`} />
            </button>
          ))}
        </div>
      ) : (
        <>
          <div className="panel-body">
            {canManage && (
              <button type="button" className="btn side-add" onClick={onAdd || (() => setPage('cameras'))}><Icons.plus />Add camera</button>
            )}
            <div className="side-find">
              <label className="find-box">
                <Icons.search />
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find a camera" aria-label="Find a camera" />
              </label>
              <div className="chip-row">
                {CAM_FILTERS.map((f) => (
                  <button key={f.id} type="button" className={`chip ${filter === f.id ? 'on' : ''}`} aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
                    {f.label} <span className="chip-n">{camList.filter(f.test).length}</span>
                  </button>
                ))}
              </div>
            </div>
            {shown.length === 0 ? (
              <Empty icon={Icons.camera}>
                {camList.length === 0
                  ? (canManage ? 'No cameras yet. Add one to start watching.' : 'No cameras have been set up yet.')
                  : 'No camera matches that search.'}
              </Empty>
            ) : (
              <div className="side-list">
                {shown.map((c) => {
                  const hot = c.threat_score >= 40
                  return (
                    <div className={`side-cam ${hot ? 'hot' : ''}`} key={c.camera_id}>
                      <button type="button" className="cam-row" disabled={!onOpenCamera} onClick={() => onOpenCamera(c)} title={onOpenCamera ? 'Open on the Live page' : undefined}>
                        <span className={`status-dot ${hot ? 'hot' : CAM_STATUS[c.status].dot}`} />
                        <span className="cam-row-main">
                          <b>{c.name}</b>
                          <span>{hot ? 'Threat in view' : c.status === 'live' && c.fps != null ? `Live, ${Math.round(c.fps)} fps` : CAM_STATUS[c.status].label}</span>
                        </span>
                      </button>
                      {hasMap && (
                        <button type="button" className="icon-btn" title="Show on the map" aria-label={`Show ${c.name} on the map`} onClick={() => onLocate(c)}>
                          <Icons.map />
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
            {newDevices.length > 0 && (
              <>
                <div className="side-title">On this computer <small>not in use</small></div>
                <div className="side-list">
                  {newDevices.map((d) => (
                    <div className="side-cam" key={d.source}>
                      <span className="cam-row" style={{ cursor: 'default' }}>
                        <span className="status-dot" />
                        <span className="cam-row-main"><b>{d.name}</b><span>Detected</span></span>
                      </span>
                      {onConnect && <button type="button" className="btn btn-sm" onClick={() => onConnect(d)}>Connect</button>}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
          {(canManage || canZones) && (
            <div className="panel-foot links">
              {canManage && <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPage('cameras')}>Manage cameras</button>}
              {canZones && <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPage('zones')}>Zones</button>}
            </div>
          )}
        </>
      )}
    </aside>
  )
}

/** Right panel: the tools for working an alert, and the alerts still waiting for someone. */
export function ResponsePanel({ tools, page, setPage, feed, alertCount, open, onToggle }) {
  return (
    <aside className={`panel side side-right ${open ? '' : 'collapsed'}`} aria-label="Response">
      <PanelHead title="Response" open={open} onToggle={onToggle} side="right" />
      {!open ? (
        <div className="rail">
          <button type="button" className="icon-btn has-badge" title="Review alerts" aria-label={`Review alerts, ${alertCount} waiting`} onClick={() => setPage('alerts')}>
            <Icons.alert />
            {alertCount > 0 && <span className="nav-badge">{alertCount}</span>}
          </button>
          {tools.map((t) => (
            <button key={t.id} type="button" className={`icon-btn rail-tool ${page === t.id ? 'active' : ''}`} style={{ '--tone': `var(--${t.tone})` }}
              title={t.label} aria-label={t.label} aria-current={page === t.id ? 'page' : undefined} onClick={() => setPage(t.id)}>
              <t.icon />
            </button>
          ))}
        </div>
      ) : (
        <>
          <div className="panel-body">
            {tools.length > 0 && (
              <div className="tool-grid">
                {tools.map((t) => (
                  <button key={t.id} type="button" className={`tool ${page === t.id ? 'active' : ''}`} style={{ '--tone': `var(--${t.tone})` }}
                    title={t.desc} aria-current={page === t.id ? 'page' : undefined} onClick={() => setPage(t.id)}>
                    <t.icon />
                    {t.label}
                  </button>
                ))}
              </div>
            )}
            <h2 className="side-title">Open alerts<small>{feed.length ? `${feed.length} not handled` : ''}</small></h2>
            {feed.length === 0 ? (
              <Empty icon={Icons.check}>Nothing waiting. New alerts appear here as cameras raise them.</Empty>
            ) : (
              <div className="feed">
                {feed.slice(0, 30).map((e, i) => (
                  <button type="button" className="feed-row" key={e.id ?? `${e.type}-${e.time}-${i}`} onClick={() => setPage('alerts')}>
                    <span className={`feed-dot tone-${SEVERITY_TONE[e.severity] || 'muted'}`} />
                    <span className="feed-main">
                      <b>{eventLabel(e.type)}</b>
                      <span>{e.cameraName || e.camera || 'Unknown camera'}</span>
                    </span>
                    <time>{timeAgo(e.time)}</time>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="panel-foot">
            <button type="button" className="btn btn-primary side-fab" onClick={() => setPage('alerts')}>
              <Icons.alert />Review alerts{alertCount > 0 ? ` (${alertCount})` : ''}
            </button>
          </div>
        </>
      )}
    </aside>
  )
}

function DeckFeed({ cam, onOpen }) {
  const [failed, setFailed] = useState(false)
  const hot = cam.threat_score >= 40 || cam.flags?.length > 0
  const live = cam.status === 'live'
  return (
    <button type="button" className={`deck-tile ${hot ? 'hot' : ''}`} disabled={!onOpen} onClick={() => onOpen(cam)}
      title={onOpen ? `${cam.name}: open on the Live page` : cam.name} aria-label={`${cam.name}, ${CAM_STATUS[cam.status].label}`}>
      {live && !failed ? (
        <img src={liveStreamUrl(cam.camera_id)} alt="" onError={() => { setFailed(true); setTimeout(() => setFailed(false), 5000) }} />
      ) : (
        <span className="deck-wait"><Icons.camera />{live ? 'Waiting for video' : CAM_STATUS[cam.status].label}</span>
      )}
      <span className="deck-name"><span className={`status-dot ${hot ? 'hot' : CAM_STATUS[cam.status].dot}`} />{cam.name}</span>
    </button>
  )
}

/** Top panel: live video only, above every page. A tile opens that camera on the Live page. */
export function CameraDeck({ camList, open, onToggle, onOpenCamera }) {
  const live = camList.filter((c) => c.status === 'live')
  const label = `${open ? 'Hide' : 'Show'} camera video`
  return (
    <section className={`panel deck ${open ? '' : 'collapsed'}`} aria-label="Camera video">
      <div className="deck-head">
        <span>Live video <small>{live.length} of {camList.length} camera{camList.length === 1 ? '' : 's'}</small></span>
        <button type="button" className="icon-btn deck-toggle" title={label} aria-label={label} aria-expanded={open} onClick={onToggle}>
          <Icons.panel />
        </button>
      </div>
      {open && (camList.length === 0 ? (
        <div className="deck-empty"><Icons.camera />No cameras have been set up yet.</div>
      ) : (
        <div className="deck-strip">
          {camList.map((c) => <DeckFeed key={c.camera_id} cam={c} onOpen={onOpenCamera} />)}
        </div>
      ))}
    </section>
  )
}

/** Home only: type a question, the assistant opens with the answer. */
export function AskBar({ liveCount, onAsk }) {
  const [q, setQ] = useState('')
  const submit = (e) => {
    e.preventDefault()
    if (!q.trim()) return
    onAsk(q.trim())
    setQ('')
  }
  return (
    <div className="askbar">
      <form onSubmit={submit}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about alerts, cameras or the threat level" aria-label="Ask the assistant" />
        <span className="askbar-meta">{liveCount} camera{liveCount === 1 ? '' : 's'} live</span>
        <button type="submit" className="askbar-send" disabled={!q.trim()} aria-label="Ask"><Icons.dispatch /></button>
      </form>
    </div>
  )
}

/** Local time for the top bar. Ticks by itself so the rest of the app does not re-render every second. */
export function Clock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])
  return (
    <time className="appbar-clock" dateTime={now.toISOString()} title="Local time">
      <b>{now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}</b>
      <span>{now.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })}</span>
    </time>
  )
}

/** Avatar in the top bar: who is signed in, and the account-level pages. */
export function AccountMenu({ me, open, setOpen, items, onSignOut }) {
  return (
    <div className="account">
      <button type="button" className="avatar avatar-btn" aria-haspopup="menu" aria-expanded={open} aria-label="Account menu" onClick={() => setOpen(!open)}>
        {(me?.username || '…').slice(0, 2).toUpperCase()}
      </button>
      {open && (
        <>
          <button type="button" className="menu-scrim" aria-label="Close account menu" onClick={() => setOpen(false)} />
          <div className="account-menu" role="menu">
            <div className="account-who"><b>{me?.username || '…'}</b><span>{me?.role || ''}</span></div>
            {items.map((it) => (
              <button key={it.label} type="button" role="menuitem" className="menu-item" onClick={() => { setOpen(false); it.run() }}>
                <it.icon />{it.label}
              </button>
            ))}
            <button type="button" role="menuitem" className="menu-item" onClick={onSignOut}><Icons.logout />Sign out</button>
          </div>
        </>
      )}
    </div>
  )
}
