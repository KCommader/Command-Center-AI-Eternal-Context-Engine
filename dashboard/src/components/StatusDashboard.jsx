import { useState, useEffect, useCallback } from 'react'
import { apiUrl, apiHeaders } from '../config'

const CARD = {
  background: 'rgba(255, 255, 255, 0.03)',
  border: '1px solid rgba(0, 212, 255, 0.1)',
  borderRadius: '12px',
  backdropFilter: 'blur(12px)',
}

function StatCard({ label, value, sub, accent }) {
  return (
    <div style={{ ...CARD, padding: '20px' }}>
      <div style={{ color: '#475569', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '10px' }}>
        {label}
      </div>
      <div style={{ color: accent || '#e2e8f0', fontSize: '26px', fontWeight: 700, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>
        {value ?? '—'}
      </div>
      {sub && (
        <div style={{ color: '#475569', fontSize: '12px', marginTop: '6px' }}>{sub}</div>
      )}
    </div>
  )
}

export default function StatusDashboard() {
  const [health, setHealth] = useState(null)
  const [error, setError]   = useState(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/health'), { headers: apiHeaders() })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setHealth(data)
      setError(null)
      setLastUpdated(new Date())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchHealth()
    const t = setInterval(fetchHealth, 15000)
    return () => clearInterval(t)
  }, [fetchHealth])

  const isOnline = health?.status === 'online'

  const dotColor = loading ? '#334155' : isOnline ? '#22d3a5' : '#f87171'
  const statusLabel = loading
    ? 'Connecting...'
    : isOnline
    ? 'Engine Online'
    : `Offline — ${error}`

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '28px' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#e2e8f0' }}>Dashboard</h1>
          <div style={{ color: '#475569', fontSize: '12px', marginTop: '3px' }}>
            {lastUpdated ? `Last refreshed ${lastUpdated.toLocaleTimeString()}` : 'Connecting to engine...'}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: '7px', height: '7px', borderRadius: '50%',
            background: dotColor,
            boxShadow: isOnline ? `0 0 8px ${dotColor}` : 'none',
            transition: 'all 0.3s',
          }} />
          <span style={{ fontSize: '13px', color: dotColor }}>{statusLabel}</span>
          <button
            onClick={fetchHealth}
            style={{
              background: 'rgba(0, 212, 255, 0.07)',
              border: '1px solid rgba(0, 212, 255, 0.18)',
              borderRadius: '7px',
              color: '#00d4ff',
              fontSize: '12px',
              padding: '5px 12px',
              cursor: 'pointer',
            }}
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Stat cards */}
      {health && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: '14px', marginBottom: '24px' }}>
          <StatCard
            label="Vault Files"
            value={health.files}
            sub="Markdown files indexed"
            accent="#00d4ff"
          />
          <StatCard
            label="Memory Vectors"
            value={health.lancedb_rows?.toLocaleString()}
            sub="LanceDB embeddings"
          />
          <StatCard
            label="Cache"
            value={health.query_cache_items}
            sub={`of ${health.query_cache_max_items} max · TTL ${health.query_cache_ttl_sec}s`}
          />
          <StatCard
            label="Auth"
            value={health.auth_enabled ? 'Enabled' : 'Open'}
            sub={health.auth_enabled ? 'Bearer tokens active' : 'No auth configured'}
            accent={health.auth_enabled ? '#22d3a5' : '#f59e0b'}
          />
        </div>
      )}

      {/* Details */}
      {health && (
        <div style={{ ...CARD, padding: '22px' }}>
          <div style={{ color: '#334155', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '18px' }}>
            Engine Details
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px' }}>
            {[
              ['Vault Path',      health.vault],
              ['Last Indexed',    health.last_indexed === 'never' ? 'Never' : new Date(health.last_indexed).toLocaleString()],
              ['Search Mode',     health.default_search_mode],
              ['Reranker',        health.reranker_enabled ? 'Active' : 'Disabled'],
              ['Answer Contract', health.enforce_answer_contract_default ? 'Enforced' : 'Relaxed'],
              ['Tmp TTL',         `${health.tmp_ttl_sec}s · max ${health.tmp_max_files} files`],
            ].map(([k, v]) => (
              <div key={k}>
                <div style={{ color: '#475569', fontSize: '11px', marginBottom: '3px' }}>{k}</div>
                <div style={{ color: '#94a3b8', fontSize: '13px', fontFamily: 'monospace', wordBreak: 'break-all' }}>
                  {String(v)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Offline state */}
      {!loading && !health && (
        <div style={{
          ...CARD, padding: '48px 24px',
          border: '1px solid rgba(248, 113, 113, 0.15)',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: '28px', marginBottom: '14px', opacity: 0.4 }}>⚠</div>
          <div style={{ color: '#f87171', fontWeight: 600, marginBottom: '8px' }}>Engine Unreachable</div>
          <div style={{ color: '#64748b', fontSize: '13px' }}>{error}</div>
          <div style={{ marginTop: '16px', color: '#334155', fontSize: '12px', fontFamily: 'monospace' }}>
            python engine/omniscience.py start
          </div>
        </div>
      )}
    </div>
  )
}
