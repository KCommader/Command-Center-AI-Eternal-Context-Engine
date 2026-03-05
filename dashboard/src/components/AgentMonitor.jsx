const CARD = {
  background: 'rgba(255, 255, 255, 0.03)',
  border: '1px solid rgba(0, 212, 255, 0.1)',
  borderRadius: '12px',
  backdropFilter: 'blur(12px)',
}

// Static list of known connection methods — live tracking needs engine v1.5
const CONNECTIONS = [
  {
    name: 'Claude Code (stdio)',
    desc: 'Connected via ~/.claude/settings.json · MCP stdio transport',
    status: 'active',
    role: 'admin',
  },
  {
    name: 'HTTP MCP clients',
    desc: 'Any agent connecting to port 8766 · Bearer token auth',
    status: 'standby',
    role: 'variable',
  },
  {
    name: 'REST API clients',
    desc: 'Direct calls to engine port 8765 · OMNI_API_KEY required',
    status: 'standby',
    role: 'variable',
  },
]

const STATUS_COLOR = {
  active:  '#22d3a5',
  standby: '#334155',
}

export default function AgentMonitor() {
  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ margin: '0 0 3px', fontSize: '20px', fontWeight: 700, color: '#e2e8f0' }}>
          Agents
        </h1>
        <div style={{ color: '#475569', fontSize: '12px' }}>
          Connected AIs and their access to the engine
        </div>
      </div>

      {/* Connection matrix */}
      <div style={{ ...CARD, padding: '20px', marginBottom: '14px' }}>
        <div style={{ color: '#334155', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '16px' }}>
          Connection Methods
        </div>
        {CONNECTIONS.map((c, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '14px',
              padding: '13px 0',
              borderTop: i > 0 ? '1px solid rgba(255,255,255,0.03)' : 'none',
            }}
          >
            <div style={{
              width: '7px', height: '7px', borderRadius: '50%',
              background: STATUS_COLOR[c.status],
              boxShadow: c.status === 'active' ? `0 0 7px ${STATUS_COLOR[c.status]}` : 'none',
              flexShrink: 0,
            }} />
            <div style={{ flex: 1 }}>
              <div style={{ color: '#cbd5e1', fontSize: '13px', fontWeight: 500 }}>{c.name}</div>
              <div style={{ color: '#475569', fontSize: '12px', marginTop: '2px' }}>{c.desc}</div>
            </div>
            <div style={{
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.06)',
              borderRadius: '6px',
              padding: '3px 10px',
              color: '#64748b',
              fontSize: '11px',
              fontFamily: 'monospace',
              flexShrink: 0,
            }}>
              {c.role}
            </div>
          </div>
        ))}
      </div>

      {/* Live tracking placeholder */}
      <div style={{
        ...CARD,
        padding: '64px 24px',
        textAlign: 'center',
        borderStyle: 'dashed',
        borderColor: 'rgba(0, 212, 255, 0.07)',
      }}>
        <div style={{ fontSize: '28px', marginBottom: '14px', opacity: 0.2 }}>◎</div>
        <div style={{ color: '#64748b', fontWeight: 600, marginBottom: '8px', fontSize: '14px' }}>
          Live activity feed — Phase 2
        </div>
        <div style={{ color: '#334155', fontSize: '13px', maxWidth: '380px', margin: '0 auto', lineHeight: 1.7 }}>
          Will show real-time tool calls, which agent searched what, when memory was stored, and role-based activity logs.
        </div>
        <div style={{ marginTop: '18px', color: '#1e293b', fontSize: '12px', fontFamily: 'monospace' }}>
          requires: GET /agents/activity (engine v1.5)
        </div>
      </div>
    </div>
  )
}
