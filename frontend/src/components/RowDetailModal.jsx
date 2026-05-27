import StatusBadge from './StatusBadge'

function Detail({ label, value, wide = false }) {
  return (
    <div className={wide ? 'col-span-2' : ''}>
      <p className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">{label}</p>
      <p className="text-sm font-medium text-gray-800 break-words">{value ?? '—'}</p>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 border-b border-gray-100 pb-1">{title}</h3>
      {children}
    </div>
  )
}

export default function RowDetailModal({ row, onClose }) {
  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 sticky top-0 bg-white z-10">
          <div>
            <h2 className="text-base font-bold text-gray-800">Row #{row.id} — Detail</h2>
            <p className="text-xs text-gray-400 mt-0.5">{row.source_type.replace(/_/g, ' ')} · Scope {row.scope}</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl leading-none w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 transition-colors"
          >
            ✕
          </button>
        </div>

        <div className="px-6 py-5 space-y-6">
          {/* Core fields */}
          <Section title="Emission Record">
            <div className="grid grid-cols-2 gap-4">
              <Detail label="Description"     value={row.description} wide />
              <Detail label="Source Reference" value={row.source_reference} />
              <Detail label="Activity"         value={row.activity_value ? `${row.activity_value} ${row.activity_unit}` : null} />
              <Detail label="Emission Factor"  value={row.emission_factor ? `${row.emission_factor} ${row.emission_factor_unit}` : null} />
              <Detail label="CO₂e (MTCO₂e)"   value={row.co2e_mt} />
              <Detail label="Period Start"     value={row.period_start} />
              <Detail label="Period End"       value={row.period_end} />
              <div className="col-span-2 flex items-center gap-3">
                <span className="text-xs text-gray-400 uppercase tracking-wide">Status</span>
                <StatusBadge status={row.status} />
              </div>
              {row.flag_reason && (
                <div className="col-span-2 bg-red-50 border border-red-200 rounded px-3 py-2">
                  <p className="text-xs font-semibold text-red-600 mb-0.5">Flag Reason</p>
                  <p className="text-sm text-red-700">{row.flag_reason}</p>
                </div>
              )}
            </div>
          </Section>

          {/* Raw source data */}
          <Section title="Raw Source Data">
            <pre className="bg-gray-50 border border-gray-200 rounded-md p-3 text-xs text-gray-700 overflow-x-auto">
              {JSON.stringify(row.raw_source_data, null, 2)}
            </pre>
          </Section>

          {/* Normalized data */}
          <Section title="Normalized Data">
            <pre className="bg-gray-50 border border-gray-200 rounded-md p-3 text-xs text-gray-700 overflow-x-auto">
              {JSON.stringify(row.normalized_data, null, 2)}
            </pre>
          </Section>

          {/* Audit trail */}
          <Section title="Audit History">
            {!row.audit_trail?.length
              ? <p className="text-sm text-gray-400">No audit entries yet</p>
              : (
                <div className="space-y-2">
                  {row.audit_trail.map(entry => (
                    <div key={entry.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm bg-gray-50 rounded px-3 py-2">
                      <span className="text-xs text-gray-400 whitespace-nowrap font-mono">
                        {new Date(entry.timestamp).toLocaleString()}
                      </span>
                      <span className="font-semibold text-gray-700">{entry.actor}</span>
                      <span className={`font-medium ${entry.action === 'APPROVED' ? 'text-green-600' : entry.action === 'REJECTED' ? 'text-red-600' : 'text-yellow-600'}`}>
                        {entry.action}
                      </span>
                      <span className="text-gray-400 text-xs">
                        {entry.previous_status} → {entry.new_status}
                      </span>
                      {entry.notes && <span className="text-gray-500 text-xs italic w-full">{entry.notes}</span>}
                    </div>
                  ))}
                </div>
              )
            }
          </Section>
        </div>
      </div>
    </div>
  )
}
