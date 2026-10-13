import { parseTs } from '../lib/time'
import { useEffect, useRef, useState } from 'react'
import { Card, Icons, Empty, Stat, Tag } from '../components/ui'
import { AreaChart, BarList, Donut } from '../components/charts'
import { fetchCalibrationMetrics, fetchLiveAnalytics } from '../services/api'

function fmtDuration(sec) {
  if (sec == null) return '—'
  if (sec < 90) return `${Math.round(sec)}s`
  if (sec < 5400) return `${(sec / 60).toFixed(1)} min`
  return `${(sec / 3600).toFixed(1)} h`
}

// Occupancy grid from the pipeline heartbeat (rows of 0-100), drawn as a blue→red heat overlay.
function Heatmap({ grid }) {
  const ref = useRef(null)
  useEffect(() => {
    const canvas = ref.current
    if (!canvas || !grid?.length) return
    const rows = grid.length, cols = grid[0].length
    canvas.width = cols
    canvas.height = rows
    const g = canvas.getContext('2d')
    g.clearRect(0, 0, cols, rows)
    grid.forEach((row, y) => row.forEach((v, x) => {
      if (!v) return
      g.fillStyle = `hsla(${240 - 2.4 * v}, 90%, 50%, ${0.25 + 0.0075 * v})`
      g.fillRect(x, y, 1, 1)
    }))
  }, [grid])
  return (
    <canvas
      ref={ref}
      aria-label="Occupancy heatmap"
      style={{ width: '100%', aspectRatio: '16 / 9', background: 'var(--media)', borderRadius: 12, filter: 'blur(3px)' }}
    />
  )
}

function LiveCamera({ cam }) {
  const lines = Object.entries(cam.traffic_flow?.lines || {})
  const dwell = Object.entries(cam.dwell_stats || {})
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <strong>{cam.camera_id}</strong>
        <Tag tone="ok">{cam.track_count ?? 0} in view</Tag>
      </div>
      <Heatmap grid={cam.heatmap} />
      <dl className="kv" style={{ marginTop: 10 }}>
        <dt>People (last {Math.round(cam.traffic_flow?.window_seconds ?? 60)}s)</dt><dd>{cam.traffic_flow?.people ?? 0}</dd>
        {lines.map(([name, c]) => (
          <span key={name} style={{ display: 'contents' }}><dt>Line {name}</dt><dd>{c.in} in · {c.out} out</dd></span>
        ))}
        {dwell.map(([zone, d]) => (
          <span key={zone} style={{ display: 'contents' }}><dt>Dwell {zone}</dt><dd>{d.count} · avg {fmtDuration(d.avg_duration)}</dd></span>
        ))}
      </dl>
    </div>
  )
}

export function Analytics({ ctx }) {
  const { summary, trends, locations, events } = ctx
  const [cal, setCal] = useState(null)
  const [calError, setCalError] = useState('')
  const [live, setLive] = useState({})

  useEffect(() => {
    fetchCalibrationMetrics(168).then(setCal).catch((e) => setCalError(e.message || 'Request failed'))
  }, [])

  useEffect(() => {
    const load = () => fetchLiveAnalytics().then((d) => setLive(d || {})).catch(() => {})
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [])

  const trendData = trends.map((t) => t.events)
  const trendLabels = trends.map((t) => {
    const d = parseTs(`${t.date}T00:00:00`)
    return d ? d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' }) : t.date
  })
  const hourLabels = Array.from({ length: 24 }, (_, hr) => `${String(hr).padStart(2, '0')}:00`)
  const total = summary?.total_events ?? 0
  const crit = summary?.criminal_detections ?? 0
  const weap = summary?.weapon_detections ?? 0
  const susp = summary?.suspicious_activities ?? 0

  const precision = cal?.precision != null ? `${(cal.precision * 100).toFixed(1)}%` : '—'
  const far = cal?.false_alarm_rate != null
    ? `${(cal.false_alarm_rate * 100).toFixed(1)}%`
    : (cal?.proxy?.dismiss_rate != null ? `${(cal.proxy.dismiss_rate * 100).toFixed(1)}%*` : '—')

  const hourBuckets = Array.from({ length: 24 }, () => 0)
  events.forEach((e) => {
    const d = parseTs(e.time)      // zone-less UTC from the backend, shown in local time
    if (d) hourBuckets[d.getHours()]++
  })

  return (
    <>
      <div className="grid grid-4 mb">
        <Stat label="Events" value={summary ? total : '—'} delta={`Last ${summary?.period_hours ?? 24} hours`} accent="primary" icon={Icons.incident} />
        <Stat label="Precision" value={precision} delta={cal?.labeled ? `From ${cal.labeled} labelled detections` : 'Label detections to measure this'} accent="ok" icon={Icons.check} />
        <Stat label="False alarm rate" value={far}
          delta={cal?.false_alarm_rate != null ? 'From labelled detections' : '* Estimated from dismissed alerts'} accent="warn" icon={Icons.alert} />
        <Stat label="Time to acknowledge" value={fmtDuration(summary?.mtta_seconds)}
          delta={summary?.acknowledged_alerts ? `Average of ${summary.acknowledged_alerts} acknowledged alerts` : 'No acknowledged alerts yet'} accent="cyan" icon={Icons.clock} />
      </div>

      <div className="grid grid-2 mb">
        <Card title="Events per day" sub="Last 7 days">
          <AreaChart data={trendData} labels={trendLabels} label="Events per day" emptyText="No events in the last 7 days" />
        </Card>
        <Card title="Alerts by hour of day" sub={`Latest ${events.length} alerts · your local time`}>
          <AreaChart data={hourBuckets} labels={hourLabels} color="var(--purple)" label="Alerts per hour" emptyText="No alerts loaded yet" />
        </Card>
      </div>

      <div className="grid grid-2 mb">
        <Card title="What was detected" sub={`Last ${summary?.period_hours ?? 24} hours`}>
          <Donut
            label={total}
            sublabel="events"
            segments={[
              { label: 'Watchlist', value: crit, color: 'var(--danger)' },
              { label: 'Weapon', value: weap, color: 'var(--orange)' },
              { label: 'Suspicious', value: susp, color: 'var(--warn)' },
            ]}
          />
        </Card>
        <Card title="Busiest locations" sub="Detections per camera location">
          <BarList items={locations.map((l) => ({ label: l.location || 'Unknown', value: l.events }))} color="var(--cyan)" emptyText="No detections in this period" />
        </Card>
      </div>

      <Card title="Live occupancy" sub="Where people stand, line crossings and dwell time per camera">
        {Object.keys(live).length ? (
          <div className="grid grid-2">
            {Object.values(live).map((cam) => <LiveCamera key={cam.camera_id} cam={cam} />)}
          </div>
        ) : <Empty icon={Icons.chart}>No live occupancy data. It appears while the detection pipeline is running.</Empty>}
      </Card>
      <div style={{ height: 14 }} />

      <Card title="Detection accuracy" sub="From detections people have labelled · last 7 days">
        {!cal && !calError && <div className="skeleton" style={{ height: 120 }} aria-label="Loading accuracy figures" />}
        {!cal && calError && <Empty icon={Icons.alert}>Could not load accuracy figures: {calError}</Empty>}
        {cal && (
          <div className="grid grid-2">
            <div>
              <dl className="kv">
                <dt>Labelled</dt><dd>{cal.labeled}</dd>
                <dt>True positives</dt><dd>{cal.confusion?.true_positive ?? 0}</dd>
                <dt>False positives</dt><dd>{cal.confusion?.false_positive ?? 0}</dd>
                <dt>Recall</dt><dd>{cal.recall != null ? `${(cal.recall * 100).toFixed(1)}%` : '—'}</dd>
                <dt>F1</dt><dd>{cal.f1 != null ? cal.f1.toFixed(3) : '—'}</dd>
                <dt>Dismiss rate</dt><dd>{cal.proxy?.dismiss_rate != null ? `${(cal.proxy.dismiss_rate * 100).toFixed(1)}%` : '—'}</dd>
              </dl>
              <p className="muted" style={{ fontSize: '0.76rem', marginTop: 10 }}>
                Mark a snapshot as a false positive on the Evidence page, or run{' '}
                <code className="mono">python scripts/evaluate_pipeline.py --output data/results/eval.json</code>
              </p>
            </div>
            <div>
              {cal.pipeline_eval ? (
                <>
                  <Tag tone="ok">Pipeline eval loaded</Tag>
                  <dl className="kv" style={{ marginTop: 10 }}>
                    <dt>Frames</dt><dd>{cal.pipeline_eval.frames_processed}</dd>
                    <dt>Avg ms</dt><dd>{cal.pipeline_eval.avg_frame_ms}</dd>
                    <dt>Throughput</dt><dd>{cal.pipeline_eval.throughput_fps} FPS</dd>
                  </dl>
                </>
              ) : (
                <Empty icon={Icons.report}>No offline evaluation yet. Run <code>evaluate_pipeline.py</code> to add one.</Empty>
              )}
            </div>
          </div>
        )}
      </Card>
    </>
  )
}
