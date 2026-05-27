import { useState, useEffect } from 'react'
import { apiFetch } from '../api'

const SOURCE_LABELS = {
  SAP_FUEL:            'SAP Fuel',
  UTILITY_ELECTRICITY: 'Utility',
  CORPORATE_TRAVEL:    'Travel',
}

const STATUS_STYLES = {
  COMPLETE:   'text-green-600 font-medium',
  PROCESSING: 'text-yellow-600 font-medium',
  FAILED:     'text-red-600 font-medium',
}

export default function IngestionLogTable({ tenantId, refreshKey }) {
  const [logs, setLogs] = useState([])

  useEffect(() => {
    if (!tenantId) return
    apiFetch('/api/ingestion-logs/')
      .then(r => r.json())
      .then(setLogs)
      .catch(console.error)
  }, [tenantId, refreshKey])

  if (!logs.length) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-sm text-gray-400 shadow-sm">
        No uploads yet
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm">
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Source</th>
            <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">File</th>
            <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Rows</th>
            <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Uploaded</th>
            <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {logs.map(log => (
            <tr key={log.id} className="hover:bg-gray-50 transition-colors">
              <td className="px-4 py-2 font-medium">{SOURCE_LABELS[log.source_type] || log.source_type}</td>
              <td className="px-4 py-2 text-gray-500 max-w-[160px] truncate" title={log.file_name}>{log.file_name}</td>
              <td className="px-4 py-2 text-right tabular-nums">{log.row_count}</td>
              <td className="px-4 py-2 text-gray-500 whitespace-nowrap">{new Date(log.uploaded_at).toLocaleString()}</td>
              <td className={`px-4 py-2 ${STATUS_STYLES[log.status] || 'text-gray-600'}`}>{log.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
