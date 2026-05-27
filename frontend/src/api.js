const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export const getTenantId = () => localStorage.getItem('tenantId')

export const apiFetch = (url, options = {}) =>
  fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'X-Tenant-ID': getTenantId() ?? '',
      ...(options.headers || {}),
    },
  })

export const login = (tenantId, username, password) =>
  fetch(`${API_BASE}/api/auth/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tenant_id: tenantId, username, password }),
  })

export const logout = () => {
  localStorage.removeItem('tenantId')
  window.location.reload()
}
