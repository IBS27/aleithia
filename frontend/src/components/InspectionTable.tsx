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

function ExternalIcon() {
  return (
    <svg className="w-3 h-3 text-white/15 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" />
    </svg>
  )
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
        const hasUrl = !!insp.url

        const card = (
          <>
            <div className="flex items-start justify-between mb-2">
              <div className="min-w-0 flex-1">
                <h4 className="text-sm font-semibold text-white">{r.dba_name}</h4>
                <p className="text-[10px] font-mono text-white/20 mt-0.5">{r.address}, {r.city} {r.zip}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`text-[10px] font-mono uppercase px-2 py-0.5 border ${resultStyle(r.results)}`}>
                  {r.results}
                </span>
                <span className={`text-[10px] font-mono font-medium ${riskStyle(r.risk)}`}>
                  {r.risk}
                </span>
                {hasUrl && <ExternalIcon />}
              </div>
            </div>

            <div className="flex items-center gap-3 text-[10px] font-mono text-white/15 mb-2">
              <span>{r.facility_type}</span>
              <span className="text-white/5">|</span>
              <span>{r.inspection_type}</span>
              <span className="text-white/5">|</span>
              <span>{new Date(r.inspection_date).toLocaleDateString()}</span>
            </div>
          </>
        )

        return (
          <div key={insp.id}>
            {hasUrl ? (
              <a
                href={insp.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block border border-white/[0.06] bg-white/[0.01] p-4 hover:bg-white/[0.04] hover:border-white/[0.12] transition-colors cursor-pointer"
              >
                {card}
              </a>
            ) : (
              <div className="border border-white/[0.06] bg-white/[0.01] p-4">
                {card}
              </div>
            )}

            {violations.length > 0 && (
              <details className="border border-t-0 border-white/[0.06] bg-white/[0.01]">
                <summary className="px-4 py-2 text-[10px] font-mono text-white/25 cursor-pointer hover:text-white/40 uppercase tracking-wider">
                  {violations.length} violation{violations.length > 1 ? 's' : ''}
                </summary>
                <div className="px-4 pb-3 space-y-1">
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
