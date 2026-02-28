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

  const failRate = stats.total > 0 ? stats.failed / stats.total : 0
  const overallScore = Math.min(10, Math.max(1,
    3 + failRate * 4 + (data.license_count > 10 ? 1 : 0) + (data.politics.length > 3 ? 1 : 0)
  ))

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
    { key: 'news', label: 'Intel', count: (neighborhoodData?.news.length || 0) + (neighborhoodData?.politics.length || 0) },
  ]

  return (
    <div className="h-screen flex flex-col bg-[#06080d]">
      {/* Top bar */}
      <header className="flex items-center justify-between px-6 py-3 bg-white/[0.02] backdrop-blur-md border-b border-white/[0.06]">
        <div className="flex items-center gap-5">
          <h1 className="text-sm font-semibold text-white uppercase tracking-wide">Alethia</h1>
          <div className="h-3.5 w-px bg-white/10" />
          <span className="text-xs font-mono text-white/30">
            {profile.business_type} <span className="text-white/10 mx-1">/</span> <span className="text-white/50">{profile.neighborhood}</span>
          </span>
        </div>
        <div className="flex items-center gap-5">
          <Timer running={loading} />
          <button onClick={onReset} className="text-[10px] font-mono uppercase tracking-wider text-white/20 hover:text-white/50 transition-colors cursor-pointer">
            New Search
          </button>
        </div>
      </header>

      {error && (
        <div className="mx-6 mt-4 p-4 bg-red-500/[0.06] border border-red-500/20 text-red-400/80 text-xs font-mono">
          {error} — Make sure the backend is running on port 8000
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex min-h-0">
        {/* Left: Data */}
        <div className="flex-1 flex flex-col p-4 gap-4 overflow-y-auto">
          <DataSourceBadge sources={sourceList} />

          {/* Tabs */}
          <div className="flex gap-0 border-b border-white/[0.06]">
            {tabs.map(tab => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-2 px-5 py-2.5 text-xs font-medium transition-colors border-b-2 -mb-px cursor-pointer ${
                  activeTab === tab.key
                    ? 'border-white text-white'
                    : 'border-transparent text-white/30 hover:text-white/60'
                }`}
              >
                {tab.label}
                {tab.count !== undefined && tab.count > 0 && (
                  <span className="font-mono text-[10px] text-white/20">
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {loading ? (
            <div className="border border-white/[0.06] p-16 text-center">
              <div className="w-6 h-6 border border-white/20 border-t-white/60 rounded-full animate-spin mx-auto mb-5" />
              <p className="text-xs text-white/30 font-mono uppercase tracking-wider">
                Analyzing {profile.neighborhood}
              </p>
              <p className="text-[10px] text-white/15 font-mono mt-2">Loading real Chicago city data</p>
            </div>
          ) : (
            <>
              {activeTab === 'overview' && (
                <div className="space-y-4">
                  <div className="h-[300px]">
                    <MapView activeNeighborhood={profile.neighborhood} />
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {riskScore && <RiskCard score={riskScore} />}
                    {neighborhoodData?.metrics && (
                      <DemographicsCard metrics={neighborhoodData.metrics} />
                    )}
                  </div>

                  {neighborhoodData && (
                    <div className="grid grid-cols-4 gap-3">
                      <StatCard
                        label="Food Inspections"
                        value={neighborhoodData.inspection_stats.total}
                        sub={`${neighborhoodData.inspection_stats.failed} failed`}
                        severity={neighborhoodData.inspection_stats.failed > 5 ? 'high' : 'nominal'}
                      />
                      <StatCard
                        label="Building Permits"
                        value={neighborhoodData.permit_count}
                        sub="active"
                        severity="nominal"
                      />
                      <StatCard
                        label="Business Licenses"
                        value={neighborhoodData.license_count}
                        sub="in area"
                        severity="nominal"
                      />
                      <StatCard
                        label="Intel Items"
                        value={neighborhoodData.news.length + neighborhoodData.politics.length}
                        sub="recent"
                        severity="nominal"
                      />
                    </div>
                  )}

                  <div className="border border-white/[0.06] p-5">
                    <div className="flex items-center justify-center gap-12">
                      <div className="text-center">
                        <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mb-1">Traditional</div>
                        <div className="text-lg font-bold text-white/30 line-through font-mono">$5K–$15K</div>
                        <div className="text-[10px] font-mono text-white/15">2–3 weeks</div>
                      </div>
                      <div className="text-xs font-mono text-white/10">vs</div>
                      <div className="text-center">
                        <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mb-1">Alethia</div>
                        <div className="text-lg font-bold text-white font-mono">$0</div>
                        <div className="text-[10px] font-mono text-white/30">seconds</div>
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
        <div className="w-96 border-l border-white/[0.06] p-4">
          <ChatPanel messages={messages} onSend={handleChat} loading={chatLoading} />
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, sub, severity }: { label: string; value: number; sub: string; severity: 'high' | 'nominal' }) {
  return (
    <div className={`border p-4 ${severity === 'high' ? 'border-red-500/20 bg-red-500/[0.03]' : 'border-white/[0.06] bg-white/[0.02]'}`}>
      <div className={`text-2xl font-bold font-mono ${severity === 'high' ? 'text-red-400' : 'text-white'}`}>
        {value}
      </div>
      <div className="text-[10px] font-mono uppercase tracking-wider text-white/30 mt-1">{label}</div>
      <div className="text-[10px] font-mono text-white/15">{sub}</div>
    </div>
  )
}
