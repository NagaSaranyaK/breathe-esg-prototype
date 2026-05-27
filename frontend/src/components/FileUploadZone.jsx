import { useMemo, useState, useRef } from 'react'
import { apiFetch } from '../api'

const SOURCE_CONFIG = {
  SAP_FUEL:             { label: 'SAP Fuel & Procurement',  url: '/api/upload/sap/'     },
  UTILITY_ELECTRICITY:  { label: 'Utility Electricity',     url: '/api/upload/utility/' },
  CORPORATE_TRAVEL:     { label: 'Corporate Travel',        url: '/api/upload/travel/'  },
}

const SOURCE_FIELDS = {
  SAP_FUEL:            ['DOC_DATE', 'PLANT_CODE', 'MATERIAL_ID', 'QUANTITY', 'UNIT', 'AMOUNT', 'DESCRIPTION'],
  CORPORATE_TRAVEL:    ['TRIP_ID', 'EMPLOYEE_ID', 'EXPENSE_TYPE', 'ORIGIN', 'DESTINATION', 'CABIN_CLASS', 'DISTANCE_MILES', 'NET_COST', 'NIGHTS'],
  UTILITY_ELECTRICITY: ['METER_ID', 'SERVICE_START', 'SERVICE_END', 'USAGE_KWH', 'TARIF_CODE', 'TOTAL_CHG'],
}

const REQUIRED_FIELDS = {
  SAP_FUEL:            ['MATERIAL_ID', 'QUANTITY', 'UNIT'],
  CORPORATE_TRAVEL:    ['DISTANCE_MILES', 'NET_COST'],
  UTILITY_ELECTRICITY: ['USAGE_KWH'],
}

const FIELD_LABELS = {
  DOC_DATE:       'Date',
  PLANT_CODE:     'Plant Code',
  MATERIAL_ID:    'Material',
  QUANTITY:       'Quantity',
  UNIT:           'Unit',
  AMOUNT:         'Amount',
  DESCRIPTION:    'Description',
  TRIP_ID:        'Trip ID',
  EMPLOYEE_ID:    'Employee ID',
  EXPENSE_TYPE:   'Expense Type',
  ORIGIN:         'Origin',
  DESTINATION:    'Destination',
  CABIN_CLASS:    'Travel Class',
  DISTANCE_MILES: 'Distance (miles)',
  NET_COST:       'Amount',
  NIGHTS:         'Nights',
  METER_ID:       'Meter ID',
  SERVICE_START:  'Service Start',
  SERVICE_END:    'Service End',
  USAGE_KWH:      'Usage (kWh)',
  TARIF_CODE:     'Tariff Code',
  TOTAL_CHG:      'Total Charge',
}

function parseCsvHeaderLine(line) {
  const cols = []
  let current = ''
  let inQuotes = false

  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i]
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"'
        i += 1
      } else {
        inQuotes = !inQuotes
      }
    } else if (ch === ',' && !inQuotes) {
      cols.push(current.trim())
      current = ''
    } else {
      current += ch
    }
  }
  cols.push(current.trim())
  return cols.filter(Boolean)
}

function buildDefaultMapping(canonicalFields, headers) {
  const byUpper = new Map(headers.map(h => [h.toUpperCase(), h]))
  const mapping = {}
  canonicalFields.forEach((field) => {
    mapping[field] = byUpper.get(field.toUpperCase()) || ''
  })
  return mapping
}

export default function FileUploadZone({ sourceType, onSuccess }) {
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [selectedFile, setSelectedFile] = useState(null)
  const [headers, setHeaders] = useState([])
  const [mapping, setMapping] = useState({})
  const inputRef = useRef(null)

  const { label, url } = SOURCE_CONFIG[sourceType]
  const canonicalFields = useMemo(() => SOURCE_FIELDS[sourceType] || [], [sourceType])
  const requiredFields  = useMemo(() => REQUIRED_FIELDS[sourceType] || [], [sourceType])
  const optionalFields  = useMemo(
    () => canonicalFields.filter(f => !requiredFields.includes(f)),
    [canonicalFields, requiredFields],
  )

  const isMappingValid = useMemo(() => (
    requiredFields.length > 0 && requiredFields.every(field => mapping[field])
  ), [requiredFields, mapping])

  const resetSelection = () => {
    setSelectedFile(null)
    setHeaders([])
    setMapping({})
    if (inputRef.current) inputRef.current.value = ''
  }

  const prepareFile = async (file) => {
    if (!file) return
    setError(null)
    setResult(null)

    const text = await file.text()
    const firstLine = text.split(/\r?\n/).find(line => line.trim()) || ''
    const parsedHeaders = parseCsvHeaderLine(firstLine)

    if (!parsedHeaders.length) {
      setError('Could not read CSV headers from this file.')
      return
    }

    setSelectedFile(file)
    setHeaders(parsedHeaders)
    setMapping(buildDefaultMapping(canonicalFields, parsedHeaders))
  }

  const upload = async () => {
    if (!selectedFile) return
    if (!isMappingValid) {
      setError('Map all required fields before submitting.')
      return
    }

    const ok = window.confirm(`Submit ${selectedFile.name} for ${label}?`)
    if (!ok) return

    setLoading(true)
    setResult(null)
    setError(null)

    const form = new FormData()
    form.append('file', selectedFile)
    form.append('column_mapping', JSON.stringify(mapping))

    try {
      const res = await apiFetch(url, { method: 'POST', body: form })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
      setResult(data)
      onSuccess()
      resetSelection()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    prepareFile(e.dataTransfer.files[0]).catch(() => {
      setError('Failed to read this CSV file.')
    })
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
      <p className="text-sm font-semibold text-gray-700 mb-3">{label}</p>

      <div
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !loading && inputRef.current?.click()}
        className={`cursor-pointer border-2 border-dashed rounded-md px-4 py-6 text-center transition-colors select-none
          ${dragging  ? 'border-green-500 bg-green-50'
          : loading   ? 'border-gray-200 bg-gray-50 cursor-not-allowed'
                      : 'border-gray-300 hover:border-green-400 hover:bg-green-50'}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={e => {
            prepareFile(e.target.files[0]).catch(() => {
              setError('Failed to read this CSV file.')
            })
          }}
        />
        {loading
          ? <p className="text-sm text-gray-400">Uploading…</p>
          : selectedFile
            ? <p className="text-sm text-gray-700">Selected: <span className="font-medium">{selectedFile.name}</span></p>
            : <p className="text-sm text-gray-500">Drop <span className="font-medium text-gray-700">.csv</span> here or <span className="underline text-green-600">click to browse</span></p>
        }
      </div>

      {selectedFile && headers.length > 0 && (
        <div className="mt-3 rounded-md border border-gray-200">
          <div className="px-3 py-2 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
            <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Map Columns</p>
            <button
              type="button"
              onClick={resetSelection}
              className="text-xs text-gray-500 hover:text-gray-700"
            >
              Change file
            </button>
          </div>

          <div className="p-3 space-y-4">
            {/* Required fields */}
            <div>
              <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                Required <span className="text-red-500">*</span>
              </p>
              <div className="space-y-2">
                {requiredFields.map((field) => (
                  <div key={field} className="grid grid-cols-2 gap-2 items-center">
                    <label className="text-xs font-medium text-gray-700 flex items-center gap-1">
                      {FIELD_LABELS[field] || field}
                      <span className="text-red-500">*</span>
                    </label>
                    <select
                      value={mapping[field] || ''}
                      onChange={(e) => setMapping(prev => ({ ...prev, [field]: e.target.value }))}
                      className="border border-gray-300 rounded px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-green-500"
                    >
                      <option value="">Select column…</option>
                      {headers.map(h => (
                        <option key={h} value={h}>{h}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>

            {/* Optional fields */}
            {optionalFields.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Optional</p>
                <div className="space-y-2">
                  {optionalFields.map((field) => (
                    <div key={field} className="grid grid-cols-2 gap-2 items-center">
                      <label className="text-xs font-medium text-gray-400">{FIELD_LABELS[field] || field}</label>
                      <select
                        value={mapping[field] || ''}
                        onChange={(e) => setMapping(prev => ({ ...prev, [field]: e.target.value }))}
                        className="border border-gray-300 rounded px-2 py-1.5 text-xs bg-white focus:outline-none focus:ring-2 focus:ring-green-500 text-gray-500"
                      >
                        <option value="">— skip —</option>
                        {headers.map(h => (
                          <option key={h} value={h}>{h}</option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <button
              type="button"
              disabled={loading || !isMappingValid}
              onClick={upload}
              className="mt-2 w-full bg-green-700 text-white rounded px-3 py-2 text-sm font-medium hover:bg-green-800 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Confirm & Submit
            </button>
          </div>
        </div>
      )}

      {result && (
        <p className="mt-2 text-xs text-green-700 bg-green-50 border border-green-200 rounded px-3 py-1.5">
          ✓ {result.rows_created} rows imported · {result.flagged_rows} flagged · {result.approved_rows} auto-approved
        </p>
      )}
      {error && (
        <p className="mt-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded px-3 py-1.5">✗ {error}</p>
      )}
    </div>
  )
}
