import { useState, useEffect, useMemo } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { SignedIn, SignedOut, SignInButton, SignUpButton, useClerk, useUser } from '@clerk/clerk-react'
import type { UserProfile, NeighborhoodData, DataSources, RiskScore } from '../types/index.ts'
import { api } from '../api.ts'
import RiskCard from './RiskCard.tsx'
import MapView from './MapView.tsx'
import Timer from './Timer.tsx'
import DataSourceBadge from './DataSourceBadge.tsx'
import InspectionTable from './InspectionTable.tsx'
import PermitTable from './PermitTable.tsx'
import LicenseTable from './LicenseTable.tsx'
import NewsFeed from './NewsFeed.tsx'
import CommunityFeed from './CommunityFeed.tsx'
import MarketPanel from './MarketPanel.tsx'
import TrafficCard from './TrafficCard.tsx'
import DemographicsCard from './DemographicsCard.tsx'
import PipelineMonitor from './PipelineMonitor.tsx'
import MLMonitor from './MLMonitor.tsx'
import CCTVFeedCard from './CCTVFeedCard.tsx'
import InsightsCard from './InsightsCard.tsx'
import LocationReportPanel from './LocationReportPanel.tsx'
import Drawer from './Drawer.tsx'
import ProfilePage from './ProfilePage.tsx'

/*
  Legacy chat imports intentionally commented out (not deleted):
  import { useRef } from 'react'
  import type { ChatMessage } from '../types/index.ts'
  import { streamChat } from '../api.ts'
  import type { ProcessStage } from './ProcessFlow.tsx'
  import ChatPanel from './ChatPanel.tsx'
*/

type Tab = 'overview' | 'inspections' | 'permits' | 'licenses' | 'news' | 'community' | 'market' | 'models'

interface ReportAgentInfo {
  agents_deployed: number
  neighborhoods: string[]
  data_points: number
  agent_summaries: Array<{
    name: string
    data_points: number
    sources?: string[]
  }>
}

/*
interface AgentInfo {
  agents_deployed: number
  neighborhoods: string[]
  data_points: number
  agent_summaries?: Array<{
    name: string
    data_points: number
    sources?: string[]
    regulation_count?: number
    error?: boolean
  }>
}
*/

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

  if (data.cctv && data.cctv.cameras.length > 0) {
    const density = data.cctv.density
    factors.push({
      label: `${data.cctv.cameras.length} CCTV cameras — ${density} foot traffic`,
      pct: density === 'high' ? 5 : density === 'medium' ? 10 : 15,
      source: 'cctv',
      severity: density === 'low' ? 'medium' as const : 'low' as const,
      description: `Live CCTV analysis shows ~${data.cctv.avg_pedestrians} avg pedestrians and ~${data.cctv.avg_vehicles} avg vehicles across ${data.cctv.cameras.length} nearby cameras.`,
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

  // Review ratings factor
  const reviews = data.reviews || []
  const ratings = reviews
    .map(r => (r.metadata?.rating as number) || 0)
    .filter(r => r > 0)
  if (ratings.length > 0) {
    const avgRating = ratings.reduce((a, b) => a + b, 0) / ratings.length
    factors.push({
      label: `Avg ${avgRating.toFixed(1)}/5 across ${ratings.length} businesses`,
      pct: Math.round((5 - avgRating) * 5),
      source: 'reviews',
      severity: avgRating < 3.5 ? 'high' as const : avgRating < 4.0 ? 'medium' as const : 'low' as const,
      description: 'Average business review rating in the area.',
    })
  }

  // Traffic congestion factor
  const traffic = data.traffic || []
  const congested = traffic.filter(t =>
    (t.metadata?.congestion_level as string) === 'heavy' || (t.metadata?.congestion_level as string) === 'blocked'
  )
  if (congested.length > 0) {
    factors.push({
      label: `${congested.length} congested traffic zones`,
      pct: congested.length * 10,
      source: 'traffic',
      severity: congested.length > 3 ? 'high' as const : 'medium' as const,
      description: 'Heavy traffic may affect foot traffic and deliveries.',
    })
  }

  const failRate = stats.total > 0 ? stats.failed / stats.total : 0
  const overallScore = Math.min(10, Math.max(1,
    3 + failRate * 4 + (data.license_count > 10 ? 1 : 0) + (data.politics.length > 3 ? 1 : 0)
  ))

  const totalPct = factors.reduce((s, f) => s + f.pct, 0) || 1
  factors.forEach(f => { f.pct = Math.round((f.pct / totalPct) * 100) })

  const totalDataPoints = stats.total + data.permit_count + data.license_count + reviews.length + traffic.length

  return {
    neighborhood: profile.neighborhood,
    business_type: profile.business_type,
    overall_score: Math.round(overallScore * 10) / 10,
    confidence: Math.min(0.95, 0.4 + totalDataPoints * 0.008),
    factors,
    summary: `Analysis of ${profile.neighborhood} for a ${profile.business_type.toLowerCase()} based on ${totalDataPoints} data points across city permits, inspections, licenses, reviews, traffic, and legislative activity.`,
  }
}

interface Props {
  profile: UserProfile
  onReset: () => void
  token?: string | null
  onProfileUpdate?: () => void
  initialProfileDrawerOpen?: boolean
}

export default function Dashboard({ profile, onReset, token, onProfileUpdate, initialProfileDrawerOpen = false }: Props) {
  const { signOut } = useClerk()
  const { user } = useUser()
  const navigate = useNavigate()
  const location = useLocation()
  const [profileDrawerOpen, setProfileDrawerOpen] = useState(
    (initialProfileDrawerOpen || (location.state as { openProfileDrawer?: boolean } | null)?.openProfileDrawer) ?? false,
  )
  const [neighborhoodData, setNeighborhoodData] = useState<NeighborhoodData | null>(null)
  const [sources, setSources] = useState<DataSources | null>(null)
  const [riskScore, setRiskScore] = useState<RiskScore | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  /*
    Legacy ChatPanel state intentionally commented out (not deleted):
    const [messages, setMessages] = useState<ChatMessage[]>([])
    const [chatLoading, setChatLoading] = useState(false)
    const [isStreaming, setIsStreaming] = useState(false)
    const [statusMessage, setStatusMessage] = useState('')
    const [agentInfo, setAgentInfo] = useState<AgentInfo | null>(null)
    const [agentActive, setAgentActive] = useState(false)
    const [agentElapsedMs, setAgentElapsedMs] = useState<number | undefined>(undefined)
    const [processStage, setProcessStage] = useState<ProcessStage>('idle')
    const [chatQuestion, setChatQuestion] = useState('')
    const processLogs = useRef<string[]>([])
    const userId = user?.id ?? `anon_${Date.now()}`
  */

  const refreshData = async () => {
    try {
      const [nbData, srcData] = await Promise.all([
        api.neighborhood(profile.neighborhood, profile.business_type),
        api.sources(),
      ])
      setNeighborhoodData(nbData)
      setSources(srcData)
      setRiskScore(computeRiskScore(nbData, profile))
      setLoading(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    refreshData().then(() => { if (cancelled) return })
    return () => { cancelled = true }
  }, [profile])

  const sourceList = sources
    ? (Object.entries(sources) as Array<[string, { count: number; active: boolean }]>).map(([name, info]) => ({
        name: name.replace('_', ' '),
        count: info.count,
        active: info.active,
      }))
    : []

  const reportAgentInfo = useMemo<ReportAgentInfo | null>(() => {
    if (!sources) return null

    const entries = (Object.entries(sources) as Array<[string, { count: number; active: boolean }]>)
      .map(([name, info]) => ({ name, count: info.count, active: info.active }))
      .filter(s => s.active)

    const dataPointsFromSources = entries.reduce((sum, entry) => sum + entry.count, 0)
    const neighborhoodPoints = neighborhoodData
      ? neighborhoodData.inspection_stats.total +
        neighborhoodData.permit_count +
        neighborhoodData.license_count +
        neighborhoodData.news.length +
        neighborhoodData.politics.length +
        (neighborhoodData.reddit?.length || 0) +
        (neighborhoodData.tiktok?.length || 0) +
        (neighborhoodData.reviews?.length || 0) +
        (neighborhoodData.realestate?.length || 0) +
        (neighborhoodData.traffic?.length || 0)
      : 0

    return {
      agents_deployed: entries.length,
      neighborhoods: [profile.neighborhood],
      data_points: Math.max(dataPointsFromSources, neighborhoodPoints),
      agent_summaries: entries
        .sort((a, b) => b.count - a.count)
        .slice(0, 6)
        .map(entry => ({
          name: entry.name.replaceAll('_', ' '),
          data_points: entry.count,
          sources: [entry.name],
        })),
    }
  }, [sources, neighborhoodData, profile.neighborhood])

  /*
    Legacy ChatPanel handler intentionally commented out (not deleted):
    const handleChat = async (message: string) => {
      setMessages(prev => [...prev, { role: 'user', content: message, timestamp: new Date() }])
      setChatLoading(true)
      setAgentActive(true)
      setAgentInfo(null)
      setStatusMessage('')
      setProcessStage('deploying')
      setChatQuestion(message)
      processLogs.current = [`--- query ---\n${message}\n\n--- trace ---`, `[${new Date().toISOString()}] start`]
      const startTime = Date.now()
      let responseAccum = ''

      // Add empty assistant message for streaming
      setMessages(prev => [...prev, { role: 'assistant', content: '', timestamp: new Date() }])
      setIsStreaming(true)

      try {
        await streamChat(message, profile, {
          onStatus: (content) => {
            setStatusMessage(content)
            processLogs.current.push(`[+${Date.now() - startTime}ms] status: ${content}`)
            if (content.toLowerCase().includes('synth')) {
              setProcessStage('synthesizing')
            }
          },
          onAgents: (data) => {
            setAgentInfo(data)
            setAgentActive(false)
            setAgentElapsedMs(Date.now() - startTime)
            setProcessStage('agents_complete')
            processLogs.current.push(`[+${Date.now() - startTime}ms] agents: ${data.agents_deployed} deployed, ${data.data_points} pts, neighborhoods=[${data.neighborhoods.join(', ')}]`)
            if (data.agent_summaries) {
              for (const a of data.agent_summaries) {
                processLogs.current.push(`  agent ${a.name}: ${a.data_points} pts${a.sources ? ` sources=[${a.sources.join(',')}]` : ''}${a.regulation_count ? ` regs=${a.regulation_count}` : ''}${a.error ? ' ERROR' : ''}`)
              }
            }
          },
          onToken: (token) => {
            setStatusMessage('')
            setProcessStage('streaming')
            responseAccum += token
            setMessages(prev => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              if (last && last.role === 'assistant') {
                updated[updated.length - 1] = { ...last, content: last.content + token }
              }
              return updated
            })
          },
          onDone: () => {
            setIsStreaming(false)
            setChatLoading(false)
            setProcessStage('complete')
            processLogs.current.push(`[+${Date.now() - startTime}ms] done, total=${Date.now() - startTime}ms`)
            processLogs.current.push(`\n--- response ---\n${responseAccum}`)

            if (user) {
              api.saveUserSettings(user.id, profile.business_type, profile.neighborhood).catch(() => {})
            }

            setMessages(prev => {
              const updated = [...prev]
              updated[updated.length - 1] = { ...updated[updated.length - 1], timestamp: new Date() }
              return updated
            })

            // Auto-refresh data after chat — TikTok scrape may have landed new data on volume
            setTimeout(() => refreshData(), 30_000)
          },
          onError: (_errorMsg) => {
            // Fallback to local response
            setIsStreaming(false)
            setAgentActive(false)
            setStatusMessage('')
            setProcessStage('complete')
            processLogs.current.push(`[+${Date.now() - startTime}ms] error: ${_errorMsg} (local fallback)`)

            const nb = profile.neighborhood
            const biz = profile.business_type.toLowerCase()
            let response = ''

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
              response += `- **Total inspections:** ${stats.total}\n- **Passed:** ${stats.passed}\n- **Failed:** ${stats.failed}\n`
              if (stats.total > 0) {
                response += `- **Pass rate:** ${Math.round((stats.passed / stats.total) * 100)}%\n`
              }
              response += `\nThis data helps gauge the regulatory environment you'll be operating in.`
            } else if (message.toLowerCase().includes('competition') || message.toLowerCase().includes('business')) {
              const licenses = neighborhoodData?.licenses || []
              response = `There are **${licenses.length}** active business licenses in ${nb}.\n\n`
              if (licenses.length > 0) {
                response += 'Nearby businesses include:\n'
                response += licenses.slice(0, 5).map(l => {
                  const r = l.metadata?.raw_record || {} as Record<string, string>
                  return `- ${r.doing_business_as_name || r.legal_name || 'Unknown'} (${r.license_description || 'Business'})`
                }).join('\n')
              }
            } else {
              const total = (neighborhoodData?.inspection_stats.total || 0) + (neighborhoodData?.permit_count || 0) + (neighborhoodData?.license_count || 0)
              response = `Here's what I found about **${nb}** for a ${biz}:\n\n`
              response += `We analyzed **${total}** data points across food inspections, building permits, and business licenses.\n\n`
              if (riskScore) {
                response += `**Risk score:** ${riskScore.overall_score}/10 (${riskScore.overall_score <= 4 ? 'low' : riskScore.overall_score <= 7 ? 'moderate' : 'high'} risk)\n\n`
              }
              response += 'Ask me about specific topics: permits, inspections, competition, or zoning.'
            }

            processLogs.current.push(`\n--- response (local fallback) ---\n${response}`)
            setMessages(prev => {
              const updated = [...prev]
              updated[updated.length - 1] = { role: 'assistant', content: response, timestamp: new Date() }
              return updated
            })
            setChatLoading(false)
          },
        }, userId)
      } catch {
        setIsStreaming(false)
        setChatLoading(false)
        setAgentActive(false)
        setProcessStage('complete')
      }
    }
  */

  const allTabs: { key: Tab; label: string; count?: number; isEmpty?: () => boolean }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'inspections', label: 'Inspections', count: neighborhoodData?.inspection_stats.total, isEmpty: () => !(neighborhoodData?.inspection_stats.total ?? 0) },
    { key: 'permits', label: 'Permits', count: neighborhoodData?.permit_count, isEmpty: () => !(neighborhoodData?.permit_count ?? 0) },
    { key: 'licenses', label: 'Licenses', count: neighborhoodData?.license_count, isEmpty: () => !(neighborhoodData?.license_count ?? 0) },
    { key: 'news', label: 'Intel', count: (neighborhoodData?.news.length || 0) + (neighborhoodData?.politics.length || 0), isEmpty: () => !((neighborhoodData?.news.length || 0) + (neighborhoodData?.politics.length || 0)) },
    { key: 'community', label: 'Community', count: (neighborhoodData?.reddit?.length || 0) + (neighborhoodData?.tiktok?.length || 0), isEmpty: () => !((neighborhoodData?.reddit?.length || 0) + (neighborhoodData?.tiktok?.length || 0)) },
    { key: 'market', label: 'Market', count: (neighborhoodData?.reviews?.length || 0) + (neighborhoodData?.realestate?.length || 0), isEmpty: () => !((neighborhoodData?.reviews?.length || 0) + (neighborhoodData?.realestate?.length || 0)) },
    { key: 'models', label: 'Models' },
  ]
  const tabs = useMemo(
    () => allTabs.filter(t => !t.isEmpty || !(t.isEmpty?.() ?? false)),
    [
      neighborhoodData?.inspection_stats.total,
      neighborhoodData?.permit_count,
      neighborhoodData?.license_count,
      neighborhoodData?.news.length,
      neighborhoodData?.politics.length,
      neighborhoodData?.reddit?.length,
      neighborhoodData?.tiktok?.length,
      neighborhoodData?.reviews?.length,
      neighborhoodData?.realestate?.length,
    ]
  )
  const visibleTabKeys = useMemo(() => tabs.map(t => t.key), [tabs])

  useEffect(() => {
    if (!visibleTabKeys.includes(activeTab)) {
      setActiveTab(visibleTabKeys.includes('overview') ? 'overview' : (visibleTabKeys[0] ?? 'overview'))
    }
  }, [visibleTabKeys, activeTab])

  return (
    <div className="h-screen flex flex-col bg-[#06080d]">
      {/* Top bar */}
      <header className="flex items-center justify-between px-6 py-3 bg-white/[0.02] backdrop-blur-md border-b border-white/[0.06]">
        <div className="flex items-center gap-5">
          <button
            type="button"
            onClick={onReset}
            className="text-sm font-semibold text-white uppercase tracking-wide hover:text-white/80 transition-colors cursor-pointer"
          >
            Aleithia
          </button>
          <div className="h-3.5 w-px bg-white/10" />
          <span className="text-xs font-mono text-white/30">
            {profile.business_type} <span className="text-white/10 mx-1">/</span> <span className="text-white/50">{profile.neighborhood}</span>
          </span>
        </div>
        <div className="flex items-center gap-3">
          <Timer running={loading} />
          <button onClick={refreshData} className="text-[10px] font-mono uppercase tracking-wider text-white/20 hover:text-white/50 transition-colors cursor-pointer">
            Refresh
          </button>

          <SignedOut>
            <SignInButton mode="modal">
              <button className="text-[10px] font-mono uppercase tracking-wider text-white/30 hover:text-white/60 transition-colors cursor-pointer">
                Auth
              </button>
            </SignInButton>
            <SignUpButton mode="modal">
              <button className="text-[10px] font-mono uppercase tracking-wider text-white hover:text-white/80 transition-colors cursor-pointer">
                Initialize
              </button>
            </SignUpButton>
          </SignedOut>

          <SignedIn>
            {user && <span className="text-[10px] font-mono text-white/25">{user.primaryEmailAddress?.emailAddress}</span>}
            <button onClick={() => setProfileDrawerOpen(true)} className="text-[10px] font-mono uppercase tracking-wider text-white/20 hover:text-white/50 transition-colors cursor-pointer">
              Profile
            </button>
            <button onClick={() => signOut()} className="text-[10px] font-mono uppercase tracking-wider text-white/20 hover:text-white/50 transition-colors cursor-pointer">
              Sign out
            </button>
          </SignedIn>

          <button onClick={onReset} className="text-[10px] font-mono uppercase tracking-wider text-white/20 hover:text-white/50 transition-colors cursor-pointer">
            New Search
          </button>
        </div>
      </header>

      {error && (
        <div className="mx-6 mt-4 p-4 bg-red-500/[0.06] border border-red-500/20 text-red-400/80 text-xs font-mono">
          {error} — Check that VITE_MODAL_URL is set or the Modal backend is deployed
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex min-h-0">
        {/* Left: Data */}
        <div className="flex-1 flex flex-col p-4 gap-4 overflow-y-auto">
          {/* Pipeline Monitor */}
          <PipelineMonitor />

          {/* Data sources */}
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
                  {/* HUD quadrant grid: Map + Risk | Demographics */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className="h-[280px] min-h-0">
                      <MapView activeNeighborhood={profile.neighborhood} />
                    </div>
                    <div className="min-h-0">
                      {riskScore ? <RiskCard score={riskScore} /> : <div className="h-full border border-white/[0.06] bg-white/[0.01] p-6 flex items-center justify-center"><span className="text-[10px] font-mono text-white/20">Loading risk assessment</span></div>}
                    </div>
                  </div>

                  {/* Quadrant 2: Demographics + Insights */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {neighborhoodData?.metrics && (
                      <DemographicsCard metrics={neighborhoodData.metrics} demographics={neighborhoodData.demographics} cctv={neighborhoodData.cctv} />
                    )}
                    {neighborhoodData && (
                      <InsightsCard data={neighborhoodData} profile={profile} />
                    )}
                  </div>

                  {neighborhoodData?.traffic && neighborhoodData.traffic.length > 0 && (
                    <TrafficCard data={neighborhoodData.traffic} />
                  )}

                  {neighborhoodData?.cctv && neighborhoodData.cctv.cameras.length > 0 && (
                    <CCTVFeedCard cctv={neighborhoodData.cctv} />
                  )}

                  {neighborhoodData && (
                    <div className="grid grid-cols-3 lg:grid-cols-7 gap-3">
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
                      <StatCard
                        label="Business Reviews"
                        value={neighborhoodData.reviews?.length || 0}
                        sub={neighborhoodData.metrics.avg_review_rating > 0 ? `avg ${neighborhoodData.metrics.avg_review_rating}/5` : 'listings'}
                        severity="nominal"
                      />
                      <StatCard
                        label="Community"
                        value={(neighborhoodData.reddit?.length || 0) + (neighborhoodData.tiktok?.length || 0)}
                        sub="posts"
                        severity="nominal"
                      />
                      <StatCard
                        label="CCTV Cameras"
                        value={neighborhoodData.cctv?.cameras.length ?? 0}
                        sub={neighborhoodData.cctv?.density ?? 'no data'}
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
                        <div className="text-[10px] font-mono uppercase tracking-wider text-white/20 mb-1">Aleithia</div>
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

              {activeTab === 'community' && neighborhoodData && (
                <CommunityFeed reddit={neighborhoodData.reddit || []} tiktok={neighborhoodData.tiktok || []} />
              )}

              {activeTab === 'market' && neighborhoodData && (
                <MarketPanel reviews={neighborhoodData.reviews || []} realestate={neighborhoodData.realestate || []} />
              )}

              {activeTab === 'models' && (
                <MLMonitor />
              )}
            </>
          )}
        </div>

        {/* Right: Report */}
        <div className="w-96 border-l-2 border-[#2B95D6]/40 p-4" style={{ boxShadow: '-4px 0 24px rgba(43, 149, 214, 0.08)' }}>
          {/*
            <ChatPanel
              messages={messages}
              onSend={handleChat}
              loading={chatLoading}
              isStreaming={isStreaming}
              agentInfo={agentInfo}
              agentActive={agentActive}
              agentElapsedMs={agentElapsedMs}
              statusMessage={statusMessage}
              processStage={processStage}
              chatQuestion={chatQuestion}
              processLogs={processLogs.current}
            />
          */}
          <LocationReportPanel
            profile={profile}
            neighborhoodData={neighborhoodData}
            riskScore={riskScore}
            loading={loading}
            agentInfo={reportAgentInfo}
          />
        </div>
      </div>

      <Drawer
        open={profileDrawerOpen}
        onClose={() => setProfileDrawerOpen(false)}
        title="Profile"
        width="max-w-md"
      >
        <ProfilePage
          token={token}
          onClose={() => setProfileDrawerOpen(false)}
          onProfileUpdate={onProfileUpdate}
          embedded
        />
      </Drawer>
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
