import type { PermitRecord } from '../types/index.ts'

interface Props {
  permits: PermitRecord[]
}

function statusColor(status: string) {
  switch (status?.toUpperCase()) {
    case 'ACTIVE': return 'bg-green-500/20 text-green-400 border-green-500/30'
    case 'COMPLETE': return 'bg-blue-500/20 text-blue-400 border-blue-500/30'
    case 'CLOSED': return 'bg-gray-500/20 text-gray-400 border-gray-500/30'
    default: return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
  }
}

export default function PermitTable({ permits }: Props) {
  if (permits.length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 text-center text-gray-500">
        No building permit data available for this neighborhood.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-300">Building Permits</h3>
        <span className="text-xs text-gray-500">{permits.length} records</span>
      </div>

      {permits.map((permit) => {
        const r = permit.metadata?.raw_record
        if (!r) return null

        const address = [r.street_number, r.street_direction, r.street_name].filter(Boolean).join(' ')
        const fee = r.building_fee_paid ? `$${Number(r.building_fee_paid).toLocaleString()}` : null

        return (
          <div key={permit.id} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
            <div className="flex items-start justify-between mb-2">
              <div>
                <h4 className="font-semibold text-gray-100">{r.work_type || 'Building Permit'}</h4>
                <p className="text-xs text-gray-500">{address}</p>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full border ${statusColor(r.permit_status)}`}>
                {r.permit_status}
              </span>
            </div>

            {r.work_description && (
              <p className="text-xs text-gray-400 mb-2 leading-relaxed">
                {r.work_description.substring(0, 200)}
                {r.work_description.length > 200 && '...'}
              </p>
            )}

            <div className="flex items-center gap-4 text-xs text-gray-500">
              {r.permit_ && <span>#{r.permit_}</span>}
              {r.permit_type && <span>{r.permit_type}</span>}
              {fee && <span className="text-green-400">{fee} fee</span>}
              {r.issue_date && <span>{new Date(r.issue_date).toLocaleDateString()}</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}
