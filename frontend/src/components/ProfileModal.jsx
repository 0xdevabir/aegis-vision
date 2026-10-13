import { useState } from 'react'
import { Modal } from './ui'
import { changePassword } from '../services/api'

/** Self-service password change. Rules mirror the backend: 10+ characters, not only letters or only digits. */
export function ProfileModal({ me, onClose }) {
  const [form, setForm] = useState({ current: '', next: '', again: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  const problem = (() => {
    if (!form.next) return ''
    if (form.next.length < 10) return 'Use at least 10 characters.'
    if (/^[A-Za-z]+$/.test(form.next) || /^\d+$/.test(form.next)) return 'Mix letters with digits or symbols.'
    if (form.again && form.again !== form.next) return 'The two new passwords do not match.'
    return ''
  })()
  const ready = form.current && form.next && form.again && !problem

  const submit = async () => {
    setBusy(true); setError('')
    try {
      await changePassword(form.current, form.next)
      setDone(true)
    } catch (e) {
      setError(e.message || 'Could not change password')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title="My account"
      onClose={onClose}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className="btn" onClick={onClose}>{done ? 'Close' : 'Cancel'}</button>
          {!done && <button className="btn btn-primary" disabled={!ready || busy} onClick={submit}>{busy ? 'Saving…' : 'Change password'}</button>}
        </div>
      )}
    >
      <div style={{ display: 'grid', gap: 10 }}>
        <div className="meta">Signed in as <b>{me?.username}</b> · {me?.role}</div>
        {done ? (
          <div className="tag tag-ok" style={{ padding: '8px 12px' }}>Password changed. Use it next time you sign in.</div>
        ) : (
          <>
            <label className="field">Current password
              <input className="input" type="password" autoComplete="current-password" value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} />
            </label>
            <label className="field">New password
              <input className="input" type="password" autoComplete="new-password" value={form.next} onChange={(e) => setForm({ ...form, next: e.target.value })} />
            </label>
            <label className="field">Repeat new password
              <input className="input" type="password" autoComplete="new-password" value={form.again} onChange={(e) => setForm({ ...form, again: e.target.value })} />
            </label>
            {(problem || error) && <div className="login-error" role="alert">{problem || error}</div>}
          </>
        )}
      </div>
    </Modal>
  )
}
