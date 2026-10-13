import { Card, Stat, Icons, Tag, SEVERITY_TONE, timeAgo, Empty, Pill } from '../components/ui'
import { AreaChart, BarList, Donut } from '../components/charts'
import { MapPin } from '../components/MapPin'
import { eventLabel } from '../lib/events'

const MODEL_LABELS = {
  weapon_detector: 'Weapon detection',
  vehicle_detector: 'Vehicle detection',
  human_detector: 'Person detection',
  pose_analyzer: 'Pose / fall checks',
  fire_detector: 'Fire & smoke detection',
}

function attentionItems(ctx, offlineCameras) {
  const items = []
  const sys = ctx.systemStatus
  if (ctx.reviewPending > 0) {
    items.push({ tone: 'warn', text: `${ctx.reviewPending} alert${ctx.reviewPending === 1 ? '' : 's'} waiting for review`, action: 'Review', page: 'alerts' })
  }
  if (sys && !sys.online) {
    items.push({ tone: 'danger', text: 'AI pipeline is not reporting — no live detection', action: 'Cameras', page: 'cameras' })
  }
  if (offlineCameras > 0) {
    items.push({ tone: 'warn', text: `${offlineCameras} camera${offlineCameras === 1 ? '' : 's'} offline`, action: 'Cameras', page: 'cameras' })
  }
  Object.entries(sys?.models || {}).forEach(([key, status]) => {
    if (status === 'missing') {
      items.push({ tone: 'danger', text: `${MODEL_LABELS[key] || key} is OFF — model file not found`, action: 'Details', page: 'settings' })
    }
  })
  return items
}

export function Overview({ ctx }) {
  const { events, systemStatus, summary, trends, locations, threatLevel, cameras } = ctx

  const liveCams = Object.values(systemStatus?.cameras || {})
  const activeCameras = cameras.filter((c) => c.active).length
  const offlineCameras = cameras.length - activeCameras
  const criticalEvents = events.filter((e) => e.severity === 'critical')
  const trendData = trends.map((t) => t.events)
  const mapAlert = criticalEvents.find((e) => e.lat != null)

  const attention = attentionItems(ctx, offlineCameras)
  const threatAccent = { critical: 'danger', high: 'warn', low: 'ok' }[threatLevel] || 'ok'

  return (
    <>
      <div className="page-head">
        <div>
          <h2>Executive Overview</h2>
          <p>Live posture across cameras, AI pipeline, and response channels.</p>
        </div>
        <div className="head-actions">
          <Pill tone={ctx.wsConnected ? 'ok' : 'danger'}>{ctx.wsConnected ? 'Realtime linked' : 'Link down'}</Pill>
          <Pill tone={systemStatus?.online ? 'info' : 'muted'}>{systemStatus?.online ? 'Pipeline online' : 'Pipeline standby'}</Pill>
        </div>
      </div>

      <section className={`attention ${attention.length ? '' : 'clear'}`} aria-label="Needs attention">
        <h3>{attention.length ? 'Needs attention' : 'All clear'}</h3>
        {attention.length === 0 && <p className="muted">No pending reviews, offline cameras or missing models.</p>}
        {attention.map((a) => (
          <div className={`attn-row tone-${a.tone}`} key={a.text}>
            <span>{a.text}</span>
            <button type="button" className="btn btn-sm" onClick={() => ctx.setPage(a.page)}>{a.action}</button>
          </div>
        ))}
      </section>

      <div className="section-label"><span>Operational KPIs</span></div>
      <div className="grid grid-4" style={{ marginBottom: 18 }}>
        <Stat
          label={systemStatus?.online ? 'Active Cameras' : 'Configured Cameras'}
          value={`${systemStatus?.online ? (liveCams.length || activeCameras) : cameras.length}`}
          delta={systemStatus?.online ? `${offlineCameras} offline` : 'none streaming — pipeline offline'}
          accent="primary" icon={Icons.camera}
        />
        <Stat label="AI Pipeline" value={systemStatus?.online ? 'ONLINE' : 'OFFLINE'} delta={systemStatus?.online ? `${liveCams.length} camera${liveCams.length === 1 ? '' : 's'} reporting` : 'Start the pipeline'} accent={systemStatus?.online ? 'ok' : 'warn'} icon={Icons.ai} />
        <Stat label="Active Alerts" value={criticalEvents.length} delta={`${events.length} events since you signed in`} accent={criticalEvents.length ? 'danger' : 'ok'} icon={Icons.alert} />
        <Stat label="Threat Level" value={threatLevel.toUpperCase()} delta="Unreviewed alerts, last 15 min" accent={threatAccent} icon={Icons.shield} />
      </div>

      <div className="section-label"><span>Detection volume · last {summary?.period_hours ?? 24}h</span></div>
      <div className="grid grid-4" style={{ marginBottom: 18 }}>
        <Stat label="Incidents" value={summary?.total_events ?? '—'} delta={`last ${summary?.period_hours ?? 24}h`} accent="purple" icon={Icons.incident} />
        <Stat label="Watchlist matches" value={summary?.criminal_detections ?? '—'} delta="held for human review" accent="danger" icon={Icons.watchlist} />
        <Stat label="Weapon alerts" value={summary?.weapon_detections ?? '—'} delta="multi-frame confirmed" accent="warn" icon={Icons.alert} />
        <Stat label="Alerts raised" value={summary?.alerts_triggered ?? '—'} delta="see Alert Triage" accent="cyan" icon={Icons.dispatch} />
      </div>

      <div className="grid grid-23" style={{ marginBottom: 18 }}>
        <Card title="Incident trend" sub="events / day · 7 days">
          <AreaChart data={trendData.length ? trendData : [0]} label="Events / day" />
        </Card>
        <Card title="Detection mix" sub={`last ${summary?.period_hours ?? 24}h`}>
          <Donut
            label={summary?.total_events ?? 0}
            sublabel="events"
            segments={[
              { label: 'Watchlist', value: summary?.criminal_detections ?? 0, color: 'var(--danger)' },
              { label: 'Weapon', value: summary?.weapon_detections ?? 0, color: 'var(--orange)' },
              { label: 'Suspicious', value: summary?.suspicious_activities ?? 0, color: 'var(--warn)' },
            ]}
          />
        </Card>
      </div>

      <div className="grid grid-23">
        <Card title="Recent detections" sub="live feed" actions={<Pill tone={ctx.wsConnected ? 'ok' : 'danger'}>{ctx.wsConnected ? 'Live' : 'Offline'}</Pill>}>
          {events.length === 0 && <Empty icon={Icons.eye}>No detections yet — start the pipeline: <code>./run.sh</code></Empty>}
          {events.slice(0, 8).map((evt, i) => (
            <div key={i} className={`row ${evt.severity === 'critical' ? 'crit' : ''}`}>
              <div>
                <b>{eventLabel(evt.type)}</b>
                <div className="meta">{evt.msg} · {evt.camera || '—'} · {timeAgo(evt.time)}</div>
              </div>
              <Tag tone={SEVERITY_TONE[evt.severity] || 'muted'}>{evt.severity}</Tag>
            </div>
          ))}
        </Card>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card title="Hotspots" sub="last 24h">
            <BarList items={locations.slice(0, 5).map((l) => ({ label: l.location || 'Unknown', value: l.events }))} />
          </Card>
          <Card title="Latest threat location">
            {mapAlert ? (
              <MapPin lat={mapAlert.lat} lng={mapAlert.lng} label={mapAlert.cameraName || mapAlert.camera} height={180} />
            ) : (
              <Empty icon={Icons.map}>A GPS pin appears when a critical alert has camera coordinates</Empty>
            )}
          </Card>
        </div>
      </div>
    </>
  )
}
