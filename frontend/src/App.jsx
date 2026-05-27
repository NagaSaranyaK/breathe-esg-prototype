import { useState, useCallback } from 'react'
import LoginPage from './components/LoginPage'
import DashboardSummary from './components/DashboardSummary'
import FileUploadZone from './components/FileUploadZone'
import IngestionLogTable from './components/IngestionLogTable'
import EmissionsTable from './components/EmissionsTable'
import { logout } from './api'

function App() {
  const [tenantId, setTenantId] = useState(() => localStorage.getItem('tenantId'))
  const [refreshKey, setRefreshKey] = useState(0)

  const refresh = useCallback(() => setRefreshKey(k => k + 1), [])

  if (!tenantId) {
    return <LoginPage onLoginSuccess={(id) => setTenantId(String(id))} />
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-green-700 text-white shadow-md">
        <div className="max-w-screen-xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight">Breathe ESG — Mini Ingest Portal</h1>
            <p className="text-green-200 text-sm mt-0.5">Carbon Emissions Data Ingestion &amp; Review</p>
          </div>
          <div className="flex items-center gap-4">
            <span className="hidden sm:block text-green-300 text-xs font-mono uppercase tracking-widest">
              Tenant {tenantId}
            </span>
            <button
              onClick={logout}
              className="text-xs bg-green-800 hover:bg-green-900 text-white px-3 py-1.5 rounded-lg transition-colors"
            >
              Log out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-screen-xl mx-auto px-6 py-6 space-y-6">
        {/* Dashboard KPIs */}
        <DashboardSummary tenantId={tenantId} refreshKey={refreshKey} />

        {/* Upload panels + Ingestion log side by side */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-4">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Upload Data</h2>
            <FileUploadZone sourceType="SAP_FUEL"            onSuccess={refresh} />
            <FileUploadZone sourceType="UTILITY_ELECTRICITY" onSuccess={refresh} />
            <FileUploadZone sourceType="CORPORATE_TRAVEL"    onSuccess={refresh} />
          </div>
          <div className="space-y-4">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Recent Uploads</h2>
            <IngestionLogTable tenantId={tenantId} refreshKey={refreshKey} />
          </div>
        </div>

        {/* Emissions review table */}
        <div>
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">Emissions Review</h2>
          <EmissionsTable tenantId={tenantId} refreshKey={refreshKey} onAction={refresh} />
        </div>
      </main>
    </div>
  )
}

export default App
