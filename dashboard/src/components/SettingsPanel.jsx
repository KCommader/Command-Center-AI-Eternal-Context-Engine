import { useState } from 'react'
import { apiUrl, apiHeaders } from '../config'

const CARD = {
  background: 'rgba(255, 255, 255, 0.03)',
  border: '1px solid rgba(0, 212, 255, 0.1)',
  borderRadius: '12px',
  backdropFilter: 'blur(12px)',
}

function Row({ label, desc, children }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
      gap: '20px', padding: '16px 0', borderBottom: '1px solid rgba(255,255,255,0.03)',
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ color: '#cbd5e1', fontSize: '13px', fontWeight: 500 }}>{label}</div>
        {desc && <div style={{ color: '#475569', fontSize: '12px', marginTop: '3px', lineHeight: 1.5 }}>{desc}</div>}
      </div>
      <div style={{ flexShrink: 0 }}>{children}</div>
    </div>
  )
}

function Tag({ children, color }) {
  return (
    <span style={{
      background: `${color}14`,
      border: `1px solid ${color}30`,
      color,
      fontSize: '12px',
      padding: '3px 10px',
      borderRadius: '6px',
      fontFamily: 'monospace',
    }}>
      {children}
    </span>
  )
}

export default function SettingsPanel() {
  const [adminResult, setAdminResult] = useState(null)
  const [adminLoading, setAdminLoading] = useState(false)

  const engineUrl  = import.meta.env.VITE_ENGINE_URL || null
  const hasToken   = Boolean(import.meta.env.VITE_API_TOKEN)

  const runAdmin = async (endpoint, label) => {
    setAdminLoading(label)
    setAdminResult(null)
    try {
      const res = await fetch(apiUrl(endpoint), { method: 'POST', headers: apiHeaders() })
      const data = await res.json()
      setAdminResult({ ok: res.ok, msg: data.status ?? JSON.stringify(data) })
    } catch (e) {
      setAdminResult({ ok: false, msg: e.message })
    } finally {
      setAdminLoading(null)
    }
  }

  const btnStyle = (disabled) => ({
    background: 'rgba(0, 212, 255, 0.07)',
    border: '1px solid rgba(0, 212, 255, 0.2)',
    borderRadius: '7px',
    color: disabled ? '#334155' : '#00d4ff',
    fontSize: '12px',
    padding: '6px 14px',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
  })

  return (
    <div>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ margin: '0 0 3px', fontSize: '20px', fontWeight: 700, color: '#e2e8f0' }}>
          Settings
        </h1>
        <div style={{ color: '#475569', fontSize: '12px' }}>
          Dashboard and engine configuration
        </div>
      </div>

      {/* Connection */}
      <div style={{ ...CARD, padding: '20px', marginBottom: '14px' }}>
        <div style={{ color: '#334155', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '4px' }}>
          Connection
        </div>

        <Row
          label="Engine URL"
          desc="Set VITE_ENGINE_URL in dashboard/.env.local. Defaults to localhost:8765 via Vite proxy."
        >
          <Tag color="#00d4ff">{engineUrl ?? 'proxy → localhost:8765'}</Tag>
        </Row>

        <Row
          label="API Token"
          desc="Set VITE_API_TOKEN in dashboard/.env.local when auth is enabled on the engine."
        >
          <Tag color={hasToken ? '#22d3a5' : '#f59e0b'}>{hasToken ? 'configured' : 'not set'}</Tag>
        </Row>
      </div>

      {/* Admin actions */}
      <div style={{ ...CARD, padding: '20px', marginBottom: '14px' }}>
        <div style={{ color: '#334155', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '4px' }}>
          Admin Actions
        </div>

        <Row
          label="Re-index Vault"
          desc="Force a full re-scan and re-embedding of all vault files. Runs in background."
        >
          <button
            style={btnStyle(adminLoading === 'reindex')}
            onClick={() => runAdmin('/admin/reindex', 'reindex')}
            disabled={!!adminLoading}
          >
            {adminLoading === 'reindex' ? 'Starting...' : 'Reindex'}
          </button>
        </Row>

        <Row
          label="Cleanup Temp Files"
          desc="Remove expired capture temp files from the vault."
        >
          <button
            style={btnStyle(adminLoading === 'cleanup')}
            onClick={() => runAdmin('/admin/cleanup', 'cleanup')}
            disabled={!!adminLoading}
          >
            {adminLoading === 'cleanup' ? 'Running...' : 'Cleanup'}
          </button>
        </Row>

        {adminResult && (
          <div style={{
            marginTop: '12px',
            background: adminResult.ok ? 'rgba(34,211,165,0.06)' : 'rgba(248,113,113,0.06)',
            border: `1px solid ${adminResult.ok ? 'rgba(34,211,165,0.2)' : 'rgba(248,113,113,0.2)'}`,
            borderRadius: '8px',
            padding: '10px 14px',
            color: adminResult.ok ? '#22d3a5' : '#f87171',
            fontSize: '13px',
            fontFamily: 'monospace',
          }}>
            {adminResult.msg}
          </div>
        )}
      </div>

      {/* .env.local template */}
      <div style={{ ...CARD, padding: '20px' }}>
        <div style={{ color: '#334155', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '14px' }}>
          dashboard/.env.local template
        </div>
        <div style={{
          background: 'rgba(0,0,0,0.35)',
          borderRadius: '8px',
          padding: '16px 18px',
          fontFamily: 'monospace',
          fontSize: '12px',
          color: '#64748b',
          lineHeight: 2,
        }}>
          <div style={{ color: '#334155' }}># Local (default — no changes needed)</div>
          <div>VITE_ENGINE_URL=<span style={{ color: '#00d4ff' }}>http://localhost:8765</span></div>
          <div>VITE_API_TOKEN=<span style={{ color: '#94a3b8' }}>your-token-here</span></div>
          <div style={{ marginTop: '8px', color: '#334155' }}># Remote / NAS</div>
          <div>VITE_ENGINE_URL=<span style={{ color: '#00d4ff' }}>http://192.168.1.x:8765</span></div>
        </div>
        <div style={{ color: '#334155', fontSize: '12px', marginTop: '10px' }}>
          .env.local is gitignored — safe to store tokens there.
        </div>
      </div>
    </div>
  )
}
