import { useState } from 'react'
import { login } from '../api'

export default function LoginPage({ onLoginSuccess }) {
  const [tenantId, setTenantId]   = useState('')
  const [username, setUsername]   = useState('')
  const [password, setPassword]   = useState('')
  const [error, setError]         = useState(null)
  const [loading, setLoading]     = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)

    const id = parseInt(tenantId, 10)
    if (!Number.isInteger(id) || id <= 0) {
      setError('Tenant ID must be a positive integer.')
      return
    }

    setLoading(true)
    try {
      const res  = await login(id, username, password)
      const data = await res.json()

      if (!res.ok) {
        setError(data.error || 'Login failed.')
        return
      }

      localStorage.setItem('tenantId', data.tenant_id)
      onLoginSuccess(data.tenant_id)
    } catch {
      setError('Network error — is the server running?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Card */}
        <div className="bg-white rounded-2xl shadow-lg p-8 border border-gray-100">
          {/* Logo area */}
          <div className="flex items-center gap-2 mb-6">
            <span className="text-2xl">🌿</span>
            <div>
              <h1 className="text-lg font-bold text-green-700 leading-none">Breathe ESG</h1>
              <p className="text-xs text-gray-400 mt-0.5">Mini Ingest Portal</p>
            </div>
          </div>

          <h2 className="text-base font-semibold text-gray-800 mb-5">Sign in to your tenant</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Tenant ID
              </label>
              <input
                type="number"
                min="1"
                step="1"
                value={tenantId}
                onChange={e => setTenantId(e.target.value)}
                placeholder="e.g. 1"
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="test-1"
                required
                autoComplete="username"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="pass-1"
                required
                autoComplete="current-password"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
              />
            </div>

            {error && (
              <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-green-700 text-white rounded-lg px-4 py-2.5 text-sm font-medium
                         hover:bg-green-800 active:bg-green-900 transition-colors
                         disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <p className="mt-5 text-center text-xs text-gray-400">
            Use <span className="font-mono">test-&#123;id&#125;</span> /{' '}
            <span className="font-mono">pass-&#123;id&#125;</span> for any integer ID
          </p>
        </div>
      </div>
    </div>
  )
}
