import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import type { UserProfile, NeighborhoodData, DataSources, RiskScore, CCTVData, ParkingData } from '../types/index.ts'
import { api, API_BASE, BACKEND_API_BASE, fetchTrends, type TrendData } from '../api.ts'
import MapView from './MapView.tsx'
import Timer from './Timer.tsx'
import InspectionTable from './InspectionTable.tsx'
import PermitTable from './PermitTable.tsx'
import LicenseTable from './LicenseTable.tsx'
import NewsFeed from './NewsFeed.tsx'
import CommunityFeed from './CommunityFeed.tsx'
import MarketPanel from './MarketPanel.tsx'
import DemographicsCard from './DemographicsCard.tsx'
import PipelineMonitor from './PipelineMonitor.tsx'
// import MLMonitor from './MLMonitor.tsx' // temporarily hidden — re-enable with Models tab
import CCTVCameraCard from './CCTVCameraCard.tsx'
import CCTVCameraDrawer from './CCTVCameraDrawer.tsx'
import CommandPanel from './CommandPanel.tsx'
import CityGraph from './CityGraph.tsx'
import LocationReportPanel from './LocationReportPanel.tsx'
import FootTrafficChart from './FootTrafficChart.tsx'
import StreetscapeCard from './StreetscapeCard.tsx'
// import RecursiveAgentPanel from './RecursiveAgentPanel.tsx' // temporarily hidden — re-enable with Models tab
import Drawer from './Drawer.tsx'
import ProfilePage from './ProfilePage.tsx'
import LoadingFlow from './LoadingFlow.tsx'
import { InspectionOutcomesChart, TopViolationsPareto, AlertHoursStackedArea } from './VaultCharts.tsx'
import { dedupeNews, dedupePolicy } from '../feedDedup.ts'

type Tab = 'overview' | 'regulatory' | 'intel' | 'community' | 'market' | 'vision' | 'evidence'

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
  onProfileUpdate?: () => void
  initialProfileDrawerOpen?: boolean
}

export default function Dashboard({ profile, onReset, onProfileUpdate, initialProfileDrawerOpen = false }: Props) {
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
  const [sourcesWarning, setSourcesWarning] = useState<string | null>(null)
  const [sourcesMetadataReady, setSourcesMetadataReady] = useState(false)
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
  const sourcesRetryTimeoutRef = useRef<number | null>(null)

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

  const refreshData = async () => {
    const toErrorMessage = (value: unknown) =>
      value instanceof Error ? value.message : String(value)

    if (sourcesRetryTimeoutRef.current !== null) {
      window.clearTimeout(sourcesRetryTimeoutRef.current)
      sourcesRetryTimeoutRef.current = null
    }

    setSourcesWarning(null)
    setSourcesMetadataReady(false)

    const loadSources = async () => {
      try {
        const snapshot = await api.sources()
        if (!snapshot.metadata_ready) {
          setSources(null)
          setSourcesMetadataReady(false)
          setSourcesWarning('Warming source metadata...')
          sourcesRetryTimeoutRef.current = window.setTimeout(() => {
            sourcesRetryTimeoutRef.current = null
            void loadSources()
          }, 5000)
          return
        }

        setSources(snapshot.sources)
        setSourcesMetadataReady(true)
        setSourcesWarning(null)
      } catch (err) {
        setSourcesMetadataReady(false)
        setSourcesWarning(`Source metadata unavailable: ${toErrorMessage(err)}`)
      }
    }

    try {
      const neighborhood = await api.neighborhood(profile.neighborhood, profile.business_type)
      setNeighborhoodData(neighborhood)
      setRiskScore(computeRiskScore(neighborhood, profile))
      setError(null)
      setLoading(false)

      fetchTrends(profile.neighborhood).then(t => setTrends(t)).catch(() => {})
    } catch (err) {
      setNeighborhoodData(null)
      setRiskScore(null)
      setTrends(null)
      setError(`Neighborhood data: ${toErrorMessage(err)}`)
      setLoading(false)
      return
    }

    void loadSources()
  }

  useEffect(() => {
    let cancelled = false
    refreshData().then(() => { if (cancelled) return })
    return () => {
      cancelled = true
      if (sourcesRetryTimeoutRef.current !== null) {
        window.clearTimeout(sourcesRetryTimeoutRef.current)
        sourcesRetryTimeoutRef.current = null
      }
    }
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

  const regulatoryCount = (neighborhoodData?.inspection_stats.total || 0) + (neighborhoodData?.permit_count || 0) + (neighborhoodData?.license_count || 0)
  const intelCount = neighborhoodData
    ? dedupeNews(neighborhoodData.news).length + dedupePolicy(neighborhoodData.politics).length
    : 0
  // Keep in sync with buildEvidence() inside EvidenceExplorer — both counts must
  // cover the same set of sources so the tab badge matches the filter's "All" count.
  const evidenceCount =
    (neighborhoodData?.news.length || 0) +
    (neighborhoodData?.politics.length || 0) +
    (neighborhoodData?.reddit?.length || 0) +
    (neighborhoodData?.tiktok?.length || 0) +
    (neighborhoodData?.reviews?.length || 0) +
    (neighborhoodData?.realestate?.length || 0) +
    (neighborhoodData?.federal_register?.length || 0) +
    (neighborhoodData?.inspections?.length || 0) +
    (neighborhoodData?.permits?.length || 0)
  const allTabs: { key: Tab; label: string; count?: number; isEmpty?: () => boolean }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'regulatory', label: 'Regulatory', count: regulatoryCount, isEmpty: () => !regulatoryCount },
    { key: 'intel', label: 'News & Policy', count: intelCount, isEmpty: () => !intelCount },
    { key: 'community', label: 'Community', count: (neighborhoodData?.reddit?.length || 0) + (neighborhoodData?.tiktok?.length || 0), isEmpty: () => !((neighborhoodData?.reddit?.length || 0) + (neighborhoodData?.tiktok?.length || 0)) },
    { key: 'market', label: 'Market', count: (neighborhoodData?.reviews?.length || 0) + (neighborhoodData?.realestate?.length || 0), isEmpty: () => !((neighborhoodData?.reviews?.length || 0) + (neighborhoodData?.realestate?.length || 0)) },
    { key: 'vision', label: 'Vision', count: neighborhoodData?.cctv?.cameras.length || 0, isEmpty: () => false },
    { key: 'evidence', label: 'Evidence', count: evidenceCount, isEmpty: () => !evidenceCount },
  ]
  const tabs = allTabs.filter(t => !t.isEmpty || !(t.isEmpty?.() ?? false))
  const visibleTabKeys = useMemo(() => tabs.map(t => t.key), [tabs])

  useEffect(() => {
    if (!visibleTabKeys.includes(activeTab)) {
      setActiveTab(visibleTabKeys.includes('overview') ? 'overview' : (visibleTabKeys[0] ?? 'overview'))
    }
  }, [visibleTabKeys, activeTab])

  return (
    <div className="h-screen flex flex-col bg-[#06080d]">
      {/* Top bar */}
      <header className="flex items-stretch justify-between bg-white/[0.02] backdrop-blur-md border-b border-white/[0.06]">
        {/* Identity + Context */}
        <div className="flex items-stretch">
          <button
            type="button"
            onClick={onReset}
            className="flex items-center gap-2 px-5 border-r border-white/[0.06] hover:bg-white/[0.03] transition-colors cursor-pointer group"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-[#2B95D6] group-hover:shadow-[0_0_8px_rgba(43,149,214,0.8)] transition-shadow" />
            <span className="text-sm font-semibold uppercase tracking-[0.18em] text-white/80 group-hover:text-white transition-colors">
              Aleithia
            </span>
          </button>
          <div className="flex items-center gap-3 px-5 border-r border-white/[0.06]">
            <span className="text-[9px] font-mono uppercase tracking-wider text-white/25">Target</span>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-white/70">{profile.business_type}</span>
              <span className="text-white/15">›</span>
              <span className="text-xs font-mono text-white/45">{profile.neighborhood}</span>
            </div>
          </div>
        </div>

        {/* Session status + Actions */}
        <div className="flex items-stretch">
          <div className="flex items-center gap-3 px-5 border-l border-white/[0.06]">
            <span className="text-[9px] font-mono uppercase tracking-wider text-white/25">Session</span>
            <Timer running={loading} />
            <span className={`flex items-center gap-1.5 text-[10px] font-mono ${loading ? 'text-blue-400/70' : 'text-emerald-400/70'}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${loading ? 'bg-blue-400 animate-pulse' : 'bg-emerald-400'}`} />
              {loading ? 'ANALYZING' : 'READY'}
            </span>
          </div>
          <div className="flex items-stretch">
            <button
              onClick={refreshData}
              className="px-4 border-l border-white/[0.06] text-[10px] font-mono uppercase tracking-wider text-white/35 hover:text-white hover:bg-white/[0.03] transition-colors cursor-pointer"
            >
              Refresh
            </button>
            <button
              onClick={() => setProfileDrawerOpen(true)}
              className="px-4 border-l border-white/[0.06] text-[10px] font-mono uppercase tracking-wider text-white/35 hover:text-white hover:bg-white/[0.03] transition-colors cursor-pointer"
            >
              Profile
            </button>
            <button
              onClick={() => navigate('/start')}
              className="px-4 border-l border-white/[0.06] text-[10px] font-mono uppercase tracking-wider text-white/35 hover:text-white hover:bg-white/[0.03] transition-colors cursor-pointer"
            >
              New Search
            </button>
          </div>
        </div>
      </header>

      {error && (
        <div className="mx-6 mt-4 p-4 bg-red-500/[0.06] border border-red-500/20 text-red-400/80 text-xs font-mono space-y-2">
          <p>{error}</p>
          <p className="text-white/50">
            Modal API: {API_BASE} · Backend API: {BACKEND_API_BASE} — Restart dev server after changing <code className="bg-white/10 px-1">frontend/.env</code>. Deploy: <code className="bg-white/10 px-1">modal deploy modal_app/__init__.py</code>
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
          {/* Pipeline Monitor - compact status strip */}
          <PipelineMonitor
            sourcesReady={sourcesMetadataReady}
            sourcesWarning={sourcesWarning}
            activeSources={sourceList.filter(s => s.active).length}
            totalSources={sourceList.length}
          />

          {/* Tabs — segmented workspace navigation */}
          <div className="flex gap-0 border-b border-white/[0.06] items-stretch">
            {tabs.map(tab => {
              const isActive = activeTab === tab.key
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`flex items-center gap-2 px-5 py-2.5 text-xs font-medium transition-all border-b-2 -mb-px cursor-pointer relative ${
                    isActive
                      ? 'border-[#2B95D6] text-white bg-[#2B95D6]/[0.05]'
                      : 'border-transparent text-white/35 hover:text-white/70 hover:bg-white/[0.02]'
                  }`}
                >
                  {isActive && (
                    <span className="absolute left-0 top-0 bottom-0 w-px bg-[#2B95D6]/30" />
                  )}
                  <span className="uppercase tracking-wider text-[11px]">{tab.label}</span>
                  {tab.count !== undefined && tab.count > 0 && (
                    <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${
                      isActive ? 'bg-[#2B95D6]/20 text-[#2B95D6]' : 'text-white/25 bg-white/[0.04]'
                    }`}>
                      {tab.count}
                    </span>
                  )}
                </button>
              )
            })}
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
                  {/* Map hero (left) + Unified Command Panel (right) */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className="h-[620px] min-h-0">
                      <MapView activeNeighborhood={profile.neighborhood} />
                    </div>

                    <div className="h-[620px] min-h-0">
                      {riskScore && neighborhoodData ? (
                        <CommandPanel
                          data={neighborhoodData}
                          profile={profile}
                          riskScore={riskScore}
                          onTabChange={(tab) => setActiveTab(tab as Tab)}
                        />
                      ) : (
                        <div className="h-full flex items-center justify-center border border-white/[0.06] bg-white/[0.01]">
                          <span className="text-[10px] font-mono text-white/20">Loading command panel</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Full-width demographics strip */}
                  {neighborhoodData?.metrics && (
                    <DemographicsCard metrics={neighborhoodData.metrics} demographics={neighborhoodData.demographics} horizontal />
                  )}

                  {/* Evidence preview row (Phase 2e) */}
                  {neighborhoodData && (
                    <OverviewPreviewRow
                      data={neighborhoodData}
                      onTabChange={(tab) => setActiveTab(tab as Tab)}
                    />
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

              {activeTab === 'evidence' && neighborhoodData && (
                <EvidenceExplorer data={neighborhoodData} />
              )}

              {/* Models and Vault tabs temporarily hidden from dashboard navigation.
                 Components preserved — re-add 'models'|'vault' to Tab type and allTabs to restore.

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
              */}
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
      {/* Vision header strip */}
      <div className="border border-white/[0.06] bg-gradient-to-r from-white/[0.02] to-emerald-500/[0.02] px-4 py-2 flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-emerald-300/80">Vision Command</span>
        </div>
        <div className="h-3 w-px bg-white/10" />
        <span className="text-[10px] font-mono text-white/40 uppercase tracking-wider">{neighborhood || 'Selected area'}</span>
        <div className="flex-1" />
        <div className="flex items-center gap-3 text-[10px] font-mono text-white/30">
          <span><span className="text-white/60">{cameras.length}</span> cameras</span>
          <span className="text-white/10">·</span>
          <span><span className="text-white/60">{parking?.parking_lots.length || 0}</span> lots</span>
          <span className="text-white/10">·</span>
          <span className={`uppercase ${avgDensity === 'high' ? 'text-red-400/80' : avgDensity === 'medium' ? 'text-amber-400/80' : 'text-emerald-400/80'}`}>
            {avgDensity} density
          </span>
        </div>
      </div>

      {/* Streetscape Intelligence (elevated) */}
      <StreetscapeCard neighborhood={neighborhood} />

      {/* Satellite Parking + Highway Detection - two-column module */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Parking occupancy */}
        {parking && parking.parking_lots.length > 0 ? (
          <div className="border border-white/[0.06] bg-white/[0.02]">
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/[0.06]">
              <span className="w-1 h-1 rounded-full bg-cyan-400/70" />
              <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-cyan-300/80">Parking Occupancy</span>
              <span className="text-[9px] font-mono ml-auto text-white/25 px-1.5 py-0.5 border border-white/10">
                SegFormer + YOLOv8m
              </span>
            </div>

            {/* Annotated satellite image */}
            <div className="relative aspect-video bg-black/40 overflow-hidden border-b border-white/[0.04]">
              <img
                src={api.parkingAnnotatedUrl(neighborhood)}
                alt={`Parking analysis — ${neighborhood}`}
                className="w-full h-full object-contain"
                onError={e => { e.currentTarget.style.display = 'none' }}
              />
              {/* HUD overlay */}
              <div className="absolute top-2 left-2 text-[9px] font-mono text-emerald-400/80 bg-black/60 px-1.5 py-0.5 border border-emerald-500/20">
                LIVE ● SAT
              </div>
              <div className="absolute top-2 right-2 text-[9px] font-mono text-white/50 bg-black/60 px-1.5 py-0.5 border border-white/10">
                {parking.timestamp && new Date(parking.timestamp).toLocaleDateString()}
              </div>
            </div>

            {/* Stat grid */}
            <div className="grid grid-cols-4 divide-x divide-white/[0.04]">
              <div className="px-3 py-2.5">
                <div className="text-lg font-bold font-mono text-white">{parking.parking_lots.length}</div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mt-0.5">Lots</div>
              </div>
              <div className="px-3 py-2.5">
                <div className="text-lg font-bold font-mono text-blue-400/80">{parking.total_capacity}</div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mt-0.5">Capacity</div>
              </div>
              <div className="px-3 py-2.5">
                <div className="text-lg font-bold font-mono text-emerald-400/80">{parking.total_vehicles}</div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mt-0.5">Vehicles</div>
              </div>
              <div className="px-3 py-2.5">
                <div className={`text-lg font-bold font-mono ${parking.overall_occupancy > 0.85 ? 'text-red-400' : parking.overall_occupancy > 0.6 ? 'text-amber-400' : 'text-emerald-400'}`}>
                  {Math.round(parking.overall_occupancy * 100)}%
                </div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mt-0.5">Occupancy</div>
              </div>
            </div>

            {/* Per-lot breakdown */}
            <div className="max-h-48 overflow-y-auto border-t border-white/[0.04]">
              <table className="w-full text-left">
                <thead className="sticky top-0 bg-white/[0.03] backdrop-blur">
                  <tr className="border-b border-white/[0.04]">
                    <th className="px-2.5 py-1.5 text-[9px] font-mono uppercase tracking-wider text-white/25 font-medium">Lot</th>
                    <th className="px-2.5 py-1.5 text-[9px] font-mono uppercase tracking-wider text-white/25 font-medium">Size</th>
                    <th className="px-2.5 py-1.5 text-[9px] font-mono uppercase tracking-wider text-white/25 font-medium">Vehicles</th>
                    <th className="px-2.5 py-1.5 text-[9px] font-mono uppercase tracking-wider text-white/25 font-medium">Occupancy</th>
                  </tr>
                </thead>
                <tbody>
                  {parking.parking_lots.map((lot, i) => (
                    <tr key={i} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                      <td className="px-2.5 py-1.5 text-[10px] font-mono text-white/45">#{i + 1}</td>
                      <td className="px-2.5 py-1.5 text-[10px] font-mono text-white/55">
                        {lot.area_sqm > 1000 ? `${(lot.area_sqm / 1000).toFixed(1)}k` : Math.round(lot.area_sqm)} m²
                      </td>
                      <td className="px-2.5 py-1.5 text-[10px] font-mono text-white/55">{lot.vehicles_detected} / {lot.estimated_capacity}</td>
                      <td className={`px-2.5 py-1.5 text-[10px] font-mono font-semibold ${
                        lot.occupancy_rate > 0.85 ? 'text-red-400' :
                        lot.occupancy_rate > 0.6 ? 'text-amber-400' :
                        'text-emerald-400'
                      }`}>
                        <div className="flex items-center gap-1.5">
                          <span>{Math.round(lot.occupancy_rate * 100)}%</span>
                          <div className="w-10 h-0.5 bg-white/[0.05]">
                            <div className={`h-0.5 ${lot.occupancy_rate > 0.85 ? 'bg-red-400/70' : lot.occupancy_rate > 0.6 ? 'bg-amber-400/70' : 'bg-emerald-400/70'}`} style={{ width: `${lot.occupancy_rate * 100}%` }} />
                          </div>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="border border-white/[0.06] bg-white/[0.01] p-6 flex flex-col justify-center text-center">
            <div className="text-[10px] font-mono uppercase tracking-wider text-white/25">Parking Occupancy</div>
            <div className="text-[10px] font-mono text-white/15 mt-2">Satellite analysis not yet run for this area.</div>
          </div>
        )}

        {/* Highway Camera Detection Summary */}
        <div className="border border-white/[0.06] bg-white/[0.02]">
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/[0.06]">
            <span className="w-1 h-1 rounded-full bg-blue-400/70" />
            <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-blue-300/80">Highway Detections</span>
            <span className="text-[9px] font-mono ml-auto text-white/25">IDOT · YOLOv8</span>
          </div>

          {/* Stat grid */}
          <div className="grid grid-cols-4 divide-x divide-white/[0.04]">
            <div className="px-3 py-2.5">
              <div className="text-lg font-bold font-mono text-white">{cameras.length}</div>
              <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mt-0.5">Cameras</div>
            </div>
            <div className="px-3 py-2.5">
              <div className="text-lg font-bold font-mono text-emerald-400/80">{totalPeds}</div>
              <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mt-0.5">Peds</div>
            </div>
            <div className="px-3 py-2.5">
              <div className="text-lg font-bold font-mono text-blue-400/80">{totalVehs}</div>
              <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mt-0.5">Vehicles</div>
            </div>
            <div className="px-3 py-2.5">
              <div className="text-lg font-bold font-mono text-amber-400/80">{totalBikes}</div>
              <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mt-0.5">Bikes</div>
            </div>
          </div>

          {/* Detection distribution */}
          {totalDetections > 0 && (
            <div className="px-4 py-3 border-t border-white/[0.04]">
              <div className="text-[9px] font-mono uppercase tracking-wider text-white/25 mb-2">Detection Distribution</div>
              <div className="flex h-2 overflow-hidden">
                <div className="bg-emerald-500/70" style={{ width: `${pedPct}%` }} />
                <div className="bg-blue-500/70" style={{ width: `${vehPct}%` }} />
                <div className="bg-amber-500/70" style={{ width: `${bikePct}%` }} />
              </div>
              <div className="flex justify-between mt-2 text-[10px] font-mono">
                <span className="text-emerald-400/60">Peds {pedPct}%</span>
                <span className="text-blue-400/60">Vehicles {vehPct}%</span>
                <span className="text-amber-400/60">Bikes {bikePct}%</span>
              </div>
            </div>
          )}

          {/* Traffic chart */}
          <div className="border-t border-white/[0.04]">
            <FootTrafficChart neighborhood={neighborhood} embedded />
          </div>
        </div>
      </div>

      {/* CCTV Camera Wall */}
      {cameras.length > 0 ? (
        <div className="border border-white/[0.06] bg-white/[0.02]">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-emerald-300/80">
                CCTV Grid — Live Feeds
              </span>
            </div>
            <div className="flex items-center gap-3 text-[10px] font-mono text-white/30">
              <span>{cameras.length} cameras</span>
              {selectedCamera && (
                <span className="text-emerald-400/80">● CAM {selectedCamera.camera_id.slice(-4)} selected</span>
              )}
            </div>
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
        <div className="border border-white/[0.06] bg-white/[0.01] p-8 text-center">
          <div className="text-xs font-mono text-white/25 uppercase tracking-wider">No camera data</div>
          <div className="text-[10px] font-mono text-white/15 mt-1">CCTV pipeline runs on-demand — camera feeds will appear after analysis</div>
        </div>
      )}

    </div>
  )
}

// Exported to avoid noUnusedLocals — temporarily hidden from dashboard tabs
export function VaultTab({
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
The &ldquo;Neural&rdquo; Graph Visualization
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
Visualizing the &ldquo;Attention Crisis&rdquo;
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

  const stats = neighborhoodData.inspection_stats
  const passRate = stats.total > 0 ? Math.round((stats.passed / stats.total) * 100) : 0

  const subTabs = [
    { key: 'inspections' as const, label: 'Inspections', count: stats.total, state: stats.total > 0 ? `${passRate}% pass` : '—' },
    { key: 'permits' as const, label: 'Permits', count: neighborhoodData.permit_count, state: neighborhoodData.permit_count > 0 ? 'active' : '—' },
    { key: 'licenses' as const, label: 'Licenses', count: neighborhoodData.license_count, state: neighborhoodData.license_count > 0 ? 'active' : '—' },
  ]

  return (
    <div className="space-y-4">
      {/* Regulatory evidence header */}
      <div className="border border-white/[0.06] bg-white/[0.01]">
        {/* Summary header */}
        <div className="flex items-center gap-4 px-4 py-2.5 border-b border-white/[0.04]">
          <div className="flex items-center gap-2">
            <span className="w-1 h-1 rounded-full bg-violet-400/70" />
            <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-white/35">Regulatory Evidence Workspace</span>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-4 text-[10px] font-mono text-white/40">
            <span><span className="text-emerald-400/80">{stats.passed}</span> passed</span>
            <span><span className="text-red-400/80">{stats.failed}</span> failed</span>
            <span><span className="text-white/60">{neighborhoodData.permit_count}</span> permits</span>
            <span><span className="text-white/60">{neighborhoodData.license_count}</span> licenses</span>
          </div>
        </div>
        {/* Segmented control */}
        <div className="flex gap-0 divide-x divide-white/[0.04]">
          {subTabs.map(tab => {
            const isActive = subTab === tab.key
            return (
              <button
                key={tab.key}
                onClick={() => setSubTab(tab.key)}
                className={`flex-1 flex items-center justify-between px-4 py-3 transition-all cursor-pointer border-b-2 ${
                  isActive
                    ? 'border-violet-400 bg-violet-500/[0.04]'
                    : 'border-transparent hover:bg-white/[0.02]'
                }`}
              >
                <div className="flex flex-col items-start gap-0.5">
                  <span className={`text-[11px] font-semibold uppercase tracking-wider ${isActive ? 'text-white' : 'text-white/45'}`}>
                    {tab.label}
                  </span>
                  <span className={`text-[9px] font-mono ${isActive ? 'text-violet-300/80' : 'text-white/25'}`}>
                    {tab.state}
                  </span>
                </div>
                <span className={`text-2xl font-mono font-bold ${isActive ? 'text-white' : 'text-white/30'}`}>
                  {tab.count}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {subTab === 'inspections' && <InspectionTable inspections={neighborhoodData.inspections} />}
      {subTab === 'permits' && <PermitTable permits={neighborhoodData.permits} />}
      {subTab === 'licenses' && <LicenseTable licenses={neighborhoodData.licenses} />}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────
// Overview preview row: compact peek into news / community / market
// with drill-down to the full tab.
// ────────────────────────────────────────────────────────────────────

interface PreviewRowProps {
  data: NeighborhoodData
  onTabChange: (tab: string) => void
}

function OverviewPreviewRow({ data, onTabChange }: PreviewRowProps) {
  const newsItems = [
    ...(data.news || []).map((item) => ({
      title: item.title,
      meta: item.source || 'news',
    })),
    ...(data.politics || []).map((item) => ({
      title: item.title,
      meta: (item.metadata?.matter_type as string) || 'policy',
    })),
    ...(data.federal_register || []).map((item) => ({
      title: item.title,
      meta: (item.metadata?.agency as string) || 'federal',
    })),
  ].slice(0, 3)
  const communityItems = [...(data.reddit || []), ...(data.tiktok || [])].slice(0, 3)
  const marketItems = [
    ...(data.reviews || []).map((review) => ({
      title: review.title,
      meta: review.metadata?.rating ? `${review.metadata.rating}/5 · ${review.metadata.review_count || 0} reviews` : 'review',
    })),
    ...(data.realestate || []).map((listing) => ({
      title: listing.title,
      meta: [
        listing.metadata?.listing_type as string | undefined,
        listing.metadata?.price as string | undefined,
      ].filter(Boolean).join(' · ') || 'listing',
    })),
  ].slice(0, 3)
  const hasAny = newsItems.length > 0 || communityItems.length > 0 || marketItems.length > 0
  if (!hasAny) return null

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <PreviewPanel
        title="Local Intelligence"
        accent="text-blue-300/70"
        dot="bg-blue-400/70"
        count={(data.news?.length || 0) + (data.politics?.length || 0) + (data.federal_register?.length || 0)}
        onClick={() => onTabChange('intel')}
        items={newsItems}
        emptyMsg="No recent news signals"
      />
      <PreviewPanel
        title="Community Pulse"
        accent="text-green-300/70"
        dot="bg-green-400/70"
        count={(data.reddit?.length || 0) + (data.tiktok?.length || 0)}
        onClick={() => onTabChange('community')}
        items={communityItems.map(c => ({
          title: c.title,
          meta: (c.metadata?.subreddit as string) ? `r/${c.metadata?.subreddit}` : (c.metadata?.creator as string) ? `@${c.metadata?.creator}` : 'social',
        }))}
        emptyMsg="No community chatter"
      />
      <PreviewPanel
        title="Market Snapshot"
        accent="text-cyan-300/70"
        dot="bg-cyan-400/70"
        count={(data.reviews?.length || 0) + (data.realestate?.length || 0)}
        onClick={() => onTabChange('market')}
        items={marketItems}
        emptyMsg="No market data"
      />
    </div>
  )
}

interface PreviewPanelProps {
  title: string
  accent: string
  dot: string
  count: number
  onClick: () => void
  items: Array<{ title: string; meta: string }>
  emptyMsg: string
}

function PreviewPanel({ title, accent, dot, count, onClick, items, emptyMsg }: PreviewPanelProps) {
  return (
    <button
      onClick={onClick}
      className="text-left border border-white/[0.06] bg-white/[0.01] hover:border-white/[0.12] hover:bg-white/[0.02] transition-all cursor-pointer group"
    >
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/[0.04]">
        <div className="flex items-center gap-2">
          <span className={`w-1 h-1 rounded-full ${dot}`} />
          <span className={`text-[10px] font-mono uppercase tracking-wider ${accent}`}>{title}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-white/25">{count}</span>
          <span className="text-[10px] text-white/25 group-hover:text-white/60 transition-colors">›</span>
        </div>
      </div>
      <div className="p-3 space-y-2 min-h-[130px]">
        {items.length > 0 ? items.map((item, i) => (
          <div key={i} className="text-[11px] leading-snug">
            <div className="text-white/75 line-clamp-2 group-hover:text-white/90 transition-colors">{item.title}</div>
            <div className="text-[9px] font-mono uppercase tracking-wider text-white/25 mt-0.5">{item.meta}</div>
          </div>
        )) : (
          <div className="text-[10px] font-mono text-white/20 flex items-center justify-center h-full">{emptyMsg}</div>
        )}
      </div>
    </button>
  )
}

// ────────────────────────────────────────────────────────────────────
// Evidence Explorer — cross-source investigation workspace.
// Operates on already-fetched NeighborhoodData; no new backend reads.
// ────────────────────────────────────────────────────────────────────

type EvidenceFamily = 'all' | 'regulatory' | 'news' | 'policy' | 'community' | 'market'
type EvidenceSort = 'recent' | 'importance'

interface EvidenceEntry {
  id: string
  title: string
  snippet: string
  family: Exclude<EvidenceFamily, 'all'>
  source: string
  sourceLabel: string
  timestamp: string
  url?: string
  badge?: string
  importance: number
}

function buildEvidence(data: NeighborhoodData): EvidenceEntry[] {
  const entries: EvidenceEntry[] = []

  for (const n of data.news || []) {
    entries.push({
      id: `news-${n.id}`,
      title: n.title,
      snippet: (n.content || '').slice(0, 180),
      family: 'news',
      source: n.source || 'news',
      sourceLabel: 'News',
      timestamp: n.timestamp,
      url: n.url,
      importance: 60,
    })
  }

  for (const p of data.politics || []) {
    entries.push({
      id: `politics-${p.id}`,
      title: p.title,
      snippet: (p.content || '').slice(0, 180),
      family: 'policy',
      source: 'city_council',
      sourceLabel: 'Policy',
      timestamp: p.timestamp,
      url: p.url,
      badge: (p.metadata?.matter_type as string) || undefined,
      importance: 70,
    })
  }

  for (const r of data.federal_register || []) {
    entries.push({
      id: `fed-${r.id}`,
      title: r.title,
      snippet: (r.content || '').slice(0, 180),
      family: 'policy',
      source: 'federal_register',
      sourceLabel: 'Federal',
      timestamp: r.timestamp,
      url: r.url,
      badge: (r.metadata?.agency as string) || undefined,
      importance: 75,
    })
  }

  for (const r of data.reddit || []) {
    entries.push({
      id: `reddit-${r.id}`,
      title: r.title,
      snippet: (r.content || '').slice(0, 180),
      family: 'community',
      source: 'reddit',
      sourceLabel: 'Reddit',
      timestamp: r.timestamp,
      url: r.url,
      badge: (r.metadata?.subreddit as string) ? `r/${r.metadata?.subreddit}` : undefined,
      importance: Math.min(60 + ((r.metadata?.score as number) || 0) / 50, 90),
    })
  }

  for (const t of data.tiktok || []) {
    entries.push({
      id: `tiktok-${t.id}`,
      title: t.title || 'TikTok video',
      snippet: (t.content || '').slice(0, 180),
      family: 'community',
      source: 'tiktok',
      sourceLabel: 'TikTok',
      timestamp: t.timestamp,
      url: t.url,
      badge: (t.metadata?.creator as string) ? `@${t.metadata?.creator}` : undefined,
      importance: 55,
    })
  }

  for (const rv of data.reviews || []) {
    entries.push({
      id: `review-${rv.id}`,
      title: rv.title,
      snippet: ((rv.metadata?.categories as string[]) || []).join(', '),
      family: 'market',
      source: 'reviews',
      sourceLabel: 'Reviews',
      timestamp: rv.timestamp,
      url: rv.url,
      badge: rv.metadata?.rating ? `${rv.metadata.rating}★` : undefined,
      importance: 55 + ((rv.metadata?.review_count as number) || 0) / 20,
    })
  }

  for (const re of data.realestate || []) {
    entries.push({
      id: `re-${re.id}`,
      title: re.title,
      snippet: `${(re.metadata?.property_type as string) || ''} · ${(re.metadata?.size_sqft as number) || ''} sqft`,
      family: 'market',
      source: 'realestate',
      sourceLabel: 'Listing',
      timestamp: re.timestamp,
      url: re.url,
      badge: (re.metadata?.listing_type as string) || undefined,
      importance: 50,
    })
  }

  for (const i of data.inspections || []) {
    const raw = i.metadata?.raw_record as Record<string, string> | undefined
    entries.push({
      id: `insp-${i.id}`,
      title: raw?.dba_name || i.title,
      snippet: `${raw?.inspection_type || 'Inspection'} — ${raw?.results || 'Unknown'}`,
      family: 'regulatory',
      source: 'inspections',
      sourceLabel: 'Inspection',
      timestamp: i.timestamp,
      url: i.url,
      badge: raw?.results,
      importance: raw?.results?.toLowerCase().includes('fail') ? 80 : 55,
    })
  }

  for (const p of data.permits || []) {
    const raw = p.metadata?.raw_record as Record<string, string> | undefined
    entries.push({
      id: `permit-${p.id}`,
      title: raw?.work_type || p.title,
      snippet: (raw?.work_description || '').slice(0, 180),
      family: 'regulatory',
      source: 'permits',
      sourceLabel: 'Permit',
      timestamp: p.timestamp,
      url: p.url,
      badge: raw?.permit_status,
      importance: 50,
    })
  }

  return entries
}

function EvidenceExplorer({ data }: { data: NeighborhoodData }) {
  const [family, setFamily] = useState<EvidenceFamily>('all')
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<EvidenceSort>('recent')

  const allEntries = useMemo(() => buildEvidence(data), [data])

  const familyCounts = useMemo(() => {
    const counts: Record<string, number> = { all: allEntries.length, regulatory: 0, news: 0, policy: 0, community: 0, market: 0 }
    for (const e of allEntries) counts[e.family]++
    return counts
  }, [allEntries])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return allEntries
      .filter(e => family === 'all' || e.family === family)
      .filter(e => !q || e.title.toLowerCase().includes(q) || e.snippet.toLowerCase().includes(q) || e.sourceLabel.toLowerCase().includes(q))
      .sort((a, b) => {
        if (sort === 'importance') return b.importance - a.importance
        return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      })
  }, [allEntries, family, query, sort])

  const families: { key: EvidenceFamily; label: string; accent: string }[] = [
    { key: 'all', label: 'All', accent: 'text-white' },
    { key: 'regulatory', label: 'Regulatory', accent: 'text-violet-300' },
    { key: 'news', label: 'News', accent: 'text-blue-300' },
    { key: 'policy', label: 'Policy', accent: 'text-purple-300' },
    { key: 'community', label: 'Community', accent: 'text-emerald-300' },
    { key: 'market', label: 'Market', accent: 'text-cyan-300' },
  ]

  return (
    <div className="space-y-3">
      {/* Controls */}
      <div className="border border-white/[0.06] bg-white/[0.01]">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-white/[0.04]">
          <svg className="w-3.5 h-3.5 text-white/25" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-4.35-4.35m0 0A7.5 7.5 0 103.5 10.5a7.5 7.5 0 0013.15 6.15z" />
          </svg>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search evidence across all sources..."
            className="flex-1 bg-transparent outline-none text-xs text-white/80 placeholder:text-white/20"
          />
          <div className="flex items-center gap-0 border-l border-white/[0.04] pl-2">
            <span className="text-[9px] font-mono uppercase tracking-wider text-white/25 mr-2">Sort</span>
            <button
              onClick={() => setSort('recent')}
              className={`px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider transition-colors cursor-pointer ${sort === 'recent' ? 'text-white bg-white/[0.06]' : 'text-white/30 hover:text-white/50'}`}
            >
              Recent
            </button>
            <button
              onClick={() => setSort('importance')}
              className={`px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider transition-colors cursor-pointer ${sort === 'importance' ? 'text-white bg-white/[0.06]' : 'text-white/30 hover:text-white/50'}`}
            >
              Importance
            </button>
          </div>
        </div>

        {/* Family filter chips */}
        <div className="flex flex-wrap gap-0 divide-x divide-white/[0.04]">
          {families.map(f => {
            const isActive = family === f.key
            return (
              <button
                key={f.key}
                onClick={() => setFamily(f.key)}
                className={`flex items-center gap-1.5 px-3 py-2 text-[10px] font-mono uppercase tracking-wider transition-colors cursor-pointer ${
                  isActive ? `${f.accent} bg-white/[0.04]` : 'text-white/30 hover:text-white/60 hover:bg-white/[0.02]'
                }`}
              >
                {f.label}
                <span className={`font-mono ${isActive ? 'text-white/50' : 'text-white/20'}`}>
                  {familyCounts[f.key] ?? 0}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Results */}
      {filtered.length === 0 ? (
        <div className="border border-white/[0.06] bg-white/[0.01] p-8 text-center">
          <div className="text-xs font-mono text-white/25">
            {query ? `No evidence matches "${query}"` : 'No evidence available for this filter'}
          </div>
          <div className="text-[10px] font-mono text-white/15 mt-1">Try a different source family or clear the search.</div>
        </div>
      ) : (
        <div className="space-y-1.5">
          {filtered.map(entry => (
            <EvidenceRow key={entry.id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  )
}

const FAMILY_STYLES: Record<Exclude<EvidenceFamily, 'all'>, { border: string; accent: string; dot: string }> = {
  regulatory: { border: 'border-l-violet-500/40', accent: 'text-violet-300/80', dot: 'bg-violet-400/70' },
  news: { border: 'border-l-blue-500/40', accent: 'text-blue-300/80', dot: 'bg-blue-400/70' },
  policy: { border: 'border-l-purple-500/40', accent: 'text-purple-300/80', dot: 'bg-purple-400/70' },
  community: { border: 'border-l-emerald-500/40', accent: 'text-emerald-300/80', dot: 'bg-emerald-400/70' },
  market: { border: 'border-l-cyan-500/40', accent: 'text-cyan-300/80', dot: 'bg-cyan-400/70' },
}

function EvidenceRow({ entry }: { entry: EvidenceEntry }) {
  const s = FAMILY_STYLES[entry.family]
  return (
    <div className={`border border-white/[0.06] border-l-2 ${s.border} bg-white/[0.01] hover:bg-white/[0.02] transition-colors`}>
      <div className="px-4 py-3 flex items-start gap-3">
        <div className={`w-1 h-1 rounded-full ${s.dot} mt-1.5 shrink-0`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-start gap-2 mb-1">
            <span className={`text-[9px] font-mono uppercase tracking-wider ${s.accent} shrink-0`}>
              {entry.sourceLabel}
            </span>
            {entry.badge && (
              <span className="text-[9px] font-mono uppercase tracking-wider text-white/40 border border-white/[0.08] px-1.5 py-[1px] shrink-0">
                {entry.badge}
              </span>
            )}
            <span className="text-[9px] font-mono text-white/20 ml-auto shrink-0">
              {new Date(entry.timestamp).toLocaleDateString()}
            </span>
          </div>
          <div className="text-xs text-white/80 leading-snug line-clamp-2">{entry.title}</div>
          {entry.snippet && (
            <div className="text-[11px] text-white/35 mt-1 leading-relaxed line-clamp-2">{entry.snippet}</div>
          )}
        </div>
        {entry.url && (
          <a
            href={entry.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] font-mono uppercase tracking-wider text-white/30 hover:text-white/70 transition-colors shrink-0 self-center"
          >
            Open ›
          </a>
        )}
      </div>
    </div>
  )
}
