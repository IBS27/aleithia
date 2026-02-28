import type { LicenseRecord } from '../types/index.ts'

interface Props {
  licenses: LicenseRecord[]
}

export default function LicenseTable({ licenses }: Props) {
  if (licenses.length === 0) {
    return (
      <div className="border border-white/[0.06] p-8 text-center text-xs font-mono text-white/20 uppercase tracking-wider">
        No business license data available
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30">Business Licenses</h3>
        <span className="text-[10px] font-mono text-white/15">{licenses.length} records</span>
      </div>

      <div className="border border-white/[0.06] overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/[0.06]">
              <th className="text-left p-3 text-[10px] font-mono font-medium uppercase tracking-wider text-white/20">Legal Name</th>
              <th className="text-left p-3 text-[10px] font-mono font-medium uppercase tracking-wider text-white/20">DBA</th>
              <th className="text-left p-3 text-[10px] font-mono font-medium uppercase tracking-wider text-white/20">License</th>
              <th className="text-left p-3 text-[10px] font-mono font-medium uppercase tracking-wider text-white/20">Address</th>
              <th className="text-left p-3 text-[10px] font-mono font-medium uppercase tracking-wider text-white/20">Ward</th>
            </tr>
          </thead>
          <tbody>
            {licenses.map((lic) => {
              const r = lic.metadata?.raw_record
              if (!r) return null

              return (
                <tr key={lic.id} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                  <td className="p-3 text-white/70 font-medium">
                    {r.legal_name || 'Unknown'}
                  </td>
                  <td className="p-3 text-white/30">
                    {r.doing_business_as_name || '—'}
                  </td>
                  <td className="p-3">
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 border border-white/[0.08] text-white/40">
                      {r.license_description || 'Business License'}
                    </span>
                  </td>
                  <td className="p-3 text-white/20 font-mono text-[10px]">{r.address}</td>
                  <td className="p-3 text-white/20 font-mono text-[10px]">{r.ward || lic.geo?.ward || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
