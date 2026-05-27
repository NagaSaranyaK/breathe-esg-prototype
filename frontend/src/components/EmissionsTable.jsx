import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api'
import StatusBadge from './StatusBadge'
import RowDetailModal from './RowDetailModal'

const TABS = [
  { label: 'All',          value: ''             },
  { label: 'Needs Review', value: 'needs_review' },
  { label: 'Approved',     value: 'APPROVED'     },
  { label: 'Rejected',     value: 'REJECTED'     },
]

const SOURCES = [
  { label: 'All Sources', value: '' },
  { label: 'SAP Fuel',    value: 'SAP_FUEL' },
  { label: 'Utility',     value: 'UTILITY_ELECTRICITY' },
  { label: 'Travel',      value: 'CORPORATE_TRAVEL' },
]

const SCOPE_LABELS = { 1: 'Scope 1', 2: 'Scope 2', 3: 'Scope 3' }

export default function EmissionsTable({ tenantId, refreshKey, onAction }) {
  const [tab, setTab] = useState('')
  const [source, setSource] = useState('')
  const [page, setPage] = useState(0)
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedRow, setSelectedRow] = useState(null)
  const [actionLoading, setActionLoading] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [toast, setToast] = useState(null)  // { message, type: 'success'|'error' }

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }, [])

  const fetchRows = useCallback(() => {
    if (!tenantId) return
    setLoading(true)
    setActionError(null)
    const qs = tab ? `?status=${tab}` : ''
    apiFetch(`/api/emissions/${qs}`)
      .then(r => r.json())
      .then(data => { setRows(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [tenantId, tab, refreshKey])

  useEffect(() => { fetchRows() }, [fetchRows])

  const handleAction = async (e, rowId, action) => {
    e.stopPropagation()
    setActionLoading(rowId)
    setActionError(null)
    try {
      const res = await apiFetch(`/api/emissions/${rowId}/${action}/`, { method: 'POST' })
      let payload = null
      try { payload = await res.json() } catch { /* non-JSON body */ }

      if (!res.ok) {
        const msg = payload?.error || payload?.detail || payload?.message
          || `Failed to ${action} row (HTTP ${res.status})`
        setActionError(msg)
        return
      }

      fetchRows()
      onAction()
      setSelectedRow(prev => prev?.id === rowId ? null : prev)
      showToast(`Row #${rowId} ${action === 'approve' ? 'approved' : 'rejected'} successfully`, action === 'approve' ? 'success' : 'reject')
    } catch (err) {
      const msg = err.message || `Failed to ${action} this row — network error`
      setActionError(msg)
      showToast(msg, 'error')
    } finally {
      setActionLoading(null)
    }
  }

  const displayRows = source ? rows.filter(r => r.source_type === source) : rows
  const tabCounts = displayRows.length

  const PAGE_SIZE = 50
  const totalPages = Math.max(1, Math.ceil(displayRows.length / PAGE_SIZE))
  const safePage = Math.min(page, totalPages - 1)
  const pageRows = displayRows.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE)

  return (
    <>
    {toast && (
      <div className={`fixed bottom-5 right-5 z-50 flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm font-medium transition-all
        ${toast.type === 'success'
          ? 'bg-green-700 text-white'
          : toast.type === 'reject'
          ? 'bg-red-600 text-white'
          : 'bg-red-800 text-white'}`}>
        <span>{toast.type === 'success' ? '✓' : '✗'}</span>
        {toast.message}
      </div>
    )}
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
      {/* Tab bar */}
      <div className="px-4 pt-3 border-b border-gray-200 flex items-center gap-1 flex-wrap">
        {TABS.map(t => (
          <button
            key={t.value}
            onClick={() => { setTab(t.value); setPage(0) }}
            className={`px-4 py-2 text-sm font-medium rounded-t-md transition-colors
              ${tab === t.value
                ? 'text-green-700 border-b-2 border-green-600 bg-white -mb-px'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'}`}
          >
            {t.label}
          </button>
        ))}

        {/* Source filter pills */}
        <div className="ml-auto flex items-center gap-1 pb-1">
          {SOURCES.map(s => (
            <button
              key={s.value}
              onClick={() => { setSource(s.value); setPage(0) }}
              className={`px-2.5 py-1 text-xs font-medium rounded-full border transition-colors
                ${source === s.value
                  ? 'bg-green-700 text-white border-green-700'
                  : 'bg-white text-gray-500 border-gray-300 hover:border-green-400 hover:text-green-700'}`}
            >
              {s.label}
            </button>
          ))}
          <span className="ml-2 text-xs text-gray-400 pr-1">{tabCounts} row{tabCounts !== 1 ? 's' : ''}</span>
        </div>
      </div>

      {actionError && (
        <div className="mx-4 mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {actionError}
        </div>
      )}

      {loading && (
        <div className="py-12 text-center text-sm text-gray-400 animate-pulse">Loading emissions…</div>
      )}

      {!loading && displayRows.length === 0 && (
        <div className="py-12 text-center text-sm text-gray-400">No records found for this filter</div>
      )}

      {!loading && displayRows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {['Source', 'Scope', 'Description', 'Source Ref', 'Activity', 'CO₂e (MT)', 'Status', 'Flag Reason', 'Actions'].map(h => (
                  <th
                    key={h}
                    className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {pageRows.map(row => (
                <tr
                  key={row.id}
                  className="hover:bg-gray-50 cursor-pointer transition-colors"
                  onClick={() => setSelectedRow(row)}
                >
                  <td className="px-3 py-2 whitespace-nowrap font-medium text-gray-700">
                    {row.source_type.replace(/_/g, ' ')}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-gray-500">
                    {SCOPE_LABELS[row.scope] || row.scope}
                  </td>
                  <td className="px-3 py-2 max-w-[200px] truncate text-gray-600" title={row.description}>
                    {row.description}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-gray-500 whitespace-nowrap">
                    {row.source_reference}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap tabular-nums text-gray-600">
                    {row.activity_value
                      ? `${Number(row.activity_value).toLocaleString()} ${row.activity_unit}`
                      : '—'}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap tabular-nums font-medium">
                    {row.co2e_mt != null ? Number(row.co2e_mt).toFixed(4) : '—'}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <StatusBadge status={row.status} />
                  </td>
                  <td
                    className="px-3 py-2 max-w-[220px] truncate text-xs text-red-600"
                    title={row.flag_reason || ''}
                  >
                    {row.flag_reason || ''}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap" onClick={e => e.stopPropagation()}>
                    {row.locked_at
                      ? <span className="text-xs text-gray-400 italic">Locked</span>
                      : (
                        <div className="flex gap-1">
                          <button
                            disabled={actionLoading === row.id}
                            onClick={e => handleAction(e, row.id, 'approve')}
                            className="px-2 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 transition-colors"
                          >
                            Approve
                          </button>
                          <button
                            disabled={actionLoading === row.id}
                            onClick={e => handleAction(e, row.id, 'reject')}
                            className="px-2 py-1 text-xs bg-red-100 text-red-700 border border-red-200 rounded hover:bg-red-200 disabled:opacity-50 transition-colors"
                          >
                            Reject
                          </button>
                        </div>
                      )
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {displayRows.length > PAGE_SIZE && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50 text-sm">
          <span className="text-gray-500">
            Showing {safePage * PAGE_SIZE + 1}–{Math.min((safePage + 1) * PAGE_SIZE, displayRows.length)} of {displayRows.length} rows
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={safePage === 0}
              className="px-3 py-1 text-xs font-medium rounded border border-gray-300 bg-white text-gray-600 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              ← Previous
            </button>
            <span className="text-gray-500 tabular-nums">Page {safePage + 1} of {totalPages}</span>
            <button
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={safePage >= totalPages - 1}
              className="px-3 py-1 text-xs font-medium rounded border border-gray-300 bg-white text-gray-600 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Next →
            </button>
          </div>
        </div>
      )}

      {selectedRow && (
        <RowDetailModal row={selectedRow} onClose={() => setSelectedRow(null)} />
      )}
    </div>
    </>
  )
}
