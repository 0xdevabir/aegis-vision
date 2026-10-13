import { Icons, Tag, SEVERITY_TONE, timeAgo, Empty } from './ui'

export function NotificationDrawer({ events, onClose, onClear }) {
  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="drawer">
        <div className="drawer-head">
          <span>Notification Center</span>
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn btn-sm btn-ghost" onClick={onClear}>Clear all</button>
            <button className="icon-btn" onClick={onClose}><Icons.close /></button>
          </div>
        </div>
        <div className="drawer-body">
          {events.length === 0 && <Empty icon={Icons.bell}>No notifications yet</Empty>}
          {events.map((evt, i) => (
            <div key={i} className={`row ${evt.severity === 'critical' ? 'crit' : ''}`}>
              <div>
                <b style={{ fontSize: '0.84rem' }}>{evt.type?.replace(/_/g, ' ')}</b>
                <div className="meta">{evt.msg}</div>
                <div className="meta">{evt.camera || 'Unknown camera'} · {timeAgo(evt.time)}</div>
              </div>
              <Tag tone={SEVERITY_TONE[evt.severity] || 'muted'}>{evt.severity}</Tag>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
