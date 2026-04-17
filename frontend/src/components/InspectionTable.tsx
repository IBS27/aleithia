import type { InspectionRecord } from '../types/index.ts'

interface Props {
  inspections: InspectionRecord[]
}

function resultStyle(result: string) {
  switch (result) {
    case 'Pass': return { border: 'border-emerald-500/30', text: 'text-emerald-300/90', bg: 'bg-emerald-500/[0.04]' }
    case 'Fail': return { border: 'border-red-500/30', text: 'text-red-300/90', bg: 'bg-red-500/[0.04]' }
    case 'Pass w/ Conditions': return { border: 'border-amber-500/30', text: 'text-amber-300/90', bg: 'bg-amber-500/[0.04]' }
    default: return { border: 'border-white/[0.08]', text: 'text-white/40', bg: 'bg-white/[0.01]' }
  }
}

function riskStyle(risk: string) {
  if (risk.includes('1')) return 'text-red-400/80'
  if (risk.includes('2')) return 'text-amber-400/80'
  return 'text-emerald-400/70'
}

export default function InspectionTable({ inspections }: Props) {
  if (inspections.length === 0) {
    return (
      <div className="border border-white/[0.06] bg-white/[0.01] p-8 text-center">
        <div className="text-xs font-mono text-white/30 uppercase tracking-wider">No food inspection records</div>
        <div className="text-[10px] font-mono text-white/20 mt-1">Inspections will appear once Chicago Data Portal returns records for this area.</div>
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      {inspections.map((insp) => {
        const r = insp.metadata?.raw_record
        if (!r) return null
        const violations = (r.violations || '').split('|').filter(Boolean)
        const result = resultStyle(r.results)

        return (
          <div key={insp.id} className={`border border-white/[0.06] border-l-2 ${result.border} bg-white/[0.01] hover:bg-white/[0.02] transition-colors`}>
            <div className="p-3">
              {/* Row 1: Name + Status */}
              <div className="flex items-start justify-between gap-3 mb-1">
                <h4 className="text-sm font-semibold text-white truncate">{r.dba_name}</h4>
                <div className="flex items-center gap-1.5 shrink-0">
                  <span className={`text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border ${result.border} ${result.text} ${result.bg}`}>
                    {r.results}
                  </span>
                  <span className={`text-[9px] font-mono font-semibold uppercase ${riskStyle(r.risk)}`}>
                    {r.risk}
                  </span>
                </div>
              </div>

              {/* Row 2: Address + metadata */}
              <div className="flex items-center gap-3 text-[10px] font-mono text-white/35 flex-wrap">
                <span className="truncate">{r.address}, {r.city} {r.zip}</span>
              </div>

              {/* Row 3: Type / Inspection type / Date */}
              <div className="flex items-center gap-2 text-[10px] font-mono text-white/25 mt-1.5">
                <span className="uppercase tracking-wider">{r.facility_type}</span>
                <span className="text-white/10">·</span>
                <span>{r.inspection_type}</span>
                <span className="text-white/10">·</span>
                <span>{new Date(r.inspection_date).toLocaleDateString()}</span>
              </div>

              {violations.length > 0 && (
                <details className="mt-2">
                  <summary className={`text-[10px] font-mono cursor-pointer uppercase tracking-wider ${result.text} hover:opacity-80`}>
                    {violations.length} violation{violations.length > 1 ? 's' : ''} ›
                  </summary>
                  <div className="mt-2 space-y-1">
                    {violations.map((v, i) => (
                      <div key={i} className="text-[10px] text-white/40 bg-white/[0.02] border border-white/[0.04] p-2 leading-relaxed">
                        {v.trim().substring(0, 300)}
                        {v.trim().length > 300 && '...'}
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
