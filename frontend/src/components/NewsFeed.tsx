import type { Document } from '../types/index.ts'

interface Props {
  news: Document[]
  politics: Document[]
}

function ExternalIcon() {
  return (
    <svg className="w-3 h-3 text-white/15 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" />
    </svg>
  )
}

export default function NewsFeed({ news, politics }: Props) {
  const hasContent = news.length > 0 || politics.length > 0

  if (!hasContent) {
    return (
      <div className="border border-white/[0.06] p-8 text-center text-xs font-mono text-white/20 uppercase tracking-wider">
        No intelligence data available
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {news.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between px-1">
            <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30">Local News</h3>
            <span className="text-[10px] font-mono text-white/15">{news.length} articles</span>
          </div>
          {news.map((article) => (
            <a
              key={article.id}
              href={article.url || undefined}
              target={article.url ? '_blank' : undefined}
              rel={article.url ? 'noopener noreferrer' : undefined}
              className={`block border border-white/[0.06] bg-white/[0.01] p-4 transition-colors ${
                article.url ? 'hover:bg-white/[0.04] hover:border-white/[0.12] cursor-pointer' : ''
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <h4 className="text-sm font-semibold text-white mb-1">{article.title}</h4>
                  {article.content && (
                    <p className="text-xs text-white/30 leading-relaxed mb-2">
                      {article.content.substring(0, 200)}
                      {article.content.length > 200 && '...'}
                    </p>
                  )}
                  <div className="flex items-center gap-3 text-[10px] font-mono text-white/15">
                    <span>{new Date(article.timestamp).toLocaleDateString()}</span>
                    <span className="uppercase px-2 py-0.5 border border-blue-500/20 text-blue-400/60">
                      News
                    </span>
                  </div>
                </div>
                {article.url && <ExternalIcon />}
              </div>
            </a>
          ))}
        </div>
      )}

      {politics.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between px-1">
            <h3 className="text-[10px] font-mono font-medium uppercase tracking-wider text-white/30">City Council</h3>
            <span className="text-[10px] font-mono text-white/15">{politics.length} items</span>
          </div>
          {politics.map((item) => {
            const matterType = (item.metadata?.matter_type as string) || 'Item'
            const status = (item.metadata?.status as string) || ''

            return (
              <a
                key={item.id}
                href={item.url || undefined}
                target={item.url ? '_blank' : undefined}
                rel={item.url ? 'noopener noreferrer' : undefined}
                className={`block border border-white/[0.06] bg-white/[0.01] p-4 transition-colors ${
                  item.url ? 'hover:bg-white/[0.04] hover:border-white/[0.12] cursor-pointer' : ''
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-semibold text-white mb-1">{item.title}</h4>
                    <div className="flex items-center gap-2 text-[10px] font-mono text-white/15 mt-1">
                      <span className="uppercase px-2 py-0.5 border border-purple-500/20 text-purple-400/60">
                        {matterType}
                      </span>
                      {status && <span>{status}</span>}
                      <span>{new Date(item.timestamp).toLocaleDateString()}</span>
                    </div>
                  </div>
                  {item.url && <ExternalIcon />}
                </div>
              </a>
            )
          })}
        </div>
      )}
    </div>
  )
}
