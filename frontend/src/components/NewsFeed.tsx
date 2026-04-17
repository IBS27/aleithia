import type { Document } from '../types/index.ts'

interface Props {
  news: Document[]
  politics: Document[]
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
      <div className="flex-1" />
    </div>
  )
}

function NewsRow({ article }: { article: Document }) {
  return (
    <div className="border-b border-white/[0.04] last:border-0 px-3 py-2.5 hover:bg-white/[0.02] transition-colors">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border border-blue-500/25 text-blue-300/70 bg-blue-500/[0.04]">
              News
            </span>
            {article.source && (
              <span className="text-[9px] font-mono text-white/35 truncate">{article.source}</span>
            )}
            <span className="text-[9px] font-mono text-white/20 ml-auto shrink-0">
              {new Date(article.timestamp).toLocaleDateString()}
            </span>
          </div>
          <h4 className="text-[13px] font-semibold text-white/90 leading-snug line-clamp-2">{article.title}</h4>
          {article.content && (
            <p className="text-[11px] text-white/45 mt-1 leading-relaxed line-clamp-2">
              {article.content.substring(0, 180)}
              {article.content.length > 180 && '...'}
            </p>
          )}
        </div>
        {article.url && (
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] font-mono uppercase tracking-wider text-white/30 hover:text-white/70 shrink-0 transition-colors self-center"
          >
            Read ›
          </a>
        )}
      </div>
    </div>
  )
}

function PolicyRow({ item }: { item: Document }) {
  const matterType = (item.metadata?.matter_type as string) || 'Item'
  const status = (item.metadata?.status as string) || ''
  return (
    <div className="border-b border-white/[0.04] last:border-0 px-3 py-2.5 hover:bg-white/[0.02] transition-colors">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 border border-purple-500/25 text-purple-300/70 bg-purple-500/[0.04]">
              {matterType}
            </span>
            {status && (
              <span className="text-[9px] font-mono text-white/35 uppercase tracking-wider">
                {status}
              </span>
            )}
            <span className="text-[9px] font-mono text-white/20 ml-auto shrink-0">
              {new Date(item.timestamp).toLocaleDateString()}
            </span>
          </div>
          <h4 className="text-[13px] font-semibold text-white/90 leading-snug line-clamp-2">{item.title}</h4>
        </div>
        {item.url && (
          <a
            href={item.url}
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

export default function NewsFeed({ news, politics }: Props) {
  const hasContent = news.length > 0 || politics.length > 0

  if (!hasContent) {
    return (
      <div className="border border-white/[0.06] bg-white/[0.01] p-8 text-center">
        <div className="text-xs font-mono text-white/30 uppercase tracking-wider">No intelligence data</div>
        <div className="text-[10px] font-mono text-white/20 mt-1">News and policy items will appear once pipelines populate this neighborhood.</div>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Local News Feed */}
      <div className="border border-white/[0.06] bg-white/[0.01]">
        <FeedHeader
          label="Local News"
          count={news.length}
          accent="text-blue-300/70"
          dot="bg-blue-400/70"
          suffix="articles"
        />
        {news.length > 0 ? (
          <div>{news.map((article) => <NewsRow key={article.id} article={article} />)}</div>
        ) : (
          <div className="p-6 text-center text-[10px] font-mono text-white/20">
            No local news available for this area yet.
          </div>
        )}
      </div>

      {/* City Council / Policy Feed */}
      <div className="border border-white/[0.06] bg-white/[0.01]">
        <FeedHeader
          label="City Council & Policy"
          count={politics.length}
          accent="text-purple-300/70"
          dot="bg-purple-400/70"
          suffix="items"
        />
        {politics.length > 0 ? (
          <div>{politics.map((item) => <PolicyRow key={item.id} item={item} />)}</div>
        ) : (
          <div className="p-6 text-center text-[10px] font-mono text-white/20">
            No policy activity logged for this area yet.
          </div>
        )}
      </div>
    </div>
  )
}
