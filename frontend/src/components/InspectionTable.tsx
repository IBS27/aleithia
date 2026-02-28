import type { InspectionRecord } from '../types/index.ts'

interface Props {
  inspections: InspectionRecord[]
}

function resultBadge(result: string) {
  switch (result) {
    case 'Pass':
      return 'bg-green-500/20 text-green-400 border-green-500/30'
    case 'Fail':
      return 'bg-red-500/20 text-red-400 border-red-500/30'
    case 'Pass w/ Conditions':
      return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
    default:
      return 'bg-gray-500/20 text-gray-400 border-gray-500/30'
  }
}

function riskBadge(risk: string) {
  if (risk.includes('1')) return 'text-red-400'
  if (risk.includes('2')) return 'text-yellow-400'
  return 'text-green-400'
}

export default function InspectionTable({ inspections }: Props) {
  if (inspections.length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 text-center text-gray-500">
        No food inspection data available for this neighborhood.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-300">Food Inspections</h3>
        <span className="text-xs text-gray-500">{inspections.length} records</span>
      </div>

      {inspections.map((insp) => {
        const r = insp.metadata?.raw_record
        if (!r) return null
        const violations = (r.violations || '').split('|').filter(Boolean)

        return (
          <div key={insp.id} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
            <div className="flex items-start justify-between mb-2">
              <div>
                <h4 className="font-semibold text-gray-100">{r.dba_name}</h4>
                <p className="text-xs text-gray-500">{r.address}, {r.city} {r.zip}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs px-2 py-0.5 rounded-full border ${resultBadge(r.results)}`}>
                  {r.results}
                </span>
                <span className={`text-xs font-medium ${riskBadge(r.risk)}`}>
                  {r.risk}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-4 text-xs text-gray-500 mb-2">
              <span>{r.facility_type}</span>
              <span>{r.inspection_type}</span>
              <span>{new Date(r.inspection_date).toLocaleDateString()}</span>
            </div>

            {violations.length > 0 && (
              <details className="mt-2">
                <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-300">
                  {violations.length} violation{violations.length > 1 ? 's' : ''} found
                </summary>
                <div className="mt-2 space-y-1.5">
                  {violations.map((v, i) => (
                    <div key={i} className="text-xs text-gray-500 bg-gray-800 rounded-lg p-2.5 leading-relaxed">
                      {v.trim().substring(0, 300)}
                      {v.trim().length > 300 && '...'}
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )
      })}
    </div>
  )
}
