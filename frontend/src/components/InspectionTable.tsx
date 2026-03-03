import type { InspectionRecord } from '../types/index.ts'

interface Props {
  inspections: InspectionRecord[]
}

function resultStyle(result: string) {
  switch (result) {
    case 'Pass': return 'text-green-400/80 border-green-500/20'
    case 'Fail': return 'text-red-400/80 border-red-500/20'
    case 'Pass w/ Conditions': return 'text-yellow-400/80 border-yellow-500/20'
    default: return 'text-white/30 border-white/[0.06]'
  }
}

function riskStyle(risk: string) {
  if (risk.includes('1')) return 'text-red-400/80'
  if (risk.includes('2')) return 'text-yellow-400/80'
  return 'text-green-400/80'
}

export default function InspectionTable({ inspections }: Props) {
  if (inspections.length === 0) {
    return (
      <div className="border border-white/[0.06] p-8 text-center text-xs font-mono text-white/20 uppercase tracking-wider">
        No food inspection data available
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30">Food Inspections</h3>
        <span className="text-[10px] font-mono text-white/15">{inspections.length} records</span>
      </div>

      {inspections.map((insp) => {
        const r = insp.metadata?.raw_record
        if (!r) return null
        const violations = (r.violations || '').split('|').filter(Boolean)

        return (
          <div key={insp.id} className="border border-white/[0.06] bg-white/[0.01] p-4">
            <div className="flex items-start justify-between mb-2">
              <div>
                <h4 className="text-sm font-semibold text-white">{r.dba_name}</h4>
                <p className="text-[10px] font-mono text-white/20 mt-0.5">{r.address}, {r.city} {r.zip}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-[10px] font-mono uppercase px-2 py-0.5 border ${resultStyle(r.results)}`}>
                  {r.results}
                </span>
                <span className={`text-[10px] font-mono font-medium ${riskStyle(r.risk)}`}>
                  {r.risk}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3 text-[10px] font-mono text-white/15 mb-2">
              <span>{r.facility_type}</span>
              <span className="text-white/5">|</span>
              <span>{r.inspection_type}</span>
              <span className="text-white/5">|</span>
              <span>{new Date(r.inspection_date).toLocaleDateString()}</span>
            </div>

            {violations.length > 0 && (
              <details className="mt-2">
                <summary className="text-[10px] font-mono text-white/25 cursor-pointer hover:text-white/40 uppercase tracking-wider">
                  {violations.length} violation{violations.length > 1 ? 's' : ''}
                </summary>
                <div className="mt-2 space-y-1">
                  {violations.map((v, i) => (
                    <div key={i} className="text-[10px] text-white/25 bg-white/[0.02] border border-white/[0.04] p-2.5 leading-relaxed font-mono">
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
