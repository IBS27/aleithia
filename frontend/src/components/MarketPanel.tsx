import type { Document } from '../types/index.ts'

interface Props {
  reviews: Document[]
  realestate: Document[]
}

function ratingTint(rating: number): string {
  if (rating >= 4.5) return 'text-emerald-300'
  if (rating >= 4) return 'text-emerald-400/80'
  if (rating >= 3) return 'text-amber-400/80'
  return 'text-red-400/80'
}

function ratingBar(rating: number): string {
  if (rating >= 4) return 'bg-emerald-400/70'
  if (rating >= 3) return 'bg-amber-400/70'
  return 'bg-red-400/70'
}

function BusinessRow({ review }: { review: Document }) {
  const rating = (review.metadata?.rating as number) || 0
  const reviewCount = (review.metadata?.review_count as number) || 0
  const priceLevel = (review.metadata?.price_level as string) || ''
  const categories = (review.metadata?.categories as string[]) || []
  const velocity = (review.metadata?.velocity_label as string) || ''

  return (
    <div className="border-b border-white/[0.04] last:border-0 px-3 py-2.5 hover:bg-white/[0.02] transition-colors">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 mb-1">
            <h4 className="text-[13px] font-semibold text-white/90 truncate">{review.title}</h4>
            {rating > 0 && (
              <div className="flex items-center gap-1 shrink-0">
                <span className={`text-[13px] font-bold font-mono ${ratingTint(rating)}`}>
                  {rating.toFixed(1)}
                </span>
                <span className="text-[9px] font-mono text-white/30">★</span>
              </div>
            )}
          </div>

          {/* Rating bar comparison layer */}
          {rating > 0 && (
            <div className="flex items-center gap-2 mb-1.5">
              <div className="flex-1 h-0.5 bg-white/[0.06] overflow-hidden rounded-full">
                <div className={`h-0.5 ${ratingBar(rating)}`} style={{ width: `${(rating / 5) * 100}%` }} />
              </div>
              <span className="text-[9px] font-mono text-white/35 shrink-0">
                {reviewCount} reviews
              </span>
            </div>
          )}

          {/* Metadata row */}
          <div className="flex items-center gap-2 text-[10px] font-mono text-white/30 flex-wrap">
            {priceLevel && <span className="text-emerald-400/60">{priceLevel}</span>}
            {velocity && (
              <span className="px-1.5 py-0.5 border border-cyan-500/25 text-cyan-300/70 bg-cyan-500/[0.04] uppercase tracking-wider">
                {velocity}
              </span>
            )}
            {categories.slice(0, 2).map((cat) => (
              <span key={cat} className="text-white/40">{cat}</span>
            ))}
          </div>
        </div>
        {review.url && (
          <a
            href={review.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] font-mono uppercase tracking-wider text-white/30 hover:text-white/70 shrink-0 transition-colors self-center"
          >
            Open ›
          </a>
        )}
      </div>
    </div>
  )
}

function ListingRow({ listing }: { listing: Document }) {
  const propertyType = (listing.metadata?.property_type as string) || ''
  const size = (listing.metadata?.size_sqft as number) || 0
  const price = (listing.metadata?.price as string) || ''
  const listingType = (listing.metadata?.listing_type as string) || ''

  const typeAccent = listingType.toLowerCase() === 'lease'
    ? 'border-blue-500/25 text-blue-300/70 bg-blue-500/[0.04]'
    : 'border-amber-500/25 text-amber-300/70 bg-amber-500/[0.04]'

  return (
    <div className="border-b border-white/[0.04] last:border-0 px-3 py-2.5 hover:bg-white/[0.02] transition-colors">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            {listingType && (
              <span className={`text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border ${typeAccent}`}>
                {listingType}
              </span>
            )}
            {propertyType && (
              <span className="text-[9px] font-mono uppercase tracking-wider text-violet-300/60 border border-violet-500/20 px-1.5 py-0.5 bg-violet-500/[0.03]">
                {propertyType}
              </span>
            )}
            {price && <span className="text-[12px] font-mono font-semibold text-white/80 ml-auto shrink-0">{price}</span>}
          </div>
          <h4 className="text-[13px] font-semibold text-white/90 leading-snug line-clamp-2">{listing.title}</h4>
          <div className="flex items-center gap-2 text-[10px] font-mono text-white/30 mt-1">
            {size > 0 && <span>{size.toLocaleString()} sqft</span>}
          </div>
        </div>
        {listing.url && (
          <a
            href={listing.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] font-mono uppercase tracking-wider text-white/30 hover:text-white/70 shrink-0 transition-colors self-center"
          >
            Tour ›
          </a>
        )}
      </div>
    </div>
  )
}

export default function MarketPanel({ reviews, realestate }: Props) {
  const hasContent = reviews.length > 0 || realestate.length > 0

  if (!hasContent) {
    return (
      <div className="border border-white/[0.06] bg-white/[0.01] p-8 text-center">
        <div className="text-xs font-mono text-white/30 uppercase tracking-wider">No market data</div>
        <div className="text-[10px] font-mono text-white/20 mt-1">Incumbents and commercial listings will appear once market pipelines run.</div>
      </div>
    )
  }

  // Compute market summary stats
  const ratings = reviews.map(r => (r.metadata?.rating as number) || 0).filter(r => r > 0)
  const avgRating = ratings.length > 0 ? ratings.reduce((a, b) => a + b, 0) / ratings.length : 0
  const strongIncumbents = ratings.filter(r => r >= 4).length
  const weakIncumbents = ratings.filter(r => r < 3).length

  const saleListings = realestate.filter(r => (r.metadata?.listing_type as string)?.toLowerCase() === 'sale').length
  const leaseListings = realestate.filter(r => (r.metadata?.listing_type as string)?.toLowerCase() === 'lease').length
  const untaggedListings = Math.max(0, realestate.length - saleListings - leaseListings)

  return (
    <div className="space-y-4">
      {/* Market summary header */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-white/[0.04] border border-white/[0.06]">
        <div className="bg-[#06080d] px-4 py-3">
          <div className="text-[9px] font-mono uppercase tracking-wider text-white/30">Avg Rating</div>
          <div className="text-xl font-bold font-mono mt-1">
            <span className={avgRating > 0 ? ratingTint(avgRating) : 'text-white/30'}>
              {avgRating > 0 ? avgRating.toFixed(1) : '—'}
            </span>
            {avgRating > 0 && <span className="text-[11px] text-white/30 ml-1">/ 5</span>}
          </div>
          <div className="text-[9px] font-mono text-white/25 mt-0.5">across {ratings.length} biz</div>
        </div>
        <div className="bg-[#06080d] px-4 py-3">
          <div className="text-[9px] font-mono uppercase tracking-wider text-white/30">Strong Incumbents</div>
          <div className="text-xl font-bold font-mono text-emerald-400/80 mt-1">{strongIncumbents}</div>
          <div className="text-[9px] font-mono text-white/25 mt-0.5">rated 4+ stars</div>
        </div>
        <div className="bg-[#06080d] px-4 py-3">
          <div className="text-[9px] font-mono uppercase tracking-wider text-white/30">Weak Incumbents</div>
          <div className="text-xl font-bold font-mono text-red-400/80 mt-1">{weakIncumbents}</div>
          <div className="text-[9px] font-mono text-white/25 mt-0.5">opportunity gap</div>
        </div>
        <div className="bg-[#06080d] px-4 py-3">
          <div className="text-[9px] font-mono uppercase tracking-wider text-white/30">Listings Indexed</div>
          <div className="text-xl font-bold font-mono text-white mt-1">
            {realestate.length}
          </div>
          <div className="text-[9px] font-mono text-white/25 mt-0.5">
            {(() => {
              const parts: string[] = []
              if (leaseListings) parts.push(`${leaseListings} lease`)
              if (saleListings) parts.push(`${saleListings} sale`)
              if (untaggedListings) parts.push(`${untaggedListings} unspec.`)
              return parts.length ? parts.join(' · ') : 'commercial properties'
            })()}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Business Reviews */}
        <div className="border border-white/[0.06] bg-white/[0.01]">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-white/[0.04] bg-white/[0.015]">
            <span className="w-1 h-1 rounded-full bg-cyan-400/70" />
            <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-cyan-300/70">Incumbent Scan</span>
            <span className="text-[10px] font-mono text-white/25">{reviews.length} listings</span>
          </div>
          {reviews.length > 0 ? (
            <div>{reviews.map((review) => <BusinessRow key={review.id} review={review} />)}</div>
          ) : (
            <div className="p-6 text-center text-[10px] font-mono text-white/20">
              No business reviews indexed for this area yet.
            </div>
          )}
        </div>

        {/* Commercial Listings - Opportunity Inventory */}
        <div className="border border-white/[0.06] bg-white/[0.01]">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-white/[0.04] bg-white/[0.015]">
            <span className="w-1 h-1 rounded-full bg-amber-400/70" />
            <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-amber-300/70">Opportunity Inventory</span>
            <span className="text-[10px] font-mono text-white/25">{realestate.length} properties</span>
          </div>
          {realestate.length > 0 ? (
            <div>{realestate.map((listing) => <ListingRow key={listing.id} listing={listing} />)}</div>
          ) : (
            <div className="p-6 text-center text-[10px] font-mono text-white/20">
              No commercial listings available for this area yet.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
