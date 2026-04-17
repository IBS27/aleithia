import type { LicenseRecord } from '../types/index.ts'

interface Props {
  licenses: LicenseRecord[]
}

export default function LicenseTable({ licenses }: Props) {
  if (licenses.length === 0) {
    return (
      <div className="border border-white/[0.06] bg-white/[0.01] p-8 text-center">
        <div className="text-xs font-mono text-white/30 uppercase tracking-wider">No active business licenses</div>
        <div className="text-[10px] font-mono text-white/20 mt-1">Licenses will appear once the city publishes records for this area.</div>
      </div>
    )
  }

  return (
    <div className="border border-white/[0.06] bg-white/[0.01] overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-white/[0.06] bg-white/[0.02]">
            <th className="text-left px-3 py-2 text-[9px] font-mono font-medium uppercase tracking-wider text-white/35">Legal Name</th>
            <th className="text-left px-3 py-2 text-[9px] font-mono font-medium uppercase tracking-wider text-white/35">DBA</th>
            <th className="text-left px-3 py-2 text-[9px] font-mono font-medium uppercase tracking-wider text-white/35">License Type</th>
            <th className="text-left px-3 py-2 text-[9px] font-mono font-medium uppercase tracking-wider text-white/35">Address</th>
            <th className="text-left px-3 py-2 text-[9px] font-mono font-medium uppercase tracking-wider text-white/35">Ward</th>
          </tr>
        </thead>
        <tbody>
          {licenses.map((lic) => {
            const r = lic.metadata?.raw_record
            if (!r) return null

            return (
              <tr key={lic.id} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                <td className="px-3 py-2 text-white/75 font-medium truncate max-w-[200px]">
                  {r.legal_name || 'Unknown'}
                </td>
                <td className="px-3 py-2 text-white/40 truncate max-w-[180px]">
                  {r.doing_business_as_name || '—'}
                </td>
                <td className="px-3 py-2">
                  <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border border-violet-500/20 text-violet-300/70 bg-violet-500/[0.04]">
                    {r.license_description || 'Business License'}
                  </span>
                </td>
                <td className="px-3 py-2 text-white/30 font-mono text-[10px] truncate max-w-[180px]">{r.address}</td>
                <td className="px-3 py-2 text-white/30 font-mono text-[10px]">{r.ward || lic.geo?.ward || '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
