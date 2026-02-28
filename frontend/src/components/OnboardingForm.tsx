import { useEffect, useState } from 'react'
import type { UserProfile } from '../types/index.ts'

const NEIGHBORHOODS = [
  'Albany Park', 'Andersonville', 'Avondale', 'Boystown', 'Bridgeport',
  'Bronzeville', 'Bucktown', 'Chinatown', 'Edgewater', 'Gold Coast',
  'Humboldt Park', 'Hyde Park', 'Lakeview', 'Lincoln Park', 'Lincoln Square',
  'Little Village', 'Logan Square', 'Loop', 'Near North Side', 'Old Town',
  'Pilsen', 'River North', 'Rogers Park', 'South Loop', 'Streeterville',
  'Ukrainian Village', 'Uptown', 'West Loop', 'West Town', 'Wicker Park',
]

const BUSINESS_TYPES = [
  'Restaurant', 'Coffee Shop', 'Bar / Nightlife', 'Retail Store',
  'Grocery / Convenience', 'Salon / Barbershop', 'Fitness Studio',
  'Professional Services', 'Food Truck', 'Bakery',
]

interface Props {
  onSubmit: (profile: UserProfile) => void
  onCancel?: () => void
  initialProfile?: UserProfile | null
}

export default function OnboardingForm({ onSubmit, onCancel, initialProfile }: Props) {
  const [businessType, setBusinessType] = useState(initialProfile?.business_type ?? '')
  const [neighborhood, setNeighborhood] = useState(initialProfile?.neighborhood ?? '')

  useEffect(() => {
    if (initialProfile?.business_type) {
      setBusinessType(initialProfile.business_type)
    }
    if (initialProfile?.neighborhood) {
      setNeighborhood(initialProfile.neighborhood)
    }
  }, [initialProfile])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (businessType && neighborhood) {
      onSubmit({ business_type: businessType, neighborhood })
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-[#06080d]">
      <div className="max-w-md w-full">
        <div className="mb-12">
          <p className="text-xs font-mono font-medium uppercase tracking-[0.3em] text-white/30 mb-4">
            Alethia
          </p>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2">
            Configure analysis.
          </h1>
          <p className="text-sm text-white/40 leading-relaxed">
            Select your business type and target neighborhood to begin.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-xs font-mono uppercase tracking-wider text-white/30 mb-2">
              Business Type
            </label>
            <select
              value={businessType}
              onChange={(e) => setBusinessType(e.target.value)}
              className="w-full bg-white/[0.03] border border-white/[0.08] px-4 py-3 text-sm text-white focus:outline-none focus:border-white/30 transition-colors appearance-none cursor-pointer"
            >
              <option value="" className="bg-[#0a0c12]">Select type...</option>
              {BUSINESS_TYPES.map((type) => (
                <option key={type} value={type} className="bg-[#0a0c12]">{type}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-mono uppercase tracking-wider text-white/30 mb-2">
              Neighborhood
            </label>
            <select
              value={neighborhood}
              onChange={(e) => setNeighborhood(e.target.value)}
              className="w-full bg-white/[0.03] border border-white/[0.08] px-4 py-3 text-sm text-white focus:outline-none focus:border-white/30 transition-colors appearance-none cursor-pointer"
            >
              <option value="" className="bg-[#0a0c12]">Select neighborhood...</option>
              {NEIGHBORHOODS.map((n) => (
                <option key={n} value={n} className="bg-[#0a0c12]">{n}</option>
              ))}
            </select>
          </div>

          <div className="pt-2 space-y-2">
            <button
              type="submit"
              disabled={!businessType || !neighborhood}
              className="w-full bg-white text-[#06080d] disabled:bg-white/[0.06] disabled:text-white/20 font-semibold py-3.5 text-sm tracking-wide transition-colors hover:bg-gray-200 cursor-pointer"
            >
              Run Analysis
            </button>
            {onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="w-full border border-white/20 text-white/60 hover:text-white hover:border-white/40 font-semibold py-3.5 text-sm tracking-wide transition-colors cursor-pointer"
              >
                Back
              </button>
            )}
          </div>

          <p className="text-center text-[10px] font-mono text-white/15 uppercase tracking-widest pt-2">
            9 live data sources across Chicago
          </p>
        </form>
      </div>
    </div>
  )
}
