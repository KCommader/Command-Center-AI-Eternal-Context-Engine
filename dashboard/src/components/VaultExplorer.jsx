import { useState, useEffect } from 'react'
import { apiUrl, apiHeaders } from '../config'

const CARD = {
  background: 'rgba(255, 255, 255, 0.03)',
  border: '1px solid rgba(0, 212, 255, 0.1)',
  borderRadius: '12px',
  backdropFilter: 'blur(12px)',
}

export default function VaultExplorer() {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    fetch(apiUrl('/health'), { headers: apiHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(setHealth)
      .catch(() => {})
  }, [])

  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ margin: '0 0 3px', fontSize: '20px', fontWeight: 700, color: '#e2e8f0' }}>
          Vault Explorer
        </h1>
        <div style={{ color: '#475569', fontSize: '12px' }}>Browse and inspect your knowledge vault</div>
      </div>

      {/* Current vault summary */}
      {health && (
        <div style={{ ...CARD, padding: '20px', marginBottom: '14px' }}>
          <div style={{ color: '#334155', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '12px' }}>
            Active Vault
          </div>
          <div style={{ color: '#00d4ff', fontFamily: 'monospace', fontSize: '13px', marginBottom: '6px', wordBreak: 'break-all' }}>
            {health.vault}
          </div>
          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
            <span style={{ color: '#64748b', fontSize: '13px' }}>
              <span style={{ color: '#e2e8f0', fontWeight: 600 }}>{health.files}</span> files
            </span>
            <span style={{ color: '#64748b', fontSize: '13px' }}>
              <span style={{ color: '#e2e8f0', fontWeight: 600 }}>{health.lancedb_rows?.toLocaleString()}</span> vectors
            </span>
            <span style={{ color: '#64748b', fontSize: '13px' }}>
              Last indexed: <span style={{ color: '#94a3b8' }}>
                {health.last_indexed === 'never' ? 'Never' : new Date(health.last_indexed).toLocaleString()}
              </span>
            </span>
          </div>
        </div>
      )}

      {/* Placeholder */}
      <div style={{
        ...CARD,
        padding: '64px 24px',
        textAlign: 'center',
        borderStyle: 'dashed',
        borderColor: 'rgba(0, 212, 255, 0.07)',
      }}>
        <div style={{ fontSize: '28px', marginBottom: '14px', opacity: 0.2 }}>⬡</div>
        <div style={{ color: '#64748b', fontWeight: 600, marginBottom: '8px', fontSize: '14px' }}>
          File browser — Phase 2
        </div>
        <div style={{ color: '#334155', fontSize: '13px', maxWidth: '380px', margin: '0 auto', lineHeight: 1.7 }}>
          Full tree view with inline Markdown preview. Until then, open the vault directly in Obsidian.
        </div>
        <div style={{ marginTop: '18px', color: '#1e293b', fontSize: '12px', fontFamily: 'monospace' }}>
          requires: GET /vault/files (engine v1.5)
        </div>
      </div>
    </div>
  )
}
