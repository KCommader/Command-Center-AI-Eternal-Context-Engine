import { useState, useEffect, useCallback } from 'react'
import { apiUrl, apiHeaders } from '../config'

const CARD = {
  background: 'rgba(255, 255, 255, 0.03)',
  border: '1px solid rgba(0, 212, 255, 0.1)',
  borderRadius: '12px',
  backdropFilter: 'blur(12px)',
}

const ENDPOINT_COLOR = {
  '/search':          '#00d4ff',
  '/search/grounded': '#00d4ff',
  '/capture':         '#22d3a5',
  '/health':          '#475569',
  '/agents/activity': '#475569',
  '/policy/grounding':'#475569',
  '/admin/reindex':   '#f59e0b',
  '/admin/cleanup':   '#f59e0b',
}

function reltime(isoTs) {
  const diff = Math.floor((Date.now() - new Date(isoTs).getTime()) / 1000)
  if (diff < 5)   return 'just now'
  if (diff < 60)  return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

function AgentDot({ lastSeen }) {
  const age = (Date.now() - new Date(lastSeen).getTime()) / 1000
  const color = age < 30 ? '#22d3a5' : age < 300 ? '#f59e0b' : '#334155'
  const glow  = age < 30 ? `0 0 7px ${color}` : 'none'
  return (
    <div style={{
      width: '7px', height: '7px', borderRadius: '50%',
      background: color, boxShadow: glow, flexShrink: 0,
      transition: 'background 1s',
    }} />
  )
}

export default function AgentMonitor() {
  const [data, setData]       = useState(null)
  const [error, setError]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick]       = useState(0)  // force reltime re-render

  const fetchActivity = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/agents/activity'), { headers: apiHeaders() })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setData(await res.json())
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchActivity()
    const poll   = setInterval(fetchActivity, 5000)
    const ticker = setInterval(() => setTick(t => t + 1), 10000)
    return () => { clearInterval(poll); clearInterval(ticker) }
  }, [fetchActivity])

  const agents = data?.agents ?? []
  const recent = data?.recent ?? []

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <div>
          <h1 style={{ margin: '0 0 3px', fontSize: '20px', fontWeight: 700, color: '#e2e8f0' }}>Agents</h1>
          <div style={{ color: '#475569', fontSize: '12px' }}>
            Live — polls every 5s · {data?.total_logged ?? 0} events logged this session
          </div>
        </div>
        <button
          onClick={fetchActivity}
          style={{
            background: 'rgba(0,212,255,0.07)', border: '1px solid rgba(0,212,255,0.18)',
            borderRadius: '7px', color: '#00d4ff', fontSize: '12px',
            padding: '5px 12px', cursor: 'pointer',
          }}
        >
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          ...CARD, padding: '14px 16px', marginBottom: '14px',
          border: '1px solid rgba(248,113,113,0.2)', color: '#f87171', fontSize: '13px',
        }}>
          {error}
        </div>
      )}

      {/* Connected agents */}
      {!loading && (
        <div style={{ ...CARD, padding: '20px', marginBottom: '14px' }}>
          <div style={{ color: '#334155', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '14px' }}>
            Active Agents ({agents.length})
          </div>

          {agents.length === 0 ? (
            <div style={{ color: '#334155', fontSize: '13px', padding: '12px 0' }}>
              No activity yet — agents appear here as soon as they call the engine.
            </div>
          ) : (
            agents.map((agent, i) => (
              <div
                key={agent.name}
                style={{
                  display: 'flex', alignItems: 'center', gap: '12px',
                  padding: '12px 0',
                  borderTop: i > 0 ? '1px solid rgba(255,255,255,0.03)' : 'none',
                }}
              >
                <AgentDot lastSeen={agent.last_seen} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ color: '#e2e8f0', fontSize: '13px', fontWeight: 500 }}>{agent.name}</div>
                  <div style={{ color: '#475569', fontSize: '12px', marginTop: '2px' }}>
                    Last: <span style={{ color: ENDPOINT_COLOR[agent.last_action] ?? '#94a3b8' }}>
                      {agent.last_action}
                    </span>
                    {' · '}{reltime(agent.last_seen)}
                  </div>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ color: '#00d4ff', fontWeight: 700, fontSize: '14px', fontVariantNumeric: 'tabular-nums' }}>
                    {agent.calls}
                  </div>
                  <div style={{ color: '#334155', fontSize: '11px' }}>calls</div>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Live activity feed */}
      {recent.length > 0 && (
        <div style={{ ...CARD, padding: '20px' }}>
          <div style={{ color: '#334155', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '14px' }}>
            Recent Activity
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
            {recent.map((entry, i) => (
              <div
                key={i}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '80px 1fr 1fr auto',
                  gap: '12px',
                  alignItems: 'center',
                  padding: '7px 0',
                  borderBottom: i < recent.length - 1 ? '1px solid rgba(255,255,255,0.02)' : 'none',
                  fontSize: '12px',
                }}
              >
                <div style={{ color: '#334155', fontFamily: 'monospace', fontSize: '11px' }}>
                  {reltime(entry.ts)}
                </div>
                <div style={{ color: '#64748b', fontFamily: 'monospace' }}>{entry.agent}</div>
                <div style={{ color: ENDPOINT_COLOR[entry.endpoint] ?? '#94a3b8', fontFamily: 'monospace' }}>
                  {entry.endpoint}
                </div>
                {entry.detail ? (
                  <div style={{
                    color: '#475569', fontFamily: 'monospace',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    maxWidth: '200px',
                  }}>
                    {entry.detail}
                  </div>
                ) : <div />}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
