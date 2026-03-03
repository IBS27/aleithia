import type { PermitRecord } from '../types/index.ts'

interface Props {
  permits: PermitRecord[]
}

function statusStyle(status: string) {
  switch (status?.toUpperCase()) {
    case 'ACTIVE': return 'text-green-400/80 border-green-500/20'
    case 'COMPLETE': return 'text-blue-400/80 border-blue-500/20'
    case 'CLOSED': return 'text-white/30 border-white/[0.06]'
    default: return 'text-yellow-400/80 border-yellow-500/20'
  }
}

function ExternalIcon() {
  return (
    <svg className="w-3 h-3 text-white/15 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" />
    </svg>
  )
}

export default function PermitTable({ permits }: Props) {
  if (permits.length === 0) {
    return (
      <div className="border border-white/[0.06] p-8 text-center text-xs font-mono text-white/20 uppercase tracking-wider">
        No building permit data available
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30">Building Permits</h3>
        <span className="text-[10px] font-mono text-white/15">{permits.length} records</span>
      </div>

      {permits.map((permit) => {
        const r = permit.metadata?.raw_record
        if (!r) return null

        const address = [r.street_number, r.street_direction, r.street_name].filter(Boolean).join(' ')
        const fee = r.building_fee_paid ? `$${Number(r.building_fee_paid).toLocaleString()}` : null
        const hasUrl = !!permit.url

        const content = (
          <>
            <div className="flex items-start justify-between mb-2">
              <div className="min-w-0 flex-1">
                <h4 className="text-sm font-semibold text-white">{r.work_type || 'Building Permit'}</h4>
                <p className="text-[10px] font-mono text-white/20 mt-0.5">{address}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`text-[10px] font-mono uppercase px-2 py-0.5 border ${statusStyle(r.permit_status)}`}>
                  {r.permit_status}
                </span>
                {hasUrl && <ExternalIcon />}
              </div>
            </div>

            {r.work_description && (
              <p className="text-xs text-white/30 mb-2 leading-relaxed">
                {r.work_description.substring(0, 200)}
                {r.work_description.length > 200 && '...'}
              </p>
            )}

            <div className="flex items-center gap-3 text-[10px] font-mono text-white/15">
              {r.permit_ && <span>#{r.permit_}</span>}
              {r.permit_type && <span>{r.permit_type}</span>}
              {fee && <span className="text-green-400/60">{fee}</span>}
              {r.issue_date && <span>{new Date(r.issue_date).toLocaleDateString()}</span>}
            </div>
          </>
        )

        return hasUrl ? (
          <a
            key={permit.id}
            href={permit.url}
            target="_blank"
            rel="noopener noreferrer"
            className="block border border-white/[0.06] bg-white/[0.01] p-4 hover:bg-white/[0.04] hover:border-white/[0.12] transition-colors cursor-pointer"
          >
            {content}
          </a>
        ) : (
          <div key={permit.id} className="border border-white/[0.06] bg-white/[0.01] p-4">
            {content}
          </div>
        )
      })}
    </div>
  )
}
