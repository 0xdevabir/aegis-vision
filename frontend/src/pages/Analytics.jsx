import { parseTs } from '../lib/time'
import { useEffect, useState } from 'react'
import { Card, Icons, Empty, Tag } from '../components/ui'
import { AreaChart, BarList, Donut } from '../components/charts'
import { fetchCalibrationMetrics } from '../services/api'

function fmtDuration(sec) {
  if (sec == null) return '—'
  if (sec < 90) return `${Math.round(sec)}s`
  if (sec < 5400) return `${(sec / 60).toFixed(1)} min`
  return `${(sec / 3600).toFixed(1)} h`
}

export function Analytics({ ctx }) {
  const { summary, trends, locations, events } = ctx
  const [cal, setCal] = useState(null)

  useEffect(() => {
    fetchCalibrationMetrics(168).then(setCal).catch(() => {})
  }, [])

  const trendData = trends.map((t) => t.events)
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
      <div className="grid grid-4" style={{ marginBottom: 14 }}>
        <div className="stat accent-primary"><span className="label">Events (24h)</span><span className="value">{total}</span></div>
        <div className="stat accent-ok">
          <span className="label">Precision</span>
          <span className="value">{precision}</span>
          <span className="delta">{cal?.labeled ? `${cal.labeled} labeled` : 'label alerts to calibrate'}</span>
        </div>
        <div className="stat accent-warn">
          <span className="label">False Alarm Rate</span>
          <span className="value">{far}</span>
          <span className="delta">{cal?.false_alarm_rate != null ? 'from ground truth' : 'proxy from dismissals'}</span>
        </div>
        <div className="stat accent-cyan">
          <span className="label">Time to Acknowledge</span>
          <span className="value">{fmtDuration(summary?.mtta_seconds)}</span>
          <span className="delta">{summary?.acknowledged_alerts ? `mean of ${summary.acknowledged_alerts} acknowledged` : 'no acknowledged alerts yet'}</span>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginBottom: 14 }}>
        <Card title="Daily Incidents" sub="last 7 days">
          {trendData.length ? <AreaChart data={trendData} label="Events / day" /> : <Empty icon={Icons.chart}>No trend data yet</Empty>}
        </Card>
        <Card title="Hourly Activity Heat" sub="events by hour (session)">
          <AreaChart data={hourBuckets} color="var(--purple)" label="Events / hour" />
        </Card>
      </div>

      <div className="grid grid-2" style={{ marginBottom: 14 }}>
        <Card title="Threat Distribution" sub="last 24h">
          <Donut
            label={total}
            sublabel="events"
            segments={[
              { label: 'Criminal', value: crit, color: 'var(--danger)' },
              { label: 'Weapon', value: weap, color: 'var(--orange)' },
              { label: 'Suspicious', value: susp, color: 'var(--warn)' },
            ]}
          />
        </Card>
        <Card title="Location Hotspots" sub="detections per camera location">
          <BarList items={locations.map((l) => ({ label: l.location || 'Unknown', value: l.events }))} color="var(--cyan)" />
        </Card>
      </div>

      <Card title="Model Calibration" sub="ground-truth labels · confusion matrix">
        {!cal && <Empty icon={Icons.chart}>Loading calibration metrics…</Empty>}
        {cal && (
          <div className="grid grid-2">
            <div>
              <dl className="kv">
                <dt>Labeled</dt><dd>{cal.labeled}</dd>
                <dt>True positives</dt><dd>{cal.confusion?.true_positive ?? 0}</dd>
                <dt>False positives</dt><dd>{cal.confusion?.false_positive ?? 0}</dd>
                <dt>Recall</dt><dd>{cal.recall != null ? `${(cal.recall * 100).toFixed(1)}%` : '—'}</dd>
                <dt>F1</dt><dd>{cal.f1 != null ? cal.f1.toFixed(3) : '—'}</dd>
                <dt>Dismiss rate</dt><dd>{cal.proxy?.dismiss_rate != null ? `${(cal.proxy.dismiss_rate * 100).toFixed(1)}%` : '—'}</dd>
              </dl>
              <p className="muted" style={{ fontSize: '0.76rem', marginTop: 10 }}>
                Mark evidence as False Positive in Evidence Center, or run{' '}
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
                <Empty icon={Icons.report}>No eval.json yet — run evaluate_pipeline.py</Empty>
              )}
            </div>
          </div>
        )}
      </Card>
    </>
  )
}
