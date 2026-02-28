import type { Document } from '../types/index.ts'

interface Props {
  news: Document[]
  politics: Document[]
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
            <div key={article.id} className="border border-white/[0.06] bg-white/[0.01] p-4">
              <div className="flex items-start justify-between">
                <div className="flex-1">
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
                {article.url && (
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] font-mono uppercase tracking-wider text-white/25 hover:text-white/50 ml-4 shrink-0 transition-colors"
                  >
                    Read
                  </a>
                )}
              </div>
            </div>
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
              <div key={item.id} className="border border-white/[0.06] bg-white/[0.01] p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h4 className="text-sm font-semibold text-white mb-1">{item.title}</h4>
                    <div className="flex items-center gap-2 text-[10px] font-mono text-white/15 mt-1">
                      <span className="uppercase px-2 py-0.5 border border-purple-500/20 text-purple-400/60">
                        {matterType}
                      </span>
                      {status && <span>{status}</span>}
                      <span>{new Date(item.timestamp).toLocaleDateString()}</span>
                    </div>
                  </div>
                  {item.url && (
                    <a
                      href={item.url}
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
