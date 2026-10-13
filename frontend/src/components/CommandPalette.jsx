import { useEffect, useRef, useState } from 'react'
import { Icons } from './ui'

export function CommandPalette({ pages, actions = [], onNavigate, onClose }) {
  const [query, setQuery] = useState('')
  const [sel, setSel] = useState(0)
  const inputRef = useRef(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  const items = [
    ...pages.map((p) => ({ id: p.id, label: p.label, icon: p.icon, hint: 'Go to page', run: () => onNavigate(p.id) })),
    ...actions,
  ].filter((it) => it.label.toLowerCase().includes(query.toLowerCase()))

  const handleKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(s + 1, items.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)) }
    else if (e.key === 'Enter' && items[sel]) { items[sel].run(); onClose() }
    else if (e.key === 'Escape') onClose()
  }

  return (
    <div className="palette-overlay" onClick={onClose}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          placeholder="Search pages and commands…"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setSel(0) }}
          onKeyDown={handleKey}
        />
        <div className="palette-list">
          {items.map((it, i) => {
            const Icon = it.icon || Icons.search
            return (
              <div
                key={it.id}
                className={`palette-item ${i === sel ? 'sel' : ''}`}
                onMouseEnter={() => setSel(i)}
                onClick={() => { it.run(); onClose() }}
              >
                <Icon />
                <span>{it.label}</span>
                <span className="hint">{it.hint}</span>
              </div>
            )
          })}
          {items.length === 0 && <div className="palette-item">No results for “{query}”</div>}
        </div>
      </div>
    </div>
  )
}
