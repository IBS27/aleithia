import type { Document } from '../types/index.ts'

interface Props {
  reviews: Document[]
  realestate: Document[]
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
              <div key={review.id} className="border border-white/[0.06] bg-white/[0.01] p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
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
                  {review.url && (
                    <a
                      href={review.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[10px] font-mono uppercase tracking-wider text-white/25 hover:text-white/50 ml-4 shrink-0 transition-colors"
                    >
                      View
                    </a>
                  )}
                </div>
              </div>
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
              <div key={listing.id} className="border border-white/[0.06] bg-white/[0.01] p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
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
                  {listing.url && (
                    <a
                      href={listing.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[10px] font-mono uppercase tracking-wider text-white/25 hover:text-white/50 ml-4 shrink-0 transition-colors"
                    >
                      View
                    </a>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
