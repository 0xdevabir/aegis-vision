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

      <div className="section-label"><span>Right now</span></div>
      <div className="grid grid-4" style={{ marginBottom: 24 }}>
        <Stat
          label={systemStatus?.online ? 'Cameras streaming' : 'Cameras set up'}
          value={`${systemStatus?.online ? (liveCams.length || activeCameras) : cameras.length}`}
          delta={systemStatus?.online ? `${offlineCameras} offline` : 'None streaming while detection is off'}
          accent="primary" icon={Icons.camera}
        />
        <Stat label="Detection" value={systemStatus?.online ? 'On' : 'Off'} delta={systemStatus?.online ? `${liveCams.length} camera${liveCams.length === 1 ? '' : 's'} reporting` : 'Start the pipeline to turn it on'} accent={systemStatus?.online ? 'ok' : 'warn'} icon={Icons.ai} />
        <Stat label="Critical alerts" value={criticalEvents.length} delta={`${events.length} events since you signed in`} accent={criticalEvents.length ? 'danger' : 'ok'} icon={Icons.alert} />
        <Stat label="Threat level" value={threatLevel[0].toUpperCase() + threatLevel.slice(1)} delta="From unreviewed alerts in the last 15 min" accent={threatAccent} icon={Icons.shield} />
      </div>

      <div className="section-label"><span>Detections</span><small>Last {summary?.period_hours ?? 24} hours</small></div>
      <div className="grid grid-4" style={{ marginBottom: 24 }}>
        <Stat label="Events" value={summary?.total_events ?? '—'} delta="Everything the cameras flagged" accent="primary" icon={Icons.incident} />
        <Stat label="Watchlist matches" value={summary?.criminal_detections ?? '—'} delta="Held until a person reviews them" accent="primary" icon={Icons.watchlist} />
        <Stat label="Weapon alerts" value={summary?.weapon_detections ?? '—'} delta="Confirmed across several frames" accent="primary" icon={Icons.alert} />
        <Stat label="Alerts raised" value={summary?.alerts_triggered ?? '—'} delta="Review them in Alerts" accent="primary" icon={Icons.dispatch} />
      </div>

      <div className="grid grid-23" style={{ marginBottom: 14 }}>
        <Card title="Events per day" sub="Last 7 days">
          <AreaChart data={trendData.length ? trendData : [0]} label="Events / day" />
        </Card>
        <Card title="What was detected" sub={`Last ${summary?.period_hours ?? 24} hours`}>
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
        <Card title="Latest detections" actions={<Pill tone={ctx.wsConnected ? 'ok' : 'danger'}>{ctx.wsConnected ? 'Live' : 'Offline'}</Pill>}>
          {events.length === 0 && <Empty icon={Icons.eye}>Nothing detected yet. Start the pipeline with <code>./run.sh</code></Empty>}
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Card title="Busiest locations" sub="Last 24 hours">
            <BarList items={locations.slice(0, 5).map((l) => ({ label: l.location || 'Unknown', value: l.events }))} />
          </Card>
          <Card title="Latest critical alert">
            {mapAlert ? (
              <MapPin lat={mapAlert.lat} lng={mapAlert.lng} label={mapAlert.cameraName || mapAlert.camera} height={180} />
            ) : (
              <Empty icon={Icons.map}>The camera's location shows here when a critical alert comes in.</Empty>
            )}
          </Card>
        </div>
      </div>
    </>
  )
}
