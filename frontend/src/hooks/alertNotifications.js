/** Play alert sound and browser notifications for critical events. */

let audioCtx = null

function getAudioContext() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)()
  }
  return audioCtx
}

const MUTE_KEY = 'aegis.alertsMuted'

export function isAlertSoundMuted() {
  try { return localStorage.getItem(MUTE_KEY) === '1' } catch { return false }
}

export function setAlertSoundMuted(muted) {
  try { localStorage.setItem(MUTE_KEY, muted ? '1' : '0') } catch { /* storage unavailable */ }
}

export function playAlertSound(severity = 'critical') {
  if (isAlertSoundMuted()) return
  try {
    const ctx = getAudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)

    const freq = severity === 'critical' ? 880 : 660
    osc.frequency.value = freq
    osc.type = 'square'
    gain.gain.value = 0.15

    const now = ctx.currentTime
    osc.start(now)
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4)
    osc.stop(now + 0.4)

    if (severity === 'critical') {
      setTimeout(() => {
        const o2 = ctx.createOscillator()
        const g2 = ctx.createGain()
        o2.connect(g2)
        g2.connect(ctx.destination)
        o2.frequency.value = 1100
        o2.type = 'square'
        g2.gain.value = 0.15
        const t = ctx.currentTime
        o2.start(t)
        g2.gain.exponentialRampToValueAtTime(0.001, t + 0.4)
        o2.stop(t + 0.4)
      }, 200)
    }
  } catch {
    /* audio not available */
  }
}

export function requestNotificationPermission() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission()
  }
}

export function showBrowserNotification(title, body) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  try {
    new Notification(title, {
      body,
      icon: '/favicon.svg',
      tag: 'ai-sss-alert',
      requireInteraction: true,
    })
  } catch {
    /* notification blocked */
  }
}

export function flashDocumentTitle(message, durationMs = 8000) {
  const original = document.title
  let on = true
  const interval = setInterval(() => {
    document.title = on ? `🚨 ${message}` : original
    on = !on
  }, 600)
  setTimeout(() => {
    clearInterval(interval)
    document.title = original
  }, durationMs)
}
