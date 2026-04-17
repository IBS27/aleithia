import type { PermitRecord } from '../types/index.ts'

interface Props {
  permits: PermitRecord[]
}

function statusStyle(status: string) {
  switch (status?.toUpperCase()) {
    case 'ACTIVE': return { border: 'border-emerald-500/30', text: 'text-emerald-300/90', bg: 'bg-emerald-500/[0.04]' }
    case 'COMPLETE': return { border: 'border-blue-500/30', text: 'text-blue-300/90', bg: 'bg-blue-500/[0.04]' }
    case 'CLOSED': return { border: 'border-white/[0.08]', text: 'text-white/40', bg: 'bg-white/[0.01]' }
    default: return { border: 'border-amber-500/30', text: 'text-amber-300/90', bg: 'bg-amber-500/[0.04]' }
  }
}

export default function PermitTable({ permits }: Props) {
  if (permits.length === 0) {
    return (
      <div className="border border-white/[0.06] bg-white/[0.01] p-8 text-center">
        <div className="text-xs font-mono text-white/30 uppercase tracking-wider">No building permits</div>
        <div className="text-[10px] font-mono text-white/20 mt-1">Permits will appear once construction activity is recorded in this area.</div>
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      {permits.map((permit) => {
        const r = permit.metadata?.raw_record
        if (!r) return null

        const address = [r.street_number, r.street_direction, r.street_name].filter(Boolean).join(' ')
        const fee = r.building_fee_paid ? `$${Number(r.building_fee_paid).toLocaleString()}` : null
        const status = statusStyle(r.permit_status)

        return (
          <div key={permit.id} className={`border border-white/[0.06] border-l-2 ${status.border} bg-white/[0.01] hover:bg-white/[0.02] transition-colors`}>
            <div className="p-3">
              {/* Row 1: Type + Status */}
              <div className="flex items-start justify-between gap-3 mb-1">
                <h4 className="text-sm font-semibold text-white truncate">{r.work_type || 'Building Permit'}</h4>
                <span className={`text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border shrink-0 ${status.border} ${status.text} ${status.bg}`}>
                  {r.permit_status}
                </span>
              </div>

              {/* Row 2: Address */}
              <div className="text-[10px] font-mono text-white/35 truncate">{address}</div>

              {/* Row 3: Description */}
              {r.work_description && (
                <p className="text-[11px] text-white/50 mt-1.5 leading-relaxed line-clamp-2">
                  {r.work_description}
                </p>
              )}

              {/* Row 4: Metadata */}
              <div className="flex items-center gap-2 text-[10px] font-mono text-white/25 mt-2 flex-wrap">
                {r.permit_ && <span className="uppercase tracking-wider">#{r.permit_}</span>}
                {r.permit_type && <><span className="text-white/10">·</span><span>{r.permit_type}</span></>}
                {fee && <><span className="text-white/10">·</span><span className="text-emerald-400/60">{fee}</span></>}
                {r.issue_date && <><span className="text-white/10">·</span><span>{new Date(r.issue_date).toLocaleDateString()}</span></>}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
