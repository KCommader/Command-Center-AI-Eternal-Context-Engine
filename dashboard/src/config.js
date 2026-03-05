// Engine connection config
// Override in dashboard/.env.local — never commit that file
export const ENGINE_URL = import.meta.env.VITE_ENGINE_URL ?? ''
export const API_TOKEN  = import.meta.env.VITE_API_TOKEN  ?? ''

export function apiHeaders() {
  const h = { 'Content-Type': 'application/json' }
  if (API_TOKEN) h['Authorization'] = `Bearer ${API_TOKEN}`
  return h
}

// Dev:  Vite proxy strips /api → calls localhost:8765 directly
// Prod: served by engine on same origin → no prefix needed
// Remote: set VITE_ENGINE_URL=http://x.x.x.x:8765 in .env.local
export function apiUrl(path) {
  if (ENGINE_URL) return `${ENGINE_URL}${path}`
  if (import.meta.env.DEV) return `/api${path}`
  return path  // same origin — engine serves both API and dashboard
}
