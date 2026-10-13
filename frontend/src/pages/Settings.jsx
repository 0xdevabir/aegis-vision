import { isAlertSoundMuted, setAlertSoundMuted } from '../hooks/alertNotifications'
import { useEffect, useState } from 'react'
import { Card, Tag } from '../components/ui'
import { fetchIntegrationStatus, testIntegration, fetchConfigThresholds, saveConfigThreshold, fetchThresholdSpecs } from '../services/api'
import { useToast } from '../components/Toast'

const THRESHOLD_UI = {
  confidence_threshold: { label: 'Person detection confidence', step: 0.05, fmt: (v) => `${Math.round(v * 100)}%`, hint: 'Higher = fewer false people, may miss distant ones' },
  weapon_conf_threshold: { label: 'Weapon detection confidence', step: 0.05, fmt: (v) => `${Math.round(v * 100)}%`, hint: 'Higher = fewer false alarms, may miss real weapons' },
  face_tolerance: { label: 'Face match strictness', step: 0.01, fmt: (v) => v.toFixed(2), hint: 'Lower = stricter (fewer wrong matches). Default 0.45' },
  loiter_seconds: { label: 'Loitering time', step: 1, fmt: (v) => `${v}s`, hint: 'Time standing still before it counts as loitering' },
  crowd_threshold: { label: 'Crowd size', step: 1, fmt: (v) => `${v} people`, hint: 'People in one zone before a crowd alert' },
}

function ThresholdSlider({ id, spec, value, canEdit, onCommit }) {
  const ui = THRESHOLD_UI[id]
  const [draft, setDraft] = useState(null)
  const shown = draft ?? value
  const dirtyDefault = value !== spec.default
  return (
    <div className="field" style={{ marginBottom: 16 }}>
      <label htmlFor={`thr-${id}`} style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span>{ui.label}</span><b>{ui.fmt(shown)}</b>
      </label>
      <input
        id={`thr-${id}`} type="range" min={spec.min} max={spec.max} step={ui.step}
        value={shown} disabled={!canEdit}
        onChange={(e) => setDraft(Number(e.target.value))}
        onPointerUp={() => { if (draft != null) { onCommit(id, draft); setDraft(null) } }}
        onKeyUp={() => { if (draft != null) { onCommit(id, draft); setDraft(null) } }}
      />
      <span className="meta muted" style={{ fontSize: '0.74rem' }}>
        {ui.hint}
        {canEdit && dirtyDefault && (
          <> · <button type="button" className="link-btn" onClick={() => onCommit(id, spec.default)}>Reset to {ui.fmt(spec.default)}</button></>
        )}
      </span>
    </div>
  )
}

export function Settings({ ctx }) {
  const { push: toast } = useToast()
  const { theme, setTheme, systemStatus, me } = ctx
  const [muted, setMuted] = useState(isAlertSoundMuted)
  const canEdit = me?.role === 'admin'
  const [specs, setSpecs] = useState(null)
  const [thresholds, setThresholds] = useState({})

  useEffect(() => {
    Promise.all([fetchThresholdSpecs(), fetchConfigThresholds()]).then(([sp, t]) => {
      setSpecs(sp)
      setThresholds(Object.fromEntries(Object.entries(t).map(([k, v]) => [k, parseFloat(v)])))
    }).catch(() => {})
  }, [])

  const [integrations, setIntegrations] = useState(null)
  const [testMsg, setTestMsg] = useState(null)

  useEffect(() => {
    fetchIntegrationStatus().then(setIntegrations).catch(() => {})
  }, [])

  const commit = async (key, val) => {
    const prev = thresholds[key]
    setThresholds((t) => ({ ...t, [key]: val }))
    try {
      await saveConfigThreshold(key, val)
      toast('Saved — cameras pick this up within about 30 seconds', 'ok')
    } catch (e) {
      setThresholds((t) => ({ ...t, [key]: prev }))
      toast(e.message || 'Could not save', 'danger')
    }
  }

  const runTest = async (channel) => {
    setTestMsg(null)
    try {
      const r = await testIntegration(channel, `Aegis test from ${channel}`)
      setTestMsg({ ok: true, text: `${channel}: HTTP ${r.http_status}` })
    } catch (e) {
      setTestMsg({ ok: false, text: e.message })
    }
  }

  const redis = systemStatus?.redis

  return (
    <div className="grid grid-2">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Card title="Detection thresholds" sub={canEdit ? 'applied live to every camera' : 'read-only — admin only'}>
          {!specs && <p className="muted">Loading…</p>}
          {specs && Object.keys(THRESHOLD_UI).filter((k) => specs[k]).map((k) => (
            <ThresholdSlider
              key={k} id={k} spec={specs[k]}
              value={thresholds[k] ?? specs[k].default} canEdit={canEdit} onCommit={commit}
            />
          ))}
          <p className="muted" style={{ fontSize: '0.74rem' }}>
            Changes are written to the audit log. Re-check false alarms for a day after loosening anything.
          </p>
        </Card>

        <Card title="AI models" sub="what is actually running">
          {Object.entries(systemStatus?.models || {}).map(([key, status]) => (
            <div className="row" key={key}>
              <span>{{ human_detector: 'Person detection', weapon_detector: 'Weapon detection', vehicle_detector: 'Vehicle detection', pose_analyzer: 'Pose / fall checks', fire_detector: 'Fire & smoke detection' }[key] || key}</span>
              <Tag tone={status === 'ok' ? 'ok' : status === 'missing' ? 'danger' : 'muted'}>
                {status === 'ok' ? 'Loaded' : status === 'missing' ? 'OFF — model file missing' : 'Not installed (optional)'}
              </Tag>
            </div>
          ))}
          {!systemStatus?.models && <p className="muted">Status unavailable.</p>}
        </Card>

        <Card title="External Integrations" sub="CAD / SMS / radio / security webhooks">
          {integrations && (
            <>
              <div className="row">
                <span>ALERTS_ENABLED</span>
                <Tag tone={integrations.alerts_enabled ? 'ok' : 'warn'}>
                  {integrations.alerts_enabled ? 'true' : 'false'}
                </Tag>
              </div>
              {Object.entries(integrations.channels || {}).map(([name, ch]) => (
                <div className="row" key={name}>
                  <span>
                    {name}
                    {ch.url_host && <span className="meta muted"> · {ch.url_host}</span>}
                  </span>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <Tag tone={ch.configured ? 'ok' : 'muted'}>{ch.configured ? 'Configured' : 'Not set'}</Tag>
                    {ch.configured && (
                      <button className="btn btn-sm" onClick={() => runTest(name)}>Test</button>
                    )}
                  </div>
                </div>
              ))}
              {testMsg && (
                <div className={testMsg.ok ? 'tag tag-ok' : 'login-error'} style={{ marginTop: 8, padding: '8px 12px', display: 'block' }}>
                  {testMsg.text}
                </div>
              )}
              <p className="muted" style={{ fontSize: '0.74rem', marginTop: 10 }}>
                Set CAD_WEBHOOK, SMS_WEBHOOK, LAW_ENFORCEMENT_WEBHOOK in .env and ALERTS_ENABLED=true
              </p>
            </>
          )}
        </Card>

        <Card title="Alert rules">
          <div className="row"><span>Watchlist match → external notification</span><Tag tone="info">After operator confirms</Tag></div>
          <div className="row"><span>Weapon and fire alerts</span><Tag tone="info">Multi-frame confirmed</Tag></div>
          <div className="row"><span>Incident ticket for critical / high alerts</span><Tag tone="ok">Automatic</Tag></div>
          <div className="row"><span>Heartbeat / camera SLA</span><Tag tone={systemStatus?.online ? 'ok' : 'warn'}>{systemStatus?.online ? 'Healthy' : 'No signal'}</Tag></div>
        </Card>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Card title="Appearance">
          <div className="row">
            <span>Theme</span>
            <div className="seg" role="group" aria-label="Theme">
              <button type="button" className={theme === 'dark' ? 'on' : ''} onClick={() => setTheme('dark')}>Dark</button>
              <button type="button" className={theme === 'light' ? 'on' : ''} onClick={() => setTheme('light')}>Light</button>
            </div>
          </div>
          <div className="row">
            <span>Alert sound</span>
            <div className="seg" role="group" aria-label="Alert sound">
              <button type="button" className={!muted ? 'on' : ''} onClick={() => { setAlertSoundMuted(false); setMuted(false) }}>On</button>
              <button type="button" className={muted ? 'on' : ''} onClick={() => { setAlertSoundMuted(true); setMuted(true) }}>Muted</button>
            </div>
          </div>
          <p className="muted" style={{ fontSize: '0.74rem', marginTop: 8 }}>
            Theme: <b>{theme}</b> · preferences are saved on this device. Critical alerts repeat the tone until acknowledged.
          </p>
        </Card>

        <Card title="High Availability">
          <div className="row">
            <span>Redis</span>
            <Tag tone={redis?.connected ? 'ok' : 'muted'}>
              {redis?.connected ? 'Connected' : redis?.enabled ? 'Configured (down)' : 'In-process'}
            </Tag>
          </div>
          <div className="row"><span>Offline cameras</span><Tag tone={(systemStatus?.offline_cameras || 0) ? 'warn' : 'ok'}>{systemStatus?.offline_cameras ?? 0}</Tag></div>
          <div className="row"><span>Mode</span><span className="mono muted">{redis?.mode || 'in-process'}</span></div>
          <p className="muted" style={{ fontSize: '0.74rem', marginTop: 8 }}>
            docker compose up redis — set REDIS_URL=redis://localhost:6379/0
          </p>
        </Card>

        <Card title="API & Storage">
          <dl className="kv">
            <dt>REST</dt><dd className="mono">/api/v1</dd>
            <dt>Docs</dt><dd><a href="/docs" target="_blank" rel="noreferrer" style={{ color: 'var(--primary)' }}>/docs</a></dd>
            <dt>Evidence</dt><dd>PostgreSQL + SHA-256 custody</dd>
            <dt>Recordings</dt><dd className="mono">data/recordings/</dd>
          </dl>
        </Card>

        <Card title="Keyboard Shortcuts">
          <div className="row"><span>Command palette</span><span className="mono">⌘K / Ctrl+K</span></div>
          <div className="row"><span>Notifications</span><span className="mono">N</span></div>
          <div className="row"><span>AI Copilot</span><span className="mono">C</span></div>
          <div className="row"><span>Triage: next / previous</span><span className="mono">J / K</span></div>
          <div className="row"><span>Triage: confirm / reject</span><span className="mono">V / D</span></div>
        </Card>
      </div>
    </div>
  )
}

