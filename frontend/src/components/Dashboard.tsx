import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { SignedIn, SignedOut, SignInButton, SignUpButton, useClerk, useUser } from '@clerk/clerk-react'
import type { UserProfile, NeighborhoodData, DataSources, RiskScore, CCTVData, ParkingData } from '../types/index.ts'
import { api, API_BASE, fetchTrends, type TrendData } from '../api.ts'
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
import DemographicsCard from './DemographicsCard.tsx'
import PipelineMonitor from './PipelineMonitor.tsx'
import MLMonitor from './MLMonitor.tsx'
import CCTVCameraCard from './CCTVCameraCard.tsx'
import CCTVCameraDrawer from './CCTVCameraDrawer.tsx'
import InsightsCard from './InsightsCard.tsx'
import CityGraph from './CityGraph.tsx'
import LocationReportPanel from './LocationReportPanel.tsx'
import FootTrafficChart from './FootTrafficChart.tsx'
import StreetscapeCard from './StreetscapeCard.tsx'
import RecursiveAgentPanel from './RecursiveAgentPanel.tsx'
import Drawer from './Drawer.tsx'
import ProfilePage from './ProfilePage.tsx'
import ShinyText from './ShinyText.tsx'
import LoadingFlow from './LoadingFlow.tsx'
import { InspectionOutcomesChart, TopViolationsPareto, AlertHoursStackedArea } from './VaultCharts.tsx'

/*
  Legacy chat imports intentionally commented out (not deleted):
  import { useRef } from 'react'
  import type { ChatMessage } from '../types/index.ts'
  import { streamChat } from '../api.ts'
  import type { ProcessStage } from './ProcessFlow.tsx'
  import ChatPanel from './ChatPanel.tsx'
*/

type Tab = 'overview' | 'regulatory' | 'intel' | 'community' | 'market' | 'vision' | 'models' | 'vault'

interface ReportAgentInfo {
  agents_deployed: number
  neighborhoods: string[]
  data_points: number
  agent_summaries: Array<{
    name: string
    data_points: number
    sources?: string[]
    error?: boolean
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

/**
 * Multi-Criteria Risk Assessment using Weighted Linear Combination (WLC).
 *
 * Methodology (ISO 31000-aligned):
 * 1. Logistic normalization of each input to [0, 1] risk scale
 *    — standard in risk modeling; smooth, bounded, handles outliers
 * 2. Dimensional weighting from MCDA literature for commercial site selection
 * 3. WLC aggregation: risk = Σ(wᵢ · rᵢ) / Σ(wᵢ) over available dimensions
 * 4. Confidence from dimensional coverage (breadth) + data depth
 *
 * Risk dimensions (weights sum to 1.0):
 *   Regulatory compliance  0.25 — inspection failure rates
 *   Market competition      0.20 — license density, review quality
 *   Economic vitality       0.20 — permit/construction activity
 *   Accessibility           0.15 — highway traffic, congestion, CTA transit
 *   Political stability     0.10 — legislative activity volume
 *   Community presence      0.10 — news + social media visibility
 */
function computeRiskScore(data: NeighborhoodData, profile: UserProfile): RiskScore {
  // Logistic (sigmoid) normalization: f(x) = 1 / (1 + e^(-k(x - x₀)))
  // x₀ = midpoint (output 0.5), k = steepness
  const logistic = (x: number, x0: number, k: number) =>
    1 / (1 + Math.exp(-k * (x - x0)))

  // MCDA dimensional weights — commercial site selection literature
  const W = {
    regulatory: 0.25,
    market: 0.20,
    economic: 0.20,
    accessibility: 0.15,
    political: 0.10,
    community: 0.10,
  }

  const scored: Array<{
    label: string; source: string; severity: 'low' | 'medium' | 'high'
    description: string; risk: number; weight: number; dimension: string
  }> = []

  const stats = data.inspection_stats

  // ── Regulatory Compliance (25%) — inspection fail rate ──────────────
  if (stats.total > 0) {
    const failRate = stats.failed / stats.total
    // Chicago city-wide avg fail rate ~22%; calibrated midpoint
    const risk = logistic(failRate, 0.22, 8)
    scored.push({
      label: `${stats.failed} of ${stats.total} inspections failed`,
      source: 'food_inspections',
      severity: failRate > 0.35 ? 'high' : failRate > 0.18 ? 'medium' : 'low',
      description: `${Math.round(failRate * 100)}% failure rate (city avg ~22%). ${stats.passed} passed, ${stats.failed} failed.`,
      risk, weight: W.regulatory, dimension: 'regulatory',
    })
  }

  // ── Market Competition (20%) — license density + review quality ────
  if (data.license_count > 0) {
    // More licenses = more competition = higher risk for new entrant
    const risk = logistic(data.license_count, 12, 0.25)
    scored.push({
      label: `${data.license_count} active business licenses`,
      source: 'business_licenses',
      severity: data.license_count > 20 ? 'high' : data.license_count > 10 ? 'medium' : 'low',
      description: `Higher license density means more competition for new entrants.`,
      risk, weight: W.market * 0.5, dimension: 'market',
    })
  }

  const reviews = data.reviews || []
  const ratings = reviews
    .map(r => (r.metadata?.rating as number) || 0)
    .filter(r => r > 0)
  if (ratings.length > 0) {
    const avgRating = ratings.reduce((a, b) => a + b, 0) / ratings.length
    // Inverted: lower area ratings = higher risk for new business
    const risk = 1 - logistic(avgRating, 3.5, 3)
    scored.push({
      label: `Avg ${avgRating.toFixed(1)}/5 across ${ratings.length} businesses`,
      source: 'reviews',
      severity: avgRating < 3.5 ? 'high' : avgRating < 4.0 ? 'medium' : 'low',
      description: `Area business quality indicator. Low ratings suggest market challenges.`,
      risk, weight: W.market * 0.5, dimension: 'market',
    })
  }

  // ── Economic Vitality (20%) — permit/construction activity ─────────
  if (data.permit_count > 0) {
    // Inverted: more permits = active development = lower risk
    const risk = 1 - logistic(data.permit_count, 8, 0.3)
    scored.push({
      label: `${data.permit_count} active building permits`,
      source: 'building_permits',
      severity: data.permit_count < 3 ? 'medium' : 'low',
      description: `Construction activity signals economic investment and area development.`,
      risk, weight: W.economic, dimension: 'economic',
    })
  }

  // ── Accessibility (15%) — highway traffic + congestion + transit ────
  if (data.cctv && data.cctv.cameras.length > 0) {
    // Low highway traffic = potentially less accessible area
    const densityRisk: Record<string, number> = { low: 0.7, medium: 0.4, high: 0.15 }
    const risk = densityRisk[data.cctv.density] ?? 0.5
    scored.push({
      label: `${data.cctv.cameras.length} IDOT cameras — ${data.cctv.density} highway traffic`,
      source: 'cctv',
      severity: data.cctv.density === 'low' ? 'medium' : 'low',
      description: `Highway proximity via ~${Math.round(data.cctv.avg_vehicles)} avg vehicles on nearby expressways.`,
      risk, weight: W.accessibility * 0.35, dimension: 'accessibility',
    })
  }

  const traffic = data.traffic || []
  if (traffic.length > 0) {
    const congested = traffic.filter(t =>
      ['heavy', 'blocked'].includes((t.metadata?.congestion_level as string) || '')
    )
    const congestionRatio = congested.length / traffic.length
    const risk = logistic(congestionRatio, 0.3, 6)
    scored.push({
      label: `${congested.length} of ${traffic.length} traffic zones congested`,
      source: 'traffic',
      severity: congestionRatio > 0.5 ? 'high' : congestionRatio > 0.2 ? 'medium' : 'low',
      description: `Congestion affects deliveries and customer access.`,
      risk, weight: W.accessibility * 0.3, dimension: 'accessibility',
    })
  }

  if (data.transit && data.transit.stations_nearby > 0) {
    // Inverted: more transit = more walk-in customers = lower risk
    const risk = 1 - logistic(data.transit.stations_nearby, 3, 1.0)
    const stationList = data.transit.station_names.slice(0, 3).join(', ')
    const ridersLabel = data.transit.total_daily_riders > 0
      ? `~${Math.round(data.transit.total_daily_riders / 1000)}K daily riders`
      : ''
    scored.push({
      label: `${data.transit.stations_nearby} CTA stations nearby`,
      source: 'transit',
      severity: data.transit.stations_nearby < 2 ? 'medium' : 'low',
      description: `${stationList}${ridersLabel ? ` — ${ridersLabel}` : ''}. Transit access drives foot traffic.`,
      risk, weight: W.accessibility * 0.35, dimension: 'accessibility',
    })
  }

  // ── Political Stability (10%) — legislative activity ───────────────
  if (data.politics.length > 0) {
    // More legislative activity = more regulatory uncertainty
    const risk = logistic(data.politics.length, 5, 0.4)
    scored.push({
      label: `${data.politics.length} legislative items`,
      source: 'politics',
      severity: data.politics.length > 8 ? 'high' : data.politics.length > 3 ? 'medium' : 'low',
      description: `Active legislation creates regulatory uncertainty for businesses.`,
      risk, weight: W.political, dimension: 'political',
    })
  }

  // ── Community Presence (10%) — news + social ───────────────────────
  const redditCount = data.reddit?.length || 0
  const totalMentions = data.news.length + redditCount
  if (totalMentions > 0) {
    // Inverted: low visibility = slightly higher risk (unknown area)
    const risk = 1 - logistic(totalMentions, 8, 0.3)
    scored.push({
      label: `${data.news.length} news + ${redditCount} social mentions`,
      source: 'news + social',
      severity: totalMentions < 3 ? 'medium' : 'low',
      description: `Community visibility and engagement level.`,
      risk, weight: W.community, dimension: 'community',
    })
  }

  // ── Weighted Linear Combination ────────────────────────────────────
  if (scored.length === 0) {
    return {
      neighborhood: profile.neighborhood,
      business_type: profile.business_type,
      overall_score: 5.0,
      confidence: 0.10,
      factors: [],
      summary: `Insufficient data for ${profile.neighborhood}. More pipeline data needed for risk assessment.`,
    }
  }

  let weightedRisk = 0
  let totalWeight = 0
  for (const s of scored) {
    weightedRisk += s.risk * s.weight
    totalWeight += s.weight
  }
  const normalizedRisk = weightedRisk / totalWeight
  const overallScore = Math.round(normalizedRisk * 100) / 10 // 0–10 scale

  // Factor contribution percentages (each factor's share of total weighted risk)
  const totalContribution = scored.reduce((sum, s) => sum + s.risk * s.weight, 0) || 1
  const factors = scored.map(s => ({
    label: s.label,
    pct: Math.max(1, Math.round((s.risk * s.weight / totalContribution) * 100)),
    source: s.source,
    severity: s.severity,
    description: s.description,
  }))

  // Confidence: 60% dimensional coverage + 40% data depth
  const dimensionsCovered = new Set(scored.map(s => s.dimension)).size
  const totalDimensions = Object.keys(W).length
  const coverage = dimensionsCovered / totalDimensions
  const totalDataPoints = stats.total + data.permit_count + data.license_count
    + ratings.length + traffic.length + (data.cctv?.cameras.length || 0)
    + data.news.length + data.politics.length + redditCount
    + (data.transit?.stations_nearby || 0)
  const depth = Math.min(1, totalDataPoints / 50)
  const confidence = Math.min(0.95, Math.round((coverage * 0.6 + depth * 0.4) * 100) / 100)

  return {
    neighborhood: profile.neighborhood,
    business_type: profile.business_type,
    overall_score: overallScore,
    confidence,
    factors,
    summary: `Multi-criteria risk assessment of ${profile.neighborhood} for ${profile.business_type.toLowerCase()} across ${dimensionsCovered} dimensions using ${totalDataPoints} data points.`,
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
  const [trends, setTrends] = useState<TrendData | null>(null)

  // Resizable sidebar
  const SIDEBAR_DEFAULT = 540
  const SIDEBAR_MIN = 360
  const SIDEBAR_MAX = 720
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT)
  const isDragging = useRef(false)
  const startX = useRef(0)
  const startWidth = useRef(SIDEBAR_DEFAULT)

  const onDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isDragging.current = true
    startX.current = e.clientX
    startWidth.current = sidebarWidth
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    const onMouseMove = (ev: MouseEvent) => {
      if (!isDragging.current) return
      const delta = startX.current - ev.clientX // dragging left = wider sidebar
      const newWidth = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, startWidth.current + delta))
      setSidebarWidth(newWidth)
    }

    const onMouseUp = () => {
      isDragging.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }, [sidebarWidth])

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
    const [memoryInfo, setMemoryInfo] = useState<import('../api.ts').MemoryInfo | null>(null)
    const [suggestions, setSuggestions] = useState<string[]>([])
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
      // Fetch trends (non-blocking)
      fetchTrends(profile.neighborhood).then(t => setTrends(t)).catch(() => {})
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
          onMemory: (data) => {
            setMemoryInfo(data)
            processLogs.current.push(`[+${Date.now() - startTime}ms] memory: profile=${data.has_profile}, past=${data.past_interactions}`)
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
          onSuggestions: (questions) => {
            setSuggestions(questions)
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

  const regulatoryCount = (neighborhoodData?.inspection_stats.total || 0) + (neighborhoodData?.permit_count || 0) + (neighborhoodData?.license_count || 0)
  const allTabs: { key: Tab; label: string; count?: number; isEmpty?: () => boolean }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'regulatory', label: 'Regulatory', count: regulatoryCount, isEmpty: () => !regulatoryCount },
    { key: 'intel', label: 'News & Policy', count: (neighborhoodData?.news.length || 0) + (neighborhoodData?.politics.length || 0), isEmpty: () => !((neighborhoodData?.news.length || 0) + (neighborhoodData?.politics.length || 0)) },
    { key: 'community', label: 'Community', count: (neighborhoodData?.reddit?.length || 0) + (neighborhoodData?.tiktok?.length || 0), isEmpty: () => !((neighborhoodData?.reddit?.length || 0) + (neighborhoodData?.tiktok?.length || 0)) },
    { key: 'market', label: 'Market', count: (neighborhoodData?.reviews?.length || 0) + (neighborhoodData?.realestate?.length || 0), isEmpty: () => !((neighborhoodData?.reviews?.length || 0) + (neighborhoodData?.realestate?.length || 0)) },
    { key: 'vision', label: 'Vision', count: neighborhoodData?.cctv?.cameras.length || 0, isEmpty: () => false },
    { key: 'models', label: 'Models' },
    { key: 'vault', label: 'Vault' },
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
      neighborhoodData?.cctv?.cameras.length,
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
            className="text-sm font-semibold uppercase tracking-wide text-white/70 hover:text-white transition-colors duration-300 cursor-pointer"
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

          <button onClick={() => navigate('/start')} className="text-[10px] font-mono uppercase tracking-wider text-white/20 hover:text-white/50 transition-colors cursor-pointer">
            New Search
          </button>
        </div>
      </header>

      {error && (
        <div className="mx-6 mt-4 p-4 bg-red-500/[0.06] border border-red-500/20 text-red-400/80 text-xs font-mono space-y-2">
          <p>{error}</p>
          <p className="text-white/50">
            API: {API_BASE} — Restart dev server after changing <code className="bg-white/10 px-1">frontend/.env</code>. Deploy: <code className="bg-white/10 px-1">modal deploy modal_app/__init__.py</code>
          </p>
          <button
            onClick={() => { setError(null); setLoading(true); refreshData() }}
            className="mt-2 px-3 py-1.5 text-[10px] font-medium border border-white/20 text-white/70 hover:text-white hover:border-white/40 transition-colors cursor-pointer"
          >
            Retry
          </button>
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
            <LoadingFlow neighborhood={profile.neighborhood} />
          ) : (
            <>
              {activeTab === 'overview' && trends?.congestion.anomalies && trends.congestion.anomalies.length > 0 && (
                <div className="border border-red-500/20 bg-red-500/[0.04] px-4 py-3 flex items-center gap-3">
                  <span className="text-red-400 text-xs font-mono font-bold">ALERT</span>
                  <span className="text-xs text-white/50">
                    {trends.congestion.anomalies.length} traffic anomal{trends.congestion.anomalies.length === 1 ? 'y' : 'ies'} detected:
                    {' '}{trends.congestion.anomalies.map(a => a.road).join(', ')}
                  </span>
                </div>
              )}

              {activeTab === 'overview' && (
                <div className="space-y-4">
                  {/* Map hero (left) + Unified Risk/Insights panel (right) */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className="h-[600px] min-h-0">
                      <MapView activeNeighborhood={profile.neighborhood} />
                    </div>

                    <div className="min-h-0 flex flex-col border border-white/[0.06] bg-white/[0.01] overflow-x-hidden lg:max-h-[600px] lg:overflow-y-auto hide-scrollbar">
                      {riskScore ? (
                        <RiskCard score={riskScore} borderless />
                      ) : (
                        <div className="p-6 flex items-center justify-center">
                          <span className="text-[10px] font-mono text-white/20">Loading risk assessment</span>
                        </div>
                      )}
                      {neighborhoodData && (
                        <InsightsCard data={neighborhoodData} profile={profile} onTabChange={(tab) => setActiveTab(tab as Tab)} borderless />
                      )}
                    </div>
                  </div>

                  {/* Full-width demographics strip */}
                  {neighborhoodData?.metrics && (
                    <DemographicsCard metrics={neighborhoodData.metrics} demographics={neighborhoodData.demographics} horizontal />
                  )}
                </div>
              )}

              {activeTab === 'regulatory' && neighborhoodData && (
                <RegulatorySubTabs neighborhoodData={neighborhoodData} />
              )}

              {activeTab === 'intel' && neighborhoodData && (
                <NewsFeed news={neighborhoodData.news} politics={neighborhoodData.politics} />
              )}

              {activeTab === 'community' && neighborhoodData && (
                <CommunityFeed
                  reddit={neighborhoodData.reddit || []}
                  tiktok={neighborhoodData.tiktok || []}
                />
              )}

              {activeTab === 'market' && neighborhoodData && (
                <MarketPanel reviews={neighborhoodData.reviews || []} realestate={neighborhoodData.realestate || []} />
              )}

              {activeTab === 'vision' && (
                <VisionTab cctv={neighborhoodData?.cctv ?? null} parking={neighborhoodData?.parking ?? null} neighborhood={profile.neighborhood} />
              )}

              {activeTab === 'models' && (
                <div className="space-y-4">
                  <RecursiveAgentPanel />
                  <CityGraph activeNeighborhood={profile.neighborhood} interactive />
                  <MLMonitor />
                </div>
              )}

              {activeTab === 'vault' && (
                <VaultTab
                  onOpenGraph={() => navigate('/memory-graph')}
                  dataPoints={reportAgentInfo?.data_points ?? 0}
                  neighborhood={profile.neighborhood}
                />
              )}
            </>
          )}
        </div>

        {/* Right: Resizable Report Sidebar */}
        <div className="relative shrink-0 flex" style={{ width: sidebarWidth }}>
          {/* Drag handle */}
          <div
            onMouseDown={onDragStart}
            className="absolute left-0 top-0 bottom-0 w-1.5 z-10 cursor-col-resize group hover:bg-[#2B95D6]/30 transition-colors"
          >
            <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-[#2B95D6]/40 group-hover:bg-[#2B95D6]/80 transition-colors" />
          </div>
          <div className="flex-1 p-4 overflow-y-auto" style={{ boxShadow: '-4px 0 24px rgba(43, 149, 214, 0.08)' }}>
            {/*
              <ChatPanel
                messages={messages}
                onSend={(msg) => { setSuggestions([]); handleChat(msg) }}
                loading={chatLoading}
                isStreaming={isStreaming}
                agentInfo={agentInfo}
                agentActive={agentActive}
                agentElapsedMs={agentElapsedMs}
                statusMessage={statusMessage}
                processStage={processStage}
                chatQuestion={chatQuestion}
                processLogs={processLogs.current}
                memoryInfo={memoryInfo}
                suggestions={suggestions}
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

function VisionTab({ cctv, parking, neighborhood }: { cctv: CCTVData | null; parking: ParkingData | null; neighborhood: string }) {
  const [expandedCam, setExpandedCam] = useState<string | null>(null)
  const cameras = cctv?.cameras ?? []

  // Aggregate stats
  const totalPeds = cameras.reduce((s, c) => s + c.pedestrians, 0)
  const totalVehs = cameras.reduce((s, c) => s + c.vehicles, 0)
  const totalBikes = cameras.reduce((s, c) => s + c.bicycles, 0)
  const totalDetections = totalPeds + totalVehs + totalBikes
  const pedPct = totalDetections > 0 ? Math.round((totalPeds / totalDetections) * 100) : 0
  const vehPct = totalDetections > 0 ? Math.round((totalVehs / totalDetections) * 100) : 0
  const bikePct = totalDetections > 0 ? 100 - pedPct - vehPct : 0

  const densityCounts = { high: 0, medium: 0, low: 0, unknown: 0 }
  for (const c of cameras) densityCounts[c.density_level]++
  const avgDensity = cameras.length > 0
    ? (densityCounts.high >= densityCounts.medium && densityCounts.high >= densityCounts.low ? 'high' : densityCounts.medium >= densityCounts.low ? 'medium' : 'low')
    : 'n/a'

  const selectedCamera = expandedCam ? cameras.find(c => c.camera_id === expandedCam) : null

  return (
    <div className="space-y-4">
      {/* Streetscape Intelligence */}
      <StreetscapeCard neighborhood={neighborhood} />

      {/* Satellite Parking Detection */}
      {parking && parking.parking_lots.length > 0 && (
        <>
          <div className="border border-white/[0.06] bg-white/[0.02] p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30">
                Satellite Parking Detection
              </h3>
              <span className="text-[9px] font-mono px-2 py-0.5 border border-white/10 text-white/25">
                SegFormer + YOLOv8m
              </span>
            </div>

            {/* Stat grid */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
              <div className="border border-white/[0.06] bg-white/[0.02] p-3">
                <div className="text-xl font-bold font-mono text-white">{parking.parking_lots.length}</div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mt-1">Lots Detected</div>
              </div>
              <div className="border border-white/[0.06] bg-white/[0.02] p-3">
                <div className="text-xl font-bold font-mono text-blue-400">{parking.total_capacity}</div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mt-1">Total Capacity</div>
              </div>
              <div className="border border-white/[0.06] bg-white/[0.02] p-3">
                <div className="text-xl font-bold font-mono text-green-400">{parking.total_vehicles}</div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mt-1">Vehicles</div>
              </div>
              <div className="border border-white/[0.06] bg-white/[0.02] p-3">
                <div className={`text-xl font-bold font-mono ${parking.overall_occupancy > 0.85 ? 'text-red-400' : parking.overall_occupancy > 0.6 ? 'text-amber-400' : 'text-green-400'}`}>
                  {Math.round(parking.overall_occupancy * 100)}%
                </div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mt-1">Occupancy</div>
              </div>
            </div>

            {/* Annotated satellite image */}
            <div className="relative aspect-video bg-black/40 overflow-hidden mb-4">
              <img
                src={api.parkingAnnotatedUrl(neighborhood)}
                alt={`Parking analysis — ${neighborhood}`}
                className="w-full h-full object-contain"
                onError={e => { e.currentTarget.style.display = 'none' }}
              />
            </div>

            {/* Per-lot breakdown table */}
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-white/[0.04]">
                    <th className="px-3 py-2 text-[9px] font-mono uppercase tracking-wider text-white/20 font-medium">#</th>
                    <th className="px-3 py-2 text-[9px] font-mono uppercase tracking-wider text-white/20 font-medium">Area</th>
                    <th className="px-3 py-2 text-[9px] font-mono uppercase tracking-wider text-white/20 font-medium">Capacity</th>
                    <th className="px-3 py-2 text-[9px] font-mono uppercase tracking-wider text-white/20 font-medium">Vehicles</th>
                    <th className="px-3 py-2 text-[9px] font-mono uppercase tracking-wider text-white/20 font-medium">Occupancy</th>
                    <th className="px-3 py-2 text-[9px] font-mono uppercase tracking-wider text-white/20 font-medium">Location</th>
                  </tr>
                </thead>
                <tbody>
                  {parking.parking_lots.map((lot, i) => (
                    <tr key={i} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                      <td className="px-3 py-2 text-xs font-mono text-white/30">{i + 1}</td>
                      <td className="px-3 py-2 text-xs font-mono text-white/50">
                        {lot.area_sqm > 1000 ? `${(lot.area_sqm / 1000).toFixed(1)}k` : Math.round(lot.area_sqm)} m²
                      </td>
                      <td className="px-3 py-2 text-xs font-mono text-white/50">{lot.estimated_capacity}</td>
                      <td className="px-3 py-2 text-xs font-mono text-white/50">{lot.vehicles_detected}</td>
                      <td className={`px-3 py-2 text-xs font-mono font-medium ${
                        lot.occupancy_rate > 0.85 ? 'text-red-400' :
                        lot.occupancy_rate > 0.6 ? 'text-amber-400' :
                        'text-green-400'
                      }`}>
                        {Math.round(lot.occupancy_rate * 100)}%
                      </td>
                      <td className="px-3 py-2 text-[10px] font-mono text-white/30">
                        {lot.center_lat.toFixed(4)}, {lot.center_lng.toFixed(4)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {parking.timestamp && (
              <div className="mt-3 text-[9px] font-mono text-white/15 text-right">
                Last analyzed: {new Date(parking.timestamp).toLocaleString()}
              </div>
            )}
          </div>
        </>
      )}

      {/* Detection Summary — stats + distribution merged */}
      <div className="border border-white/[0.06] bg-white/[0.02] p-5">
        <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30 mb-1">
          Highway Camera Detections
        </h3>
        <p className="text-[9px] font-mono text-white/15 mb-4">IDOT expressway cameras near {neighborhood || "selected area"}</p>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-4">
          <div className="bg-white/[0.02] border border-white/[0.04] p-3">
            <div className="text-2xl font-bold font-mono text-white">{cameras.length}</div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-white/30 mt-1">Cameras</div>
          </div>
          <div className="bg-white/[0.02] border border-white/[0.04] p-3">
            <div className="text-2xl font-bold font-mono text-green-400">{totalPeds}</div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-white/30 mt-1">Pedestrians</div>
          </div>
          <div className="bg-white/[0.02] border border-white/[0.04] p-3">
            <div className="text-2xl font-bold font-mono text-blue-400">{totalVehs}</div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-white/30 mt-1">Vehicles</div>
          </div>
          <div className="bg-white/[0.02] border border-white/[0.04] p-3">
            <div className="text-2xl font-bold font-mono text-amber-400">{totalBikes}</div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-white/30 mt-1">Bicycles</div>
          </div>
          <div className="bg-white/[0.02] border border-white/[0.04] p-3">
            <div className="text-2xl font-bold font-mono text-white/70">{avgDensity}</div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-white/30 mt-1">Avg Traffic Density</div>
          </div>
        </div>
        {totalDetections > 0 && (
          <>
            <div className="text-[9px] font-mono uppercase tracking-wider text-white/20 mb-2">Detection Distribution</div>
            <div className="flex h-3 rounded-sm overflow-hidden">
              <div className="bg-green-500/70" style={{ width: `${pedPct}%` }} />
              <div className="bg-blue-500/70" style={{ width: `${vehPct}%` }} />
              <div className="bg-amber-500/70" style={{ width: `${bikePct}%` }} />
            </div>
            <div className="flex justify-between mt-2">
              <span className="text-[10px] font-mono text-green-400/60">Pedestrians {pedPct}%</span>
              <span className="text-[10px] font-mono text-blue-400/60">Vehicles {vehPct}%</span>
              <span className="text-[10px] font-mono text-amber-400/60">Bicycles {bikePct}%</span>
            </div>
          </>
        )}
      </div>

      {/* Highway Traffic 24h Chart */}
      <FootTrafficChart neighborhood={neighborhood} />

      {/* Section C: CCTV — Camera Grid (mini HUD cards, Drawer on click) */}
      {cameras.length > 0 ? (
        <div className="border border-white/[0.06] bg-white/[0.02]">
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              <span className="text-[10px] font-mono uppercase tracking-wider text-white/40">
                CCTV — Live Camera Feeds
              </span>
            </div>
            <span className="text-[10px] font-mono text-white/20">
              {cameras.length} camera{cameras.length !== 1 ? 's' : ''} — click to open
            </span>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-white/[0.04]">
            {cameras.map((cam) => (
              <CCTVCameraCard
                key={cam.camera_id}
                cam={cam}
                cctvDensity={cctv?.density ?? 'n/a'}
                onClick={() => setExpandedCam(expandedCam === cam.camera_id ? null : cam.camera_id)}
                isSelected={expandedCam === cam.camera_id}
              />
            ))}
          </div>
          <CCTVCameraDrawer
            open={!!selectedCamera}
            onClose={() => setExpandedCam(null)}
            camera={selectedCamera ?? null}
            cctv={cctv}
          />
        </div>
      ) : (
        <div className="border border-white/[0.06] bg-white/[0.02] p-8 text-center">
          <div className="text-xs font-mono text-white/20">No camera data available for this neighborhood</div>
          <div className="text-[10px] font-mono text-white/10 mt-1">CCTV pipeline runs on-demand — camera feeds will appear after analysis</div>
        </div>
      )}

    </div>
  )
}

function VaultTab({
  onOpenGraph,
  dataPoints = 0,
  neighborhood,
  neighborhoodData,
}: {
  onOpenGraph: () => void
  dataPoints?: number
  neighborhood?: string
  neighborhoodData?: NeighborhoodData | null
}) {
  // Rough estimate: 2 min per doc manually vs seconds with AI
  const hoursReclaimed = dataPoints ? Math.round((dataPoints * 2) / 60 * 10) / 10 : 0

  return (
    <div className="space-y-6">
      {/* 1. Analytics Charts */}
      {neighborhoodData && (
        <div className="space-y-4">
          <InspectionOutcomesChart inspections={neighborhoodData.inspections ?? []} />
          <TopViolationsPareto inspections={neighborhoodData.inspections ?? []} />
          <AlertHoursStackedArea data={neighborhoodData} />
        </div>
      )}

      {/* 2. Neural Graph Visualization */}
      <div className="border border-white/[0.06] bg-white/[0.02] p-5">
        <h3 className="text-sm font-semibold mb-3">
          <ShinyText text='The "Neural" Graph Visualization' speed={2} color="#b5b5b5" shineColor="#ffffff" spread={120} direction="left" />
        </h3>
        <p className="text-xs text-white/60 leading-relaxed mb-3">
          The standout feature is the Knowledge Graph, which visually proves that content is connected.
        </p>
        {neighborhood && (
          <div className="mb-4 border border-white/[0.06] rounded overflow-hidden">
            <CityGraph activeNeighborhood={neighborhood} interactive />
          </div>
        )}
        <ul className="text-xs text-white/50 space-y-2 list-disc list-inside mb-3">
          <li><strong className="text-white/70">Nodes:</strong> Neighborhoods, regulations, entities</li>
          <li><strong className="text-white/70">Edges:</strong> Connect nodes that share similar themes</li>
          <li><strong className="text-white/70">Interactive:</strong> Drag nodes, filter by type</li>
        </ul>
        <button
          onClick={onOpenGraph}
          className="px-4 py-2 text-xs font-medium border border-white/20 text-white/70 hover:text-white hover:border-white/40 transition-colors cursor-pointer"
        >
          Open Full Knowledge Graph
        </button>
      </div>

      {/* Visualizing the &quot;Attention Crisis&quot; */}
      <div className="border border-white/[0.06] bg-white/[0.02] p-5">
        <h3 className="text-sm font-semibold mb-3">
          <ShinyText text='Visualizing the "Attention Crisis"' speed={2} color="#b5b5b5" shineColor="#ffffff" spread={120} direction="left" />
        </h3>
        <div className="space-y-4">
          <div className="flex items-center gap-4 p-4 border border-white/[0.06]">
            <div className="text-2xl font-bold font-mono text-white">{hoursReclaimed > 0 ? `${hoursReclaimed}h` : '—'}</div>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-1">Time Reclaimed</div>
              <p className="text-xs text-white/50">
                {dataPoints ? `Hours saved vs. manually reviewing ${dataPoints} data points.` : 'Hours saved by AI vs. manual review.'}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function RegulatorySubTabs({ neighborhoodData }: { neighborhoodData: NeighborhoodData }) {
  const [subTab, setSubTab] = useState<'inspections' | 'permits' | 'licenses'>('inspections')

  const subTabs = [
    { key: 'inspections' as const, label: 'Inspections', count: neighborhoodData.inspection_stats.total },
    { key: 'permits' as const, label: 'Permits', count: neighborhoodData.permit_count },
    { key: 'licenses' as const, label: 'Licenses', count: neighborhoodData.license_count },
  ]

  return (
    <div className="space-y-4">
      <div className="flex gap-0 border-b border-white/[0.06]">
        {subTabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => setSubTab(tab.key)}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-px cursor-pointer ${
              subTab === tab.key
                ? 'border-white text-white'
                : 'border-transparent text-white/30 hover:text-white/60'
            }`}
          >
            {tab.label}
            {tab.count > 0 && (
              <span className="font-mono text-[10px] text-white/20">{tab.count}</span>
            )}
          </button>
        ))}
      </div>
      {subTab === 'inspections' && <InspectionTable inspections={neighborhoodData.inspections} />}
      {subTab === 'permits' && <PermitTable permits={neighborhoodData.permits} />}
      {subTab === 'licenses' && <LicenseTable licenses={neighborhoodData.licenses} />}
    </div>
  )
}
