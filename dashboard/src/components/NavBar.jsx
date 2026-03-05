const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard',      icon: '◈' },
  { id: 'search',    label: 'Memory Search',  icon: '⌕' },
  { id: 'vault',     label: 'Vault Explorer', icon: '⬡' },
  { id: 'agents',    label: 'Agents',         icon: '◎' },
  { id: 'settings',  label: 'Settings',       icon: '⚙' },
]

export default function NavBar({ active, onNavigate }) {
  return (
    <nav style={{
      width: '220px',
      minWidth: '220px',
      background: '#0b1120',
      borderRight: '1px solid rgba(0, 212, 255, 0.07)',
      display: 'flex',
      flexDirection: 'column',
      padding: '0',
    }}>
      {/* Logo */}
      <div style={{ padding: '24px 20px 20px' }}>
        <div style={{
          color: '#00d4ff',
          fontWeight: 700,
          fontSize: '13px',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
        }}>
          Command Center
        </div>
        <div style={{ color: '#334155', fontSize: '11px', marginTop: '3px', letterSpacing: '0.05em' }}>
          Eternal Memory Engine
        </div>
      </div>

      <div style={{ height: '1px', background: 'rgba(0, 212, 255, 0.07)', margin: '0 20px 12px' }} />

      {/* Nav items */}
      <div style={{ flex: 1 }}>
        {NAV_ITEMS.map(item => {
          const isActive = active === item.id
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '10px 20px 10px 18px',
                background: isActive ? 'rgba(0, 212, 255, 0.07)' : 'transparent',
                borderLeft: isActive ? '2px solid #00d4ff' : '2px solid transparent',
                color: isActive ? '#00d4ff' : '#64748b',
                fontSize: '13px',
                fontWeight: isActive ? 600 : 400,
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'color 0.15s, background 0.15s',
              }}
              onMouseEnter={e => { if (!isActive) e.currentTarget.style.color = '#94a3b8' }}
              onMouseLeave={e => { if (!isActive) e.currentTarget.style.color = '#64748b' }}
            >
              <span style={{ fontSize: '15px', width: '18px', textAlign: 'center', flexShrink: 0 }}>
                {item.icon}
              </span>
              {item.label}
            </button>
          )
        })}
      </div>

      {/* Footer */}
      <div style={{ padding: '16px 20px', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
        <div style={{ color: '#1e293b', fontSize: '11px' }}>engine v1.4.0</div>
      </div>
    </nav>
  )
}
