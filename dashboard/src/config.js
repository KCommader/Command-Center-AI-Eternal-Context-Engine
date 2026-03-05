// Engine connection config
// Override in dashboard/.env.local — never commit that file
export const ENGINE_URL = import.meta.env.VITE_ENGINE_URL ?? ''
export const API_TOKEN  = import.meta.env.VITE_API_TOKEN  ?? ''

export function apiHeaders() {
  const h = { 'Content-Type': 'application/json' }
  if (API_TOKEN) h['Authorization'] = `Bearer ${API_TOKEN}`
  return h
}

// In dev: routes through Vite proxy to http://localhost:8765
// In prod: set VITE_ENGINE_URL or serve dashboard from same origin as engine
export function apiUrl(path) {
  return ENGINE_URL ? `${ENGINE_URL}${path}` : `/api${path}`
}
