import type { LicenseRecord } from '../types/index.ts'

interface Props {
  licenses: LicenseRecord[]
}

function ExternalIcon() {
  return (
    <svg className="w-3 h-3 text-white/15 shrink-0 inline-block ml-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" />
    </svg>
  )
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
              const hasUrl = !!lic.url

              const cells = (
                <>
                  <td className="p-3 text-white/70 font-medium">
                    {r.legal_name || 'Unknown'}
                    {hasUrl && <ExternalIcon />}
                  </td>
                  <td className="p-3 text-white/30">
                    {r.doing_business_as_name || '\u2014'}
                  </td>
                  <td className="p-3">
                    <span className="text-[10px] font-mono uppercase px-2 py-0.5 border border-white/[0.08] text-white/40">
                      {r.license_description || 'Business License'}
                    </span>
                  </td>
                  <td className="p-3 text-white/20 font-mono text-[10px]">{r.address}</td>
                  <td className="p-3 text-white/20 font-mono text-[10px]">{r.ward || lic.geo?.ward || '\u2014'}</td>
                </>
              )

              return hasUrl ? (
                <tr
                  key={lic.id}
                  className="border-b border-white/[0.03] hover:bg-white/[0.04] cursor-pointer transition-colors"
                  onClick={() => window.open(lic.url, '_blank', 'noopener,noreferrer')}
                >
                  {cells}
                </tr>
              ) : (
                <tr key={lic.id} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                  {cells}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
