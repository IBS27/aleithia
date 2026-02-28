import type { LicenseRecord } from '../types/index.ts'

interface Props {
  licenses: LicenseRecord[]
}

export default function LicenseTable({ licenses }: Props) {
  if (licenses.length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 text-center text-gray-500">
        No business license data available for this neighborhood.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-300">Business Licenses</h3>
        <span className="text-xs text-gray-500">{licenses.length} records</span>
      </div>

      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left p-3 text-xs font-medium text-gray-500">Business Name</th>
              <th className="text-left p-3 text-xs font-medium text-gray-500">DBA</th>
              <th className="text-left p-3 text-xs font-medium text-gray-500">License Type</th>
              <th className="text-left p-3 text-xs font-medium text-gray-500">Address</th>
              <th className="text-left p-3 text-xs font-medium text-gray-500">Ward</th>
            </tr>
          </thead>
          <tbody>
            {licenses.map((lic) => {
              const r = lic.metadata?.raw_record
              if (!r) return null

              return (
                <tr key={lic.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="p-3 text-gray-200 font-medium">
                    {r.legal_name || 'Unknown'}
                  </td>
                  <td className="p-3 text-gray-400">
                    {r.doing_business_as_name || '-'}
                  </td>
                  <td className="p-3">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
                      {r.license_description || 'Business License'}
                    </span>
                  </td>
                  <td className="p-3 text-gray-500 text-xs">{r.address}</td>
                  <td className="p-3 text-gray-500 text-xs">{r.ward || lic.geo?.ward || '-'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
