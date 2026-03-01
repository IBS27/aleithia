import { useEffect, useState } from 'react'
import { useUser, useAuth } from '@clerk/clerk-react'
import { api } from '../api.ts'
import type { UserQuery } from '../api.ts'

interface Props {
  onClose?: () => void
  token?: string | null
  onProfileUpdate?: () => void
  /** When true, used inside Drawer - compact layout, no nav */
  embedded?: boolean
}

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

export default function ProfilePage({ onClose, token, onProfileUpdate, embedded = false }: Props) {
  const { user } = useUser()
  const { getToken } = useAuth()
  const [businessType, setBusinessType] = useState('')
  const [neighborhood, setNeighborhood] = useState('')
  const [riskTolerance, setRiskTolerance] = useState('medium')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [recentQueries, setRecentQueries] = useState<UserQuery[]>([])

  const formatWhen = (iso: string) => {
    const date = new Date(iso)
    return date.toLocaleString()
  }

  useEffect(() => {
    const loadProfile = async () => {
      try {
        const sessionToken = token || await getToken()
        if (!sessionToken) {
          setLoading(false)
          return
        }

        const [profileResult, queryResult] = await Promise.allSettled([
          api.getUserProfile(sessionToken),
          api.getUserQueries(sessionToken, 5),
        ])

        if (profileResult.status === 'fulfilled') {
          setBusinessType(profileResult.value.business_type || '')
          setNeighborhood(profileResult.value.neighborhood || '')
          setRiskTolerance(profileResult.value.risk_tolerance || 'medium')
        } else {
          const msg = String(profileResult.reason)
          if (!msg.includes('API error 404')) {
            console.error('Failed to load profile:', profileResult.reason)
          }
        }

        if (queryResult.status === 'fulfilled') {
          setRecentQueries(queryResult.value)
        } else {
          console.error('Failed to load user queries:', queryResult.reason)
        }
      } catch (error) {
        console.error('Failed to load profile page data:', error)
      } finally {
        setLoading(false)
      }
    }

    loadProfile()
  }, [token, getToken])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()

    setSaving(true)
    setMessage('')

    try {
      const sessionToken = token || await getToken()
      if (!sessionToken) throw new Error('No session token')
      
      await api.updateUserProfile(sessionToken, businessType, neighborhood, riskTolerance)
      setMessage('Profile updated successfully!')
      onProfileUpdate?.()

      const refreshedQueries = await api.getUserQueries(sessionToken, 5)
      setRecentQueries(refreshedQueries)

      setTimeout(() => setMessage(''), 3000)
    } catch (error) {
      setMessage('Failed to save profile: ' + String(error))
    } finally {
      setSaving(false)
    }
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-[#06080d] text-white flex items-center justify-center">
        <p>Please sign in to access your profile.</p>
      </div>
    )
  }

  return (
    <div className={`bg-[#06080d] text-white p-6 ${embedded ? '' : 'min-h-screen'}`}>
      <div className="max-w-2xl mx-auto">
        {embedded && <p className="text-xs font-mono text-white/40 mb-4">{user.primaryEmailAddress?.emailAddress}</p>}
        {!embedded && (
          <div className="mb-8">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-bold mb-2">Profile</h1>
                <p className="text-white/40">{user.primaryEmailAddress?.emailAddress}</p>
              </div>
              {onClose && (
                <button
                  onClick={onClose}
                  className="text-white/40 hover:text-white/60 transition-colors cursor-pointer"
                >
                  ✕
                </button>
              )}
            </div>
          </div>
        )}

        {loading ? (
          <div className="border border-white/10 p-8 rounded">
            <p className="text-white/30">Loading profile...</p>
          </div>
        ) : (
          <div className="space-y-6">
            <form onSubmit={handleSave} className="border border-white/10 p-8 rounded space-y-6">
              <div>
                <label className="block text-sm font-semibold mb-2 text-white/80">
                  Default Business Type
                </label>
                <select
                  value={businessType}
                  onChange={(e) => setBusinessType(e.target.value)}
                  className="w-full bg-white/[0.03] border border-white/[0.08] px-4 py-3 text-sm text-white focus:outline-none focus:border-white/30 transition-colors appearance-none cursor-pointer"
                >
                  <option value="">No default</option>
                  {BUSINESS_TYPES.map((type) => (
                    <option key={type} value={type} className="bg-[#0a0c12]">
                      {type}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-semibold mb-2 text-white/80">
                  Default Neighborhood
                </label>
                <select
                  value={neighborhood}
                  onChange={(e) => setNeighborhood(e.target.value)}
                  className="w-full bg-white/[0.03] border border-white/[0.08] px-4 py-3 text-sm text-white focus:outline-none focus:border-white/30 transition-colors appearance-none cursor-pointer"
                >
                  <option value="">No default</option>
                  {NEIGHBORHOODS.map((n) => (
                    <option key={n} value={n} className="bg-[#0a0c12]">
                      {n}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-semibold mb-2 text-white/80">
                  Risk Tolerance
                </label>
                <select
                  value={riskTolerance}
                  onChange={(e) => setRiskTolerance(e.target.value)}
                  className="w-full bg-white/[0.03] border border-white/[0.08] px-4 py-3 text-sm text-white focus:outline-none focus:border-white/30 transition-colors appearance-none cursor-pointer"
                >
                  <option value="low" className="bg-[#0a0c12]">Low</option>
                  <option value="medium" className="bg-[#0a0c12]">Medium (Default)</option>
                  <option value="high" className="bg-[#0a0c12]">High</option>
                </select>
              </div>

              {message && (
                <div
                  className={`p-3 rounded text-sm ${
                    message.includes('success')
                      ? 'bg-green-500/10 text-green-400 border border-green-500/20'
                      : 'bg-red-500/10 text-red-400 border border-red-500/20'
                  }`}
                >
                  {message}
                </div>
              )}

              <div className="flex gap-3">
                <button
                  type="submit"
                  disabled={saving}
                  className="flex-1 !bg-white !text-[#06080d] disabled:!bg-white/30 disabled:!text-white/40 font-semibold py-3 text-sm transition-colors hover:!bg-white/90 cursor-pointer"
                >
                  {saving ? 'Saving...' : 'Save Profile'}
                </button>
                {onClose && (
                  <button
                    type="button"
                    onClick={onClose}
                    className="flex-1 border border-white/20 text-white/60 hover:text-white hover:border-white/40 font-semibold py-3 text-sm transition-colors cursor-pointer"
                  >
                    Close
                  </button>
                )}
              </div>
            </form>

            <div className="border border-white/10 p-6 rounded">
              <h2 className="text-lg font-semibold mb-4">Recent Queries</h2>
              {recentQueries.length === 0 ? (
                <p className="text-sm text-white/40">No recent queries yet.</p>
              ) : (
                <div className="space-y-3">
                  {recentQueries.map((query) => (
                    <div key={query.id} className="bg-white/[0.03] border border-white/[0.08] rounded p-3">
                      <p className="text-sm text-white/90">{query.query_text}</p>
                      <p className="text-xs text-white/40 mt-1">
                        {query.business_type} · {query.neighborhood} · {formatWhen(query.created_at)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
