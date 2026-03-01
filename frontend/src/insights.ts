import type {
  NeighborhoodData,
  UserProfile,
  RiskProfile,
  InsightsResult,
  CategoryScore,
  SubMetric,
  InsightSignal,
  StreetscapeData,
} from './types/index.ts'

const WEIGHTS: Record<RiskProfile, Record<string, number>> = {
  conservative: {
    regulatory: 0.25, economic: 0.10, market: 0.15,
    demographic: 0.15, safety: 0.25, community: 0.10,
  },
  growth: {
    regulatory: 0.10, economic: 0.25, market: 0.25,
    demographic: 0.10, safety: 0.10, community: 0.20,
  },
  budget: {
    regulatory: 0.15, economic: 0.15, market: 0.15,
    demographic: 0.25, safety: 0.10, community: 0.20,
  },
}

const LICENSE_MAP: Record<string, string[]> = {
  'Restaurant': ['retail food', 'restaurant', 'tavern', 'caterer'],
  'Coffee Shop': ['retail food', 'coffee'],
  'Bar': ['tavern', 'liquor', 'late night'],
  'Retail Store': ['retail', 'general retail'],
  'Salon': ['beauty', 'barber', 'nail'],
}

function signal(score: number): { signal: InsightSignal; signalLabel: string } {
  if (score >= 65) return { signal: 'positive', signalLabel: 'FAVORABLE' }
  if (score >= 40) return { signal: 'neutral', signalLabel: 'MODERATE' }
  return { signal: 'negative', signalLabel: 'CONCERNING' }
}

function avg(values: number[]): number {
  if (values.length === 0) return 0
  return values.reduce((a, b) => a + b, 0) / values.length
}

function clamp(v: number, lo = 0, hi = 100): number {
  return Math.max(lo, Math.min(hi, v))
}

// ── Category Scorers ───────────────────────────────────────────────

function scoreRegulatory(data: NeighborhoodData): CategoryScore | null {
  const stats = data.inspection_stats
  if (stats.total === 0 && data.inspections.length === 0) return null

  const subs: SubMetric[] = []
  let dataPoints = stats.total

  if (stats.total > 0) {
    const passRate = (stats.passed / stats.total) * 100
    subs.push({ name: 'Pass Rate', value: passRate, raw: `${stats.passed} of ${stats.total} passed (${Math.round(passRate)}%)` })
  }

  // Risk level from inspections
  const riskValues = data.inspections
    .map(i => i.metadata?.raw_record?.risk)
    .filter(Boolean)
    .map(r => {
      const s = (r as string).toLowerCase()
      if (s.includes('1') || s.includes('high')) return 0
      if (s.includes('2') || s.includes('medium')) return 50
      return 100
    })
  if (riskValues.length > 0) {
    const avgRisk = avg(riskValues)
    const highCount = riskValues.filter(v => v === 0).length
    subs.push({ name: 'Risk Level', value: avgRisk, raw: `${highCount} high-risk of ${riskValues.length} facilities` })
  }

  // Violation density
  const violationLengths = data.inspections
    .map(i => (i.metadata?.raw_record?.violations as string)?.length || 0)
    .filter(v => v > 0)
  if (violationLengths.length > 0) {
    const avgLen = avg(violationLengths)
    const score = clamp(100 - avgLen / 10)
    subs.push({ name: 'Violation Density', value: score, raw: `avg ${Math.round(avgLen)} chars across ${violationLengths.length} records` })
  }

  if (subs.length === 0) return null

  const score = Math.round(avg(subs.map(s => s.value)))
  const { signal: sig, signalLabel } = signal(score)
  const passRate = stats.total > 0 ? Math.round((stats.passed / stats.total) * 100) : 0
  const highRisk = riskValues.filter(v => v === 0).length

  return {
    id: 'regulatory', name: 'Regulatory', score, subMetrics: subs,
    claim: `${passRate}% pass rate across ${stats.total} inspections, ${highRisk} high-risk facilities — ${signalLabel} regulatory environment`,
    signal: sig, signalLabel, sources: ['food_inspections'], dataPoints,
  }
}

function scoreEconomic(data: NeighborhoodData): CategoryScore | null {
  const subs: SubMetric[] = []
  const permitCount = data.permit_count
  const licenseCount = data.license_count

  if (permitCount === 0 && licenseCount === 0) return null

  if (permitCount > 0) {
    const momentum = clamp((permitCount / 15) * 100)
    subs.push({ name: 'Permit Momentum', value: momentum, raw: `${permitCount} active permits` })
  }

  // Investment signal from fees
  const fees = data.permits
    .map(p => parseFloat(p.metadata?.raw_record?.building_fee_paid || '0'))
    .filter(f => f > 0)
  if (fees.length > 0) {
    const totalFees = fees.reduce((a, b) => a + b, 0)
    const investScore = clamp(totalFees / 1000)
    subs.push({ name: 'Investment Signal', value: investScore, raw: `$${Math.round(totalFees).toLocaleString()} in fees paid` })
  }

  // New construction ratio
  if (data.permits.length > 0) {
    const newBuilds = data.permits.filter(p => {
      const wt = (p.metadata?.raw_record?.work_type || '').toLowerCase()
      return wt.includes('new') || wt.includes('addition')
    }).length
    const ratio = (newBuilds / data.permits.length) * 100
    subs.push({ name: 'New Construction', value: ratio, raw: `${newBuilds} of ${data.permits.length} are new/addition` })
  }

  if (licenseCount > 0) {
    const density = clamp(licenseCount * 4)
    subs.push({ name: 'License Density', value: density, raw: `${licenseCount} active licenses` })
  }

  if (subs.length === 0) return null

  const score = Math.round(avg(subs.map(s => s.value)))
  const { signal: sig, signalLabel } = signal(score)
  const totalFees = fees.length > 0 ? fees.reduce((a, b) => a + b, 0) : 0
  const newBuilds = data.permits.filter(p => {
    const wt = (p.metadata?.raw_record?.work_type || '').toLowerCase()
    return wt.includes('new') || wt.includes('addition')
  }).length

  return {
    id: 'economic', name: 'Economic', score, subMetrics: subs,
    claim: `${permitCount} active permits, $${Math.round(totalFees / 1000)}K invested, ${newBuilds} new builds — ${signalLabel} economic activity`,
    signal: sig, signalLabel,
    sources: ['building_permits', 'business_licenses'],
    dataPoints: permitCount + licenseCount,
  }
}

function scoreMarket(data: NeighborhoodData, profile: UserProfile, streetscape?: StreetscapeData | null): CategoryScore | null {
  const reviews = data.reviews || []
  const subs: SubMetric[] = []

  const ratings = reviews
    .map(r => (r.metadata?.rating as number) || 0)
    .filter(r => r > 0)
  if (ratings.length > 0) {
    const avgRating = avg(ratings)
    subs.push({ name: 'Avg Rating', value: (avgRating / 5) * 100, raw: `${avgRating.toFixed(1)}/5 across ${ratings.length} businesses` })
  }

  // Review velocity
  const velocities = reviews
    .map(r => r.metadata?.velocity_label as string)
    .filter(Boolean)
    .map(v => {
      if (v === 'high') return 100
      if (v === 'medium' || v === 'med') return 50
      return 20
    })
  if (velocities.length > 0) {
    subs.push({ name: 'Review Velocity', value: avg(velocities), raw: `${velocities.length} businesses tracked` })
  }

  // Competitor saturation
  const keywords = LICENSE_MAP[profile.business_type] || []
  const matchingLicenses = keywords.length > 0
    ? data.licenses.filter(l => {
        const desc = (l.metadata?.raw_record?.license_description || '').toLowerCase()
        return keywords.some(kw => desc.includes(kw))
      }).length
    : data.licenses.length
  const saturation = clamp(100 - matchingLicenses * 8)
  subs.push({ name: 'Competitor Saturation', value: saturation, raw: `${matchingLicenses} direct competitors` })

  // Review volume
  const reviewCount = (data.metrics?.review_count || reviews.length)
  if (reviewCount > 0) {
    subs.push({ name: 'Review Volume', value: clamp(reviewCount / 5), raw: `${reviewCount} total reviews` })
  }

  // Space Availability from streetscape vision data
  if (streetscape?.counts) {
    const total = streetscape.counts.storefront_open + streetscape.counts.storefront_closed + streetscape.counts.for_lease_sign
    if (total > 0) {
      const vacancyRate = (streetscape.counts.for_lease_sign + streetscape.counts.storefront_closed) / total
      // Moderate vacancy (15-40%) is best for new entrants; too low = no space, too high = bad area
      const availability = vacancyRate > 0.4 ? clamp(30) : vacancyRate > 0.15 ? clamp(75) : clamp(40)
      subs.push({ name: 'Space Availability', value: availability, raw: `${streetscape.counts.for_lease_sign} for-lease, ${total} total storefronts` })
    }
  }

  if (subs.length === 0) return null

  const score = Math.round(avg(subs.map(s => s.value)))
  const { signal: sig, signalLabel } = signal(score)
  const avgRating = ratings.length > 0 ? avg(ratings).toFixed(1) : '—'

  return {
    id: 'market', name: 'Market', score, subMetrics: subs,
    claim: `Avg ${avgRating}/5 stars across ${ratings.length} businesses, ${matchingLicenses} direct competitors — ${signalLabel} market conditions`,
    signal: sig, signalLabel,
    sources: ['reviews', 'business_licenses'],
    dataPoints: reviews.length + data.licenses.length,
  }
}

function scoreDemographic(data: NeighborhoodData): CategoryScore | null {
  const d = data.demographics
  if (!d) return null

  const subs: SubMetric[] = []

  if (d.median_gross_rent && d.median_household_income) {
    const rentBurden = (d.median_gross_rent * 12) / d.median_household_income * 100
    const affordability = clamp((1 - (rentBurden - 20) / 25) * 100)
    subs.push({ name: 'Affordability', value: affordability, raw: `$${d.median_gross_rent.toLocaleString()}/mo rent vs $${Math.round(d.median_household_income / 1000)}K income (${Math.round(rentBurden)}% burden)` })
  }

  if (d.unemployment_rate !== undefined) {
    const employment = clamp(100 - d.unemployment_rate * 5)
    subs.push({ name: 'Employment', value: employment, raw: `${d.unemployment_rate.toFixed(1)}% unemployment` })
  }

  if (d.bachelors_degree !== undefined || d.masters_degree !== undefined) {
    const bPct = d.bachelors_degree || 0
    const mPct = d.masters_degree || 0
    const education = clamp((bPct + mPct) * 2)
    subs.push({ name: 'Education', value: education, raw: `${bPct.toFixed(0)}% bachelor's, ${mPct.toFixed(0)}% master's` })
  }

  if (d.total_population) {
    const popSignal = clamp(d.total_population / 500)
    subs.push({ name: 'Population Signal', value: popSignal, raw: `${d.total_population.toLocaleString()} residents` })
  }

  if (subs.length === 0) return null

  const score = Math.round(avg(subs.map(s => s.value)))
  const { signal: sig, signalLabel } = signal(score)

  const rent = d.median_gross_rent ? `$${d.median_gross_rent.toLocaleString()}` : '—'
  const income = d.median_household_income ? `$${Math.round(d.median_household_income / 1000)}K` : '—'
  const burden = d.median_gross_rent && d.median_household_income
    ? `${Math.round((d.median_gross_rent * 12) / d.median_household_income * 100)}%`
    : '—'

  return {
    id: 'demographic', name: 'Demographic', score, subMetrics: subs,
    claim: `Rent ${rent}/mo vs ${income} income (${burden} burden) — ${signalLabel} affordability`,
    signal: sig, signalLabel, sources: ['demographics'], dataPoints: 1,
  }
}

const WALKIN_WEIGHT: Record<string, number> = {
  'Coffee Shop': 1.0,
  'Retail Store': 0.95,
  'Restaurant': 0.9,
  'Bar': 0.85,
  'Salon': 0.8,
  'Professional Services': 0.3,
  'Warehouse': 0.1,
}

function scoreSafety(data: NeighborhoodData, profile: UserProfile): CategoryScore | null {
  const subs: SubMetric[] = []
  let dataPoints = 0

  // CCTV highway traffic (IDOT expressway cameras — not street-level)
  if (data.cctv && data.cctv.cameras.length > 0) {
    const densityMap: Record<string, number> = { low: 25, medium: 60, high: 100 }
    const activity = densityMap[data.cctv.density] ?? 50
    subs.push({ name: 'Highway Activity', value: activity, raw: `${data.cctv.density} density from ${data.cctv.cameras.length} IDOT cameras` })

    const vehScore = clamp((data.cctv.avg_vehicles / 100) * 100)
    subs.push({ name: 'Vehicle Flow', value: vehScore, raw: `~${Math.round(data.cctv.avg_vehicles)} avg vehicles` })

    dataPoints += data.cctv.cameras.length
  }

  // Traffic congestion
  const traffic = data.traffic || []
  if (traffic.length > 0) {
    const congestionValues = traffic
      .map(t => {
        const level = (t.metadata?.congestion_level as string || '').toLowerCase()
        if (level.includes('free')) return 100
        if (level.includes('moderate')) return 66
        if (level.includes('heavy')) return 33
        if (level.includes('blocked')) return 0
        return 66
      })
    subs.push({ name: 'Traffic Accessibility', value: avg(congestionValues), raw: `${traffic.length} traffic zones monitored` })
    dataPoints += traffic.length
  }

  // Walk-In Potential from CTA transit ridership (not highway cameras)
  if (data.transit && data.transit.stations_nearby > 0) {
    const weight = WALKIN_WEIGHT[profile.business_type] ?? 0.5
    const walkinScore = Math.round(data.transit.transit_score * weight)
    const stationList = data.transit.station_names.slice(0, 3).join(', ')
    const ridersLabel = data.transit.total_daily_riders > 0
      ? `~${Math.round(data.transit.total_daily_riders / 1000)}K daily riders`
      : `${data.transit.stations_nearby} stations nearby`
    subs.push({
      name: 'Walk-In Potential',
      value: walkinScore,
      raw: `${data.transit.stations_nearby} CTA stations (${stationList}), ${ridersLabel}, ${profile.business_type} weight ${weight}`,
    })
    dataPoints += data.transit.stations_nearby
  }

  if (subs.length === 0) return null

  const score = Math.round(avg(subs.map(s => s.value)))
  const { signal: sig, signalLabel } = signal(score)
  const vehicleFlow = data.cctv ? `~${Math.round(data.cctv.avg_vehicles)} vehicles` : 'no data'
  const peakClaim = data.cctv?.peak_hour != null ? `, peak ~${data.cctv.peak_hour}:00` : ''
  const transitClaim = data.transit && data.transit.stations_nearby > 0
    ? `, ${data.transit.stations_nearby} CTA stations`
    : ''

  return {
    id: 'safety', name: 'Traffic & Accessibility', score, subMetrics: subs,
    claim: `${vehicleFlow}${peakClaim}${transitClaim} — ${signalLabel} accessibility`,
    signal: sig, signalLabel,
    sources: ['cctv', 'traffic', 'transit'],
    dataPoints,
  }
}

function scoreCommunity(data: NeighborhoodData): CategoryScore | null {
  const newsCount = data.news.length
  const politicsCount = data.politics.length
  const redditCount = data.reddit?.length || 0
  const tiktokCount = data.tiktok?.length || 0
  const totalMentions = newsCount + politicsCount + redditCount + tiktokCount

  if (totalMentions === 0) return null

  const subs: SubMetric[] = []

  if (newsCount > 0) {
    subs.push({ name: 'News Volume', value: clamp(newsCount * 8), raw: `${newsCount} articles` })
  }
  if (politicsCount > 0) {
    subs.push({ name: 'Political Activity', value: clamp(politicsCount * 10), raw: `${politicsCount} legislative items` })
  }
  if (redditCount + tiktokCount > 0) {
    subs.push({ name: 'Social Engagement', value: clamp((redditCount + tiktokCount) * 10), raw: `${redditCount} reddit + ${tiktokCount} tiktok` })
  }
  subs.push({ name: 'Total Buzz', value: clamp((totalMentions / 20) * 100), raw: `${totalMentions} total mentions` })

  const score = Math.round(avg(subs.map(s => s.value)))
  const { signal: sig, signalLabel } = signal(score)

  const socialPart = redditCount + tiktokCount > 0
    ? `, ${redditCount + tiktokCount} social posts`
    : ', no social'

  return {
    id: 'community', name: 'Community', score, subMetrics: subs,
    claim: `${newsCount} news mentions${socialPart} — ${score < 40 ? 'QUIET' : signalLabel} neighborhood`,
    signal: sig, signalLabel,
    sources: ['news', 'politics', 'reddit', 'tiktok'].filter((_, i) =>
      [newsCount, politicsCount, redditCount, tiktokCount][i] > 0
    ),
    dataPoints: totalMentions,
  }
}

// ── WLS Composite ──────────────────────────────────────────────────

function computeWLS(categories: CategoryScore[], profile: RiskProfile): number {
  const weights = WEIGHTS[profile]
  let weightedSum = 0
  let totalWeight = 0
  for (const cat of categories) {
    const w = weights[cat.id] || 0
    weightedSum += cat.score * w
    totalWeight += w
  }
  return totalWeight > 0 ? Math.round(weightedSum / totalWeight) : 0
}

// ── Public API ─────────────────────────────────────────────────────

export function computeInsights(
  data: NeighborhoodData,
  profile: UserProfile,
  riskProfile: RiskProfile,
  streetscape?: StreetscapeData | null,
): InsightsResult {
  const scorers = [
    scoreRegulatory(data),
    scoreEconomic(data),
    scoreMarket(data, profile, streetscape),
    scoreDemographic(data),
    scoreSafety(data, profile),
    scoreCommunity(data),
  ]

  const categories = scorers.filter((c): c is CategoryScore => c !== null)
  const overall = computeWLS(categories, riskProfile)

  return {
    categories,
    overall,
    profile: riskProfile,
    coverageCount: categories.length,
    computedAt: new Date().toISOString(),
  }
}
