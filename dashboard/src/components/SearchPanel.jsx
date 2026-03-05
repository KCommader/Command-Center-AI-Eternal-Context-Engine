import { useState, useRef, useCallback } from 'react'
import { apiUrl, apiHeaders } from '../config'

const CARD = {
  background: 'rgba(255, 255, 255, 0.03)',
  border: '1px solid rgba(0, 212, 255, 0.1)',
  borderRadius: '12px',
  backdropFilter: 'blur(12px)',
}

const VERDICT_COLOR = {
  grounded:             '#22d3a5',
  weak_grounding:       '#f59e0b',
  low_confidence:       '#f59e0b',
  insufficient_context: '#f87171',
}

function ResultCard({ result, index }) {
  const [expanded, setExpanded] = useState(false)
  const text = result.text ?? result.content ?? ''
  const score = result._distance !== undefined
    ? (1 - result._distance).toFixed(3)
    : result.score?.toFixed(3) ?? '—'

  return (
    <div
      onClick={() => setExpanded(v => !v)}
      style={{
        ...CARD,
        padding: '16px',
        cursor: 'pointer',
        transition: 'border-color 0.15s',
        borderColor: expanded ? 'rgba(0, 212, 255, 0.28)' : 'rgba(0, 212, 255, 0.1)',
      }}
    >
      <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Badges */}
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '8px' }}>
            <span style={{
              background: 'rgba(0, 212, 255, 0.1)', color: '#00d4ff',
              fontSize: '11px', padding: '2px 8px', borderRadius: '99px', fontWeight: 600,
            }}>
              #{index + 1}
            </span>
            {result.namespace && (
              <span style={{
                background: 'rgba(255,255,255,0.05)', color: '#64748b',
                fontSize: '11px', padding: '2px 8px', borderRadius: '99px',
              }}>
                {result.namespace}
              </span>
            )}
            {result.tier && (
              <span style={{
                background: 'rgba(34, 211, 165, 0.08)', color: '#22d3a5',
                fontSize: '11px', padding: '2px 8px', borderRadius: '99px',
              }}>
                {result.tier}
              </span>
            )}
          </div>

          {/* Text */}
          <p style={{
            margin: 0,
            color: '#cbd5e1',
            fontSize: '13px',
            lineHeight: 1.6,
            overflow: expanded ? 'visible' : 'hidden',
            display: expanded ? 'block' : '-webkit-box',
            WebkitLineClamp: expanded ? 'unset' : 3,
            WebkitBoxOrient: 'vertical',
          }}>
            {text}
          </p>

          {result.source && (
            <div style={{ marginTop: '8px', color: '#334155', fontSize: '11px', fontFamily: 'monospace' }}>
              {result.source}
            </div>
          )}
        </div>

        {/* Score */}
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ color: '#00d4ff', fontWeight: 700, fontSize: '14px', fontVariantNumeric: 'tabular-nums' }}>
            {score}
          </div>
          <div style={{ color: '#334155', fontSize: '11px' }}>score</div>
        </div>
      </div>
    </div>
  )
}

export default function SearchPanel() {
  const [query, setQuery]   = useState('')
  const [topK, setTopK]     = useState(10)
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState(null)
  const abortRef = useRef(null)

  const search = useCallback(async () => {
    if (!query.trim()) return
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()
    setLoading(true)
    setError(null)

    try {
      const res = await fetch(apiUrl('/search'), {
        method: 'POST',
        headers: apiHeaders(),
        body: JSON.stringify({ query: query.trim(), k: topK }),
        signal: abortRef.current.signal,
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setResults(data)
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [query, topK])

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ margin: '0 0 3px', fontSize: '20px', fontWeight: 700, color: '#e2e8f0' }}>
          Memory Search
        </h1>
        <div style={{ color: '#475569', fontSize: '12px' }}>
          Semantic search across the full vault
        </div>
      </div>

      {/* Search bar */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px', alignItems: 'center' }}>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && search()}
          placeholder="Search memory... (Enter to search)"
          autoFocus
          style={{
            flex: 1,
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(0, 212, 255, 0.18)',
            borderRadius: '10px',
            padding: '11px 16px',
            color: '#e2e8f0',
            fontSize: '14px',
            outline: 'none',
          }}
          onFocus={e  => e.target.style.borderColor = 'rgba(0, 212, 255, 0.45)'}
          onBlur={e   => e.target.style.borderColor = 'rgba(0, 212, 255, 0.18)'}
        />

        <select
          value={topK}
          onChange={e => setTopK(Number(e.target.value))}
          style={{
            background: '#0b1120',
            border: '1px solid rgba(0, 212, 255, 0.12)',
            borderRadius: '10px',
            padding: '11px 12px',
            color: '#64748b',
            fontSize: '13px',
            cursor: 'pointer',
            outline: 'none',
          }}
        >
          {[5, 10, 20, 50].map(n => (
            <option key={n} value={n}>{n} results</option>
          ))}
        </select>

        <button
          onClick={search}
          disabled={loading || !query.trim()}
          style={{
            background: 'rgba(0, 212, 255, 0.1)',
            border: '1px solid rgba(0, 212, 255, 0.25)',
            borderRadius: '10px',
            padding: '11px 20px',
            color: '#00d4ff',
            fontSize: '13px',
            fontWeight: 600,
            cursor: loading || !query.trim() ? 'not-allowed' : 'pointer',
            opacity: loading || !query.trim() ? 0.45 : 1,
            transition: 'opacity 0.15s',
            whiteSpace: 'nowrap',
          }}
        >
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>

      {/* Grounding verdict */}
      {results?.grounding && (
        <div style={{
          background: 'rgba(255,255,255,0.02)',
          border: `1px solid ${VERDICT_COLOR[results.grounding.verdict] ?? '#475569'}22`,
          borderRadius: '8px',
          padding: '10px 14px',
          marginBottom: '14px',
          display: 'flex',
          gap: '14px',
          alignItems: 'center',
          flexWrap: 'wrap',
        }}>
          <span style={{ color: '#475569', fontSize: '12px' }}>Verdict</span>
          <span style={{
            color: VERDICT_COLOR[results.grounding.verdict] ?? '#94a3b8',
            fontWeight: 600,
            fontSize: '13px',
          }}>
            {results.grounding.verdict}
          </span>
          {results.grounding.confidence !== undefined && (
            <span style={{ color: '#475569', fontSize: '12px' }}>
              Confidence: <span style={{ color: '#94a3b8' }}>
                {(results.grounding.confidence * 100).toFixed(0)}%
              </span>
            </span>
          )}
          <span style={{ color: '#334155', fontSize: '12px', marginLeft: 'auto' }}>
            {results.results?.length ?? 0} results
          </span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{
          background: 'rgba(248, 113, 113, 0.05)',
          border: '1px solid rgba(248, 113, 113, 0.2)',
          borderRadius: '8px',
          padding: '12px 16px',
          color: '#f87171',
          fontSize: '13px',
          marginBottom: '14px',
        }}>
          Search failed: {error}
        </div>
      )}

      {/* Results list */}
      {results?.results && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {results.results.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#334155', padding: '48px 0', fontSize: '14px' }}>
              No results found for &ldquo;{query}&rdquo;
            </div>
          ) : (
            results.results.map((r, i) => <ResultCard key={i} result={r} index={i} />)
          )}
        </div>
      )}
    </div>
  )
}
