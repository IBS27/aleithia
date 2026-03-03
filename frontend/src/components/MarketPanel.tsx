import type { Document } from '../types/index.ts'

interface Props {
  reviews: Document[]
  realestate: Document[]
}

function ExternalIcon() {
  return (
    <svg className="w-3 h-3 text-white/15 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" />
    </svg>
  )
}

export default function MarketPanel({ reviews, realestate }: Props) {
  const hasContent = reviews.length > 0 || realestate.length > 0

  if (!hasContent) {
    return (
      <div className="border border-white/[0.06] p-8 text-center text-xs font-mono text-white/20 uppercase tracking-wider">
        No market data available
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {reviews.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between px-1">
            <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30">Business Reviews</h3>
            <span className="text-[10px] font-mono text-white/15">{reviews.length} listings</span>
          </div>
          {reviews.map((review) => {
            const rating = (review.metadata?.rating as number) || 0
            const reviewCount = (review.metadata?.review_count as number) || 0
            const priceLevel = (review.metadata?.price_level as string) || ''
            const categories = (review.metadata?.categories as string[]) || []
            const velocity = (review.metadata?.velocity_label as string) || ''

            return (
              <a
                key={review.id}
                href={review.url || undefined}
                target={review.url ? '_blank' : undefined}
                rel={review.url ? 'noopener noreferrer' : undefined}
                className={`block border border-white/[0.06] bg-white/[0.01] p-4 transition-colors ${
                  review.url ? 'hover:bg-white/[0.04] hover:border-white/[0.12] cursor-pointer' : ''
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-semibold text-white mb-1">{review.title}</h4>
                    <div className="flex items-center gap-3 text-[10px] font-mono text-white/15 flex-wrap">
                      {rating > 0 && (
                        <span className={`font-bold ${rating >= 4 ? 'text-green-400/70' : rating >= 3 ? 'text-yellow-400/70' : 'text-red-400/70'}`}>
                          {rating}/5
                        </span>
                      )}
                      {reviewCount > 0 && <span>{reviewCount} reviews</span>}
                      {priceLevel && <span>{priceLevel}</span>}
                      {velocity && (
                        <span className="px-2 py-0.5 border border-cyan-500/20 text-cyan-400/60">
                          {velocity}
                        </span>
                      )}
                      {categories.slice(0, 2).map((cat) => (
                        <span key={cat} className="px-1.5 py-0.5 border border-amber-500/20 text-amber-400/60">
                          {cat}
                        </span>
                      ))}
                    </div>
                  </div>
                  {review.url && <ExternalIcon />}
                </div>
              </a>
            )
          })}
        </div>
      )}

      {realestate.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between px-1">
            <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30">Commercial Listings</h3>
            <span className="text-[10px] font-mono text-white/15">{realestate.length} properties</span>
          </div>
          {realestate.map((listing) => {
            const propertyType = (listing.metadata?.property_type as string) || ''
            const size = (listing.metadata?.size_sqft as number) || 0
            const price = (listing.metadata?.price as string) || ''
            const listingType = (listing.metadata?.listing_type as string) || ''

            return (
              <a
                key={listing.id}
                href={listing.url || undefined}
                target={listing.url ? '_blank' : undefined}
                rel={listing.url ? 'noopener noreferrer' : undefined}
                className={`block border border-white/[0.06] bg-white/[0.01] p-4 transition-colors ${
                  listing.url ? 'hover:bg-white/[0.04] hover:border-white/[0.12] cursor-pointer' : ''
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-semibold text-white mb-1">{listing.title}</h4>
                    <div className="flex items-center gap-3 text-[10px] font-mono text-white/15 flex-wrap">
                      {propertyType && (
                        <span className="px-2 py-0.5 border border-violet-500/20 text-violet-400/60 uppercase">
                          {propertyType}
                        </span>
                      )}
                      {size > 0 && <span>{size.toLocaleString()} sqft</span>}
                      {price && <span className="text-white/40">{price}</span>}
                      {listingType && (
                        <span className={`px-2 py-0.5 border ${listingType.toLowerCase() === 'lease' ? 'border-blue-500/20 text-blue-400/60' : 'border-orange-500/20 text-orange-400/60'}`}>
                          {listingType}
                        </span>
                      )}
                    </div>
                  </div>
                  {listing.url && <ExternalIcon />}
                </div>
              </a>
            )
          })}
        </div>
      )}
    </div>
  )
}
