const STYLES = {
  PENDING:  'bg-yellow-100 text-yellow-800 border-yellow-200',
  FLAGGED:  'bg-red-100 text-red-700 border-red-200',
  APPROVED: 'bg-green-100 text-green-700 border-green-200',
  REJECTED: 'bg-gray-100 text-gray-600 border-gray-200',
}

export default function StatusBadge({ status }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded border text-xs font-semibold tracking-wide ${STYLES[status] || 'bg-gray-100 text-gray-500 border-gray-200'}`}>
      {status}
    </span>
  )
}
