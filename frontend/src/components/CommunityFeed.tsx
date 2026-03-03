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

function ExternalIcon() {
  return (
    <svg className="w-3 h-3 text-white/15 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" />
    </svg>
  )
}

interface Props {
  reddit: Document[]
  tiktok: Document[]
}

export default function CommunityFeed({ reddit, tiktok }: Props) {
  const displayedTikTok = tiktok.slice(0, 5)
  const hasContent = reddit.length > 0 || displayedTikTok.length > 0

  if (!hasContent) {
    return (
      <div className="border border-white/[0.06] p-8 text-center text-xs font-mono text-white/20 uppercase tracking-wider">
        No community data available
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {reddit.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between px-1">
            <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30">Reddit Discussions</h3>
            <span className="text-[10px] font-mono text-white/15">{reddit.length} posts</span>
          </div>
          {reddit.map((post) => {
            const subreddit = (post.metadata?.subreddit as string) || ''
            const score = (post.metadata?.score as number) || 0
            const numComments = (post.metadata?.num_comments as number) || 0

            return (
              <a
                key={post.id}
                href={post.url || undefined}
                target={post.url ? '_blank' : undefined}
                rel={post.url ? 'noopener noreferrer' : undefined}
                className={`block border border-white/[0.06] bg-white/[0.01] p-4 transition-colors ${
                  post.url ? 'hover:bg-white/[0.04] hover:border-white/[0.12] cursor-pointer' : ''
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-semibold text-white mb-1">{post.title}</h4>
                    {post.content && (
                      <p className="text-xs text-white/30 leading-relaxed mb-2">
                        {post.content.substring(0, 200)}
                        {post.content.length > 200 && '...'}
                      </p>
                    )}
                    <div className="flex items-center gap-3 text-[10px] font-mono text-white/15">
                      <span>{new Date(post.timestamp).toLocaleDateString()}</span>
                      {subreddit && (
                        <span className="px-2 py-0.5 border border-green-500/20 text-green-400/60">
                          r/{subreddit}
                        </span>
                      )}
                      {score > 0 && <span>{score} pts</span>}
                      {numComments > 0 && <span>{numComments} comments</span>}
                    </div>
                  </div>
                  {post.url && <ExternalIcon />}
                </div>
              </a>
            )
          })}
        </div>
      )}

      {tiktok.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between px-1">
            <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30">TikTok</h3>
            <span className="text-[10px] font-mono text-white/15">{displayedTikTok.length} videos</span>
          </div>
          {displayedTikTok.length === 0 && (
            <div className="border border-white/[0.06] bg-white/[0.01] p-4 text-[10px] font-mono uppercase tracking-wider text-white/25">
              No TikTok videos for this profile yet
            </div>
          )}
          {displayedTikTok.map((video) => {
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
              <a
                key={video.id}
                href={video.url || undefined}
                target={video.url ? '_blank' : undefined}
                rel={video.url ? 'noopener noreferrer' : undefined}
                className={`block border border-white/[0.06] bg-white/[0.01] p-4 transition-colors ${
                  video.url ? 'hover:bg-white/[0.04] hover:border-white/[0.12] cursor-pointer' : ''
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-semibold text-white mb-1">{titleText}</h4>
                    {contentText && (
                      <p className="text-xs text-white/30 leading-relaxed mb-2">
                        {contentText.substring(0, 150)}
                        {contentText.length > 150 && '...'}
                      </p>
                    )}
                    <div className="flex items-center gap-3 text-[10px] font-mono text-white/15 flex-wrap">
                      <span>{new Date(video.timestamp).toLocaleDateString()}</span>
                      {creator && <span>@{creator}</span>}
                      {views > 0 && <span>{views.toLocaleString()} views</span>}
                      {hashtags.slice(0, 3).map((tag) => (
                        <span key={tag} className="px-1.5 py-0.5 border border-pink-500/20 text-pink-400/60">
                          #{tag}
                        </span>
                      ))}
                    </div>
                  </div>
                  {video.url && <ExternalIcon />}
                </div>
              </a>
            )
          })}
        </div>
      )}
    </div>
  )
}
