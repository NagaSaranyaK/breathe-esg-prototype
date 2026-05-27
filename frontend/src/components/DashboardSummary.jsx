import { useState, useEffect } from 'react'
import { apiFetch } from '../api'

function StatCard({ label, value, colorClasses }) {
  return (
    <div className={`rounded-lg border p-4 flex flex-col gap-1 ${colorClasses}`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</p>
      <p className="text-2xl font-bold text-gray-800">{value}</p>
    </div>
  )
}

export default function DashboardSummary({ tenantId, refreshKey }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    if (!tenantId) return
    apiFetch('/api/dashboard/')
      .then(r => r.json())
      .then(setData)
      .catch(console.error)
  }, [tenantId, refreshKey])

  if (!data) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 animate-pulse">
        {Array(6).fill(0).map((_, i) => (
          <div key={i} className="h-20 bg-gray-200 rounded-lg" />
        ))}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      <StatCard label="Total Rows"    value={data.total_rows}              colorClasses="bg-white border-gray-200" />
      <StatCard label="Needs Review"  value={data.needs_review}            colorClasses="bg-yellow-50 border-yellow-200" />
      <StatCard label="Flagged"       value={data.flagged}                  colorClasses="bg-red-50 border-red-200" />
      <StatCard label="Approved"      value={data.approved}                 colorClasses="bg-green-50 border-green-200" />
      <StatCard label="Rejected"      value={data.rejected}                 colorClasses="bg-gray-50 border-gray-200" />
      <StatCard label="Total MTCO₂e"  value={Number(data.total_co2e_mt).toFixed(2)} colorClasses="bg-blue-50 border-blue-200" />
    </div>
  )
}
