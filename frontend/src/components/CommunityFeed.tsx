import type { Document } from '../types/index.ts'

function parseViewCount(raw: string): number {
  if (!raw) return 0
  const cleaned = raw.trim().toUpperCase().replace(/,/g, '')
  const match = cleaned.match(/^([\d.]+)\s*([KMB])?$/)
  if (!match) return parseInt(cleaned, 10) || 0
  const num = parseFloat(match[1])
  const suffix = match[2]
  if (suffix === 'K') return Math.round(num * 1_000)
  if (suffix === 'M') return Math.round(num * 1_000_000)
  if (suffix === 'B') return Math.round(num * 1_000_000_000)
  return Math.round(num)
}

function formatViews(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toString()
}

function isCountOnlyText(raw: string): boolean {
  if (!raw) return false
  return /^\s*\d[\d,.\s]*[KMB]?\s*$/i.test(raw)
}

function cleanTikTokContent(raw: string): string {
  const text = (raw || '').trim()
  if (!text) return ''
  if (isCountOnlyText(text)) return ''
  if (text.includes('\n[Transcript]')) {
    const [firstLine, ...rest] = text.split('\n')
    if (isCountOnlyText(firstLine)) {
      return rest.join('\n').trim()
    }
  }
  return text
}

function transcriptHeadline(raw: string): string {
  const text = cleanTikTokContent(raw)
  if (!text) return ''
  const transcriptPart = text.includes('[Transcript]') ? text.split('[Transcript]')[1] : text
  const compact = transcriptPart.replace(/\s+/g, ' ').trim()
  if (!compact) return ''

  const endMatch = compact.match(/^(.*?[.!?])(\s|$)/)
  const sentence = endMatch ? endMatch[1].trim() : compact
  const trimmed = sentence.length > 120 ? `${sentence.slice(0, 117)}...` : sentence
  return trimmed.replace(/^[\d,.\s]+[KMB]?\s*/i, '').trim()
}

interface Props {
  reddit: Document[]
  tiktok: Document[]
}

function FeedHeader({ label, count, accent, dot, suffix }: {
  label: string
  count: number
  accent: string
  dot: string
  suffix: string
}) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 border-b border-white/[0.04] bg-white/[0.015]">
      <span className={`w-1 h-1 rounded-full ${dot}`} />
      <span className={`text-[10px] font-mono uppercase tracking-[0.2em] ${accent}`}>{label}</span>
      <span className="text-[10px] font-mono text-white/25">{count} {suffix}</span>
    </div>
  )
}

function RedditPost({ post }: { post: Document }) {
  const subreddit = (post.metadata?.subreddit as string) || ''
  const score = (post.metadata?.score as number) || 0
  const numComments = (post.metadata?.num_comments as number) || 0

  return (
    <div className="border-b border-white/[0.04] last:border-0 px-3 py-2.5 hover:bg-white/[0.02] transition-colors">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            {subreddit && (
              <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border border-orange-500/25 text-orange-300/80 bg-orange-500/[0.04]">
                r/{subreddit}
              </span>
            )}
            <div className="flex items-center gap-2 text-[9px] font-mono text-white/35 ml-auto shrink-0">
              {score > 0 && (
                <span className="flex items-center gap-0.5">
                  <span className="text-orange-300/60">▲</span>
                  {score}
                </span>
              )}
              {numComments > 0 && <span>{numComments} comments</span>}
              <span>{new Date(post.timestamp).toLocaleDateString()}</span>
            </div>
          </div>
          <h4 className="text-[13px] font-semibold text-white/90 leading-snug line-clamp-2">{post.title}</h4>
          {post.content && (
            <p className="text-[11px] text-white/45 mt-1 leading-relaxed line-clamp-2">
              {post.content.substring(0, 180)}
              {post.content.length > 180 && '...'}
            </p>
          )}
        </div>
        {post.url && (
          <a
            href={post.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] font-mono uppercase tracking-wider text-white/30 hover:text-white/70 shrink-0 transition-colors self-center"
          >
            View ›
          </a>
        )}
      </div>
    </div>
  )
}

function TikTokPost({ video }: { video: Document }) {
  const creator = (video.metadata?.creator as string) || ''
  const query = (video.metadata?.search_query as string) || ''
  const views = parseViewCount((video.metadata?.views as string) || '')
  const hashtags = (video.metadata?.hashtags as string[]) || []
  const rawTitle = (video.title || '').trim()
  const transcriptTitle = transcriptHeadline(video.content)
  const hasMeaningfulTitle = rawTitle && !isCountOnlyText(rawTitle) && rawTitle.toLowerCase() !== 'tiktok video'
  const titleText = hasMeaningfulTitle
    ? rawTitle
    : transcriptTitle || (creator ? `@${creator}` : '') || (query ? `TikTok: ${query}` : 'TikTok video')
  const contentText = cleanTikTokContent(video.content)

  return (
    <div className="border-b border-white/[0.04] last:border-0 px-3 py-2.5 hover:bg-white/[0.02] transition-colors">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            {creator && (
              <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border border-pink-500/25 text-pink-300/80 bg-pink-500/[0.04]">
                @{creator}
              </span>
            )}
            <div className="flex items-center gap-2 text-[9px] font-mono text-white/35 ml-auto shrink-0">
              {views > 0 && (
                <span className="flex items-center gap-0.5">
                  <span className="text-pink-300/60">●</span>
                  {formatViews(views)} views
                </span>
              )}
              <span>{new Date(video.timestamp).toLocaleDateString()}</span>
            </div>
          </div>
          <h4 className="text-[13px] font-semibold text-white/90 leading-snug line-clamp-2">{titleText}</h4>
          {contentText && (
            <p className="text-[11px] text-white/45 mt-1 leading-relaxed line-clamp-2">
              {contentText.substring(0, 150)}
              {contentText.length > 150 && '...'}
            </p>
          )}
          {hashtags.length > 0 && (
            <div className="flex items-center gap-1 mt-1.5 flex-wrap">
              {hashtags.slice(0, 4).map((tag) => (
                <span key={tag} className="text-[9px] font-mono text-pink-300/50">
                  #{tag}
                </span>
              ))}
            </div>
          )}
        </div>
        {video.url && (
          <a
            href={video.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] font-mono uppercase tracking-wider text-white/30 hover:text-white/70 shrink-0 transition-colors self-center"
          >
            Watch ›
          </a>
        )}
      </div>
    </div>
  )
}

export default function CommunityFeed({ reddit, tiktok }: Props) {
  const displayedTikTok = tiktok.slice(0, 6)
  const hasContent = reddit.length > 0 || displayedTikTok.length > 0

  if (!hasContent) {
    return (
      <div className="border border-white/[0.06] bg-white/[0.01] p-8 text-center">
        <div className="text-xs font-mono text-white/30 uppercase tracking-wider">No community data</div>
        <div className="text-[10px] font-mono text-white/20 mt-1">Reddit discussions and TikTok chatter will surface once social pipelines run.</div>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className="border border-white/[0.06] bg-white/[0.01]">
        <FeedHeader
          label="Reddit Discussions"
          count={reddit.length}
          accent="text-orange-300/70"
          dot="bg-orange-400/70"
          suffix="posts"
        />
        {reddit.length > 0 ? (
          <div>{reddit.map((post) => <RedditPost key={post.id} post={post} />)}</div>
        ) : (
          <div className="p-6 text-center text-[10px] font-mono text-white/20">
            No Reddit posts indexed for this area yet.
          </div>
        )}
      </div>

      <div className="border border-white/[0.06] bg-white/[0.01]">
        <FeedHeader
          label="TikTok Signal"
          count={displayedTikTok.length}
          accent="text-pink-300/70"
          dot="bg-pink-400/70"
          suffix="videos"
        />
        {displayedTikTok.length > 0 ? (
          <div>{displayedTikTok.map((video) => <TikTokPost key={video.id} video={video} />)}</div>
        ) : (
          <div className="p-6 text-center text-[10px] font-mono text-white/20">
            No TikTok videos for this profile yet.
          </div>
        )}
      </div>
    </div>
  )
}
