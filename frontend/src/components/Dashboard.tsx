import { useState, useEffect } from 'react'
import type { UserProfile, NeighborhoodData, DataSources, ChatMessage, RiskScore } from '../types/index.ts'
import { api } from '../api.ts'
import RiskCard from './RiskCard.tsx'
import ChatPanel from './ChatPanel.tsx'
import MapView from './MapView.tsx'
import Timer from './Timer.tsx'
import DataSourceBadge from './DataSourceBadge.tsx'
import InspectionTable from './InspectionTable.tsx'
import PermitTable from './PermitTable.tsx'
import LicenseTable from './LicenseTable.tsx'
import NewsFeed from './NewsFeed.tsx'
import DemographicsCard from './DemographicsCard.tsx'

type Tab = 'overview' | 'inspections' | 'permits' | 'licenses' | 'news'

function computeRiskScore(data: NeighborhoodData, profile: UserProfile): RiskScore {
  const factors = []
  const stats = data.inspection_stats

  if (stats.total > 0) {
    const failRate = stats.failed / stats.total
    factors.push({
      label: `${stats.failed} of ${stats.total} inspections failed nearby`,
      pct: Math.round(failRate * 100),
      source: 'food_inspections',
      severity: failRate > 0.4 ? 'high' as const : failRate > 0.2 ? 'medium' as const : 'low' as const,
      description: `${stats.passed} passed, ${stats.failed} failed out of ${stats.total} recent food inspections in the area.`,
    })
  }

  if (data.permit_count > 0) {
    factors.push({
      label: `${data.permit_count} active building permits`,
      pct: Math.min(data.permit_count * 5, 30),
      source: 'building_permits',
      severity: data.permit_count > 10 ? 'medium' as const : 'low' as const,
      description: 'Active construction and renovation activity suggests a developing area.',
    })
  }

  if (data.license_count > 0) {
    factors.push({
      label: `${data.license_count} active business licenses`,
      pct: Math.min(data.license_count * 3, 25),
      source: 'business_licenses',
      severity: data.license_count > 15 ? 'medium' as const : 'low' as const,
      description: 'Existing business density indicates competition level and market viability.',
    })
  }

  if (data.news.length > 0) {
    factors.push({
      label: `${data.news.length} recent news articles`,
      pct: 10,
      source: 'news',
      severity: 'low' as const,
      description: 'Local news coverage indicates community activity and awareness.',
    })
  }

  if (data.politics.length > 0) {
    factors.push({
      label: `${data.politics.length} legislative items`,
      pct: 15,
      source: 'politics',
      severity: data.politics.length > 5 ? 'medium' as const : 'low' as const,
      description: 'Recent city council activity related to this area.',
    })
  }

  const metrics = data.metrics || {}
  if (metrics.active_permits) {
    factors.push({
      label: `Permit density: ${metrics.active_permits} in neighborhood`,
      pct: 10,
      source: 'public_data',
      severity: 'low' as const,
      description: 'Overall permit activity density across the neighborhood.',
    })
  }

  // Compute overall score (0-10, higher = more risk)
  const failRate = stats.total > 0 ? stats.failed / stats.total : 0
  const overallScore = Math.min(10, Math.max(1,
    3 + failRate * 4 + (data.license_count > 10 ? 1 : 0) + (data.politics.length > 3 ? 1 : 0)
  ))

  // Normalize factor percentages to 100
  const totalPct = factors.reduce((s, f) => s + f.pct, 0) || 1
  factors.forEach(f => { f.pct = Math.round((f.pct / totalPct) * 100) })

  return {
    neighborhood: profile.neighborhood,
    business_type: profile.business_type,
    overall_score: Math.round(overallScore * 10) / 10,
    confidence: Math.min(0.95, 0.4 + (stats.total + data.license_count + data.permit_count) * 0.01),
    factors,
    summary: `Analysis of ${profile.neighborhood} for a ${profile.business_type.toLowerCase()} based on ${stats.total + data.permit_count + data.license_count} data points across city permits, inspections, licenses, and legislative activity.`,
  }
}

interface Props {
  profile: UserProfile
  onReset: () => void
}

export default function Dashboard({ profile, onReset }: Props) {
  const [neighborhoodData, setNeighborhoodData] = useState<NeighborhoodData | null>(null)
  const [sources, setSources] = useState<DataSources | null>(null)
  const [riskScore, setRiskScore] = useState<RiskScore | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [chatLoading, setChatLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [nbData, srcData] = await Promise.all([
          api.neighborhood(profile.neighborhood),
          api.sources(),
        ])
        if (cancelled) return
        setNeighborhoodData(nbData)
        setSources(srcData)
        setRiskScore(computeRiskScore(nbData, profile))
        setLoading(false)
      } catch (err) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load data')
        setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [profile])

  const sourceList = sources
    ? Object.entries(sources).map(([name, info]) => ({
        name: name.replace('_', ' '),
        count: info.count,
        active: info.active,
      }))
    : []

  const handleChat = (message: string) => {
    setMessages(prev => [...prev, { role: 'user', content: message, timestamp: new Date() }])
    setChatLoading(true)

    setTimeout(() => {
      let response = ''
      const nb = profile.neighborhood
      const biz = profile.business_type.toLowerCase()

      if (message.toLowerCase().includes('permit')) {
        const permits = neighborhoodData?.permits || []
        response = `Based on ${permits.length} recent permits in ${nb}:\n\n`
        if (permits.length > 0) {
          response += permits.slice(0, 3).map(p => {
            const r = p.metadata?.raw_record || {} as Record<string, string>
            return `- ${r.work_type || 'Permit'}: ${r.street_number || ''} ${r.street_direction || ''} ${r.street_name || ''} (${r.permit_status || 'Active'})`
          }).join('\n')
        }
        response += `\n\nFor a ${biz}, you'll typically need a Limited Business License and applicable permits for your specific operation.`
      } else if (message.toLowerCase().includes('inspection') || message.toLowerCase().includes('health')) {
        const stats = neighborhoodData?.inspection_stats || { total: 0, failed: 0, passed: 0 }
        response = `Food inspection data for ${nb}:\n\n`
        response += `- Total inspections: ${stats.total}\n- Passed: ${stats.passed}\n- Failed: ${stats.failed}\n`
        if (stats.total > 0) {
          response += `- Pass rate: ${Math.round((stats.passed / stats.total) * 100)}%\n`
        }
        response += `\nThis data helps gauge the regulatory environment you'll be operating in.`
      } else if (message.toLowerCase().includes('competition') || message.toLowerCase().includes('business')) {
        const licenses = neighborhoodData?.licenses || []
        response = `There are ${licenses.length} active business licenses in ${nb}.\n\n`
        if (licenses.length > 0) {
          response += 'Nearby businesses include:\n'
          response += licenses.slice(0, 5).map(l => {
            const r = l.metadata?.raw_record || {} as Record<string, string>
            return `- ${r.doing_business_as_name || r.legal_name || 'Unknown'} (${r.license_description || 'Business'})`
          }).join('\n')
        }
      } else {
        const total = (neighborhoodData?.inspection_stats.total || 0) + (neighborhoodData?.permit_count || 0) + (neighborhoodData?.license_count || 0)
        response = `Here's what I found about ${nb} for a ${biz}:\n\n`
        response += `We analyzed ${total} data points across food inspections, building permits, and business licenses.\n\n`
        if (riskScore) {
          response += `Risk score: ${riskScore.overall_score}/10 (${riskScore.overall_score <= 4 ? 'low' : riskScore.overall_score <= 7 ? 'moderate' : 'high'} risk)\n\n`
        }
        response += 'Ask me about specific topics: permits, inspections, competition, or zoning.'
      }

      setMessages(prev => [...prev, { role: 'assistant', content: response, timestamp: new Date() }])
      setChatLoading(false)
    }, 800)
  }

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'inspections', label: 'Inspections', count: neighborhoodData?.inspection_stats.total },
    { key: 'permits', label: 'Permits', count: neighborhoodData?.permit_count },
    { key: 'licenses', label: 'Licenses', count: neighborhoodData?.license_count },
    { key: 'news', label: 'News & Politics', count: (neighborhoodData?.news.length || 0) + (neighborhoodData?.politics.length || 0) },
  ]

  return (
    <div className="h-screen flex flex-col">
      {/* Top bar */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-gray-800 bg-gray-900/80 backdrop-blur-sm">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-bold text-indigo-400">Alethia</h1>
          <div className="h-4 w-px bg-gray-700" />
          <span className="text-sm text-gray-400">
            {profile.business_type} in <strong className="text-gray-200">{profile.neighborhood}</strong>
          </span>
        </div>
        <div className="flex items-center gap-4">
          <Timer running={loading} />
          <button onClick={onReset} className="text-xs text-gray-500 hover:text-gray-300 transition-colors">
            New Search
          </button>
        </div>
      </header>

      {error && (
        <div className="mx-6 mt-4 p-4 bg-red-900/30 border border-red-800 rounded-lg text-red-300 text-sm">
          {error} — Make sure the backend is running on port 8000
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex min-h-0">
        {/* Left: Data */}
        <div className="flex-1 flex flex-col p-4 gap-4 overflow-y-auto">
          {/* Data sources */}
          <DataSourceBadge sources={sourceList} />

          {/* Tabs */}
          <div className="flex gap-1 bg-gray-900 rounded-lg p-1 border border-gray-800">
            {tabs.map(tab => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === tab.key
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                }`}
              >
                {tab.label}
                {tab.count !== undefined && tab.count > 0 && (
                  <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                    activeTab === tab.key ? 'bg-indigo-500' : 'bg-gray-700'
                  }`}>
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {loading ? (
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-12 text-center">
              <div className="animate-spin w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full mx-auto mb-4" />
              <p className="text-gray-400">Analyzing {profile.neighborhood} across all data sources...</p>
              <p className="text-xs text-gray-600 mt-2">Loading real Chicago city data</p>
            </div>
          ) : (
            <>
              {activeTab === 'overview' && (
                <div className="space-y-4">
                  {/* Map */}
                  <div className="h-[300px]">
                    <MapView activeNeighborhood={profile.neighborhood} />
                  </div>

                  {/* Risk + Demographics side by side */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {riskScore && <RiskCard score={riskScore} />}
                    {neighborhoodData?.metrics && (
                      <DemographicsCard metrics={neighborhoodData.metrics} />
                    )}
                  </div>

                  {/* Quick stats */}
                  {neighborhoodData && (
                    <div className="grid grid-cols-4 gap-3">
                      <StatCard
                        label="Food Inspections"
                        value={neighborhoodData.inspection_stats.total}
                        sub={`${neighborhoodData.inspection_stats.failed} failed`}
                        color={neighborhoodData.inspection_stats.failed > 5 ? 'red' : 'green'}
                      />
                      <StatCard
                        label="Building Permits"
                        value={neighborhoodData.permit_count}
                        sub="active"
                        color="blue"
                      />
                      <StatCard
                        label="Business Licenses"
                        value={neighborhoodData.license_count}
                        sub="in area"
                        color="purple"
                      />
                      <StatCard
                        label="News & Politics"
                        value={neighborhoodData.news.length + neighborhoodData.politics.length}
                        sub="recent items"
                        color="amber"
                      />
                    </div>
                  )}

                  {/* Cost comparison */}
                  <div className="bg-gray-900/50 rounded-xl border border-gray-800 p-4 text-center">
                    <div className="flex items-center justify-center gap-8">
                      <div>
                        <div className="text-xs text-gray-500">Traditional research</div>
                        <div className="text-lg font-bold text-red-400 line-through">$5,000 - $15,000</div>
                        <div className="text-xs text-gray-600">2-3 weeks</div>
                      </div>
                      <div className="text-2xl text-gray-600">vs</div>
                      <div>
                        <div className="text-xs text-gray-500">Alethia</div>
                        <div className="text-lg font-bold text-green-400">Free</div>
                        <div className="text-xs text-gray-600">seconds</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'inspections' && neighborhoodData && (
                <InspectionTable inspections={neighborhoodData.inspections} />
              )}

              {activeTab === 'permits' && neighborhoodData && (
                <PermitTable permits={neighborhoodData.permits} />
              )}

              {activeTab === 'licenses' && neighborhoodData && (
                <LicenseTable licenses={neighborhoodData.licenses} />
              )}

              {activeTab === 'news' && neighborhoodData && (
                <NewsFeed news={neighborhoodData.news} politics={neighborhoodData.politics} />
              )}
            </>
          )}
        </div>

        {/* Right: Chat */}
        <div className="w-96 border-l border-gray-800 p-4">
          <ChatPanel messages={messages} onSend={handleChat} loading={chatLoading} />
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, sub, color }: { label: string; value: number; sub: string; color: string }) {
  const colors: Record<string, string> = {
    red: 'text-red-400 bg-red-500/10 border-red-500/20',
    green: 'text-green-400 bg-green-500/10 border-green-500/20',
    blue: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
    purple: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
    amber: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  }
  return (
    <div className={`rounded-xl border p-4 ${colors[color] || colors.blue}`}>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs opacity-80 mt-1">{label}</div>
      <div className="text-xs opacity-60">{sub}</div>
    </div>
  )
}
