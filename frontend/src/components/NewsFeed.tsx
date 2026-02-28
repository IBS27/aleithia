import type { Document } from '../types/index.ts'

interface Props {
  news: Document[]
  politics: Document[]
}

export default function NewsFeed({ news, politics }: Props) {
  const hasContent = news.length > 0 || politics.length > 0

  if (!hasContent) {
    return (
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-8 text-center text-gray-500">
        No news or political data available for this neighborhood.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* News Articles */}
      {news.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-300">Local News</h3>
            <span className="text-xs text-gray-500">{news.length} articles</span>
          </div>
          {news.map((article) => (
            <div key={article.id} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h4 className="font-semibold text-gray-100 mb-1">{article.title}</h4>
                  {article.content && (
                    <p className="text-xs text-gray-400 leading-relaxed mb-2">
                      {article.content.substring(0, 200)}
                      {article.content.length > 200 && '...'}
                    </p>
                  )}
                  <div className="flex items-center gap-3 text-xs text-gray-500">
                    <span>{new Date(article.timestamp).toLocaleDateString()}</span>
                    <span className="px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                      News
                    </span>
                  </div>
                </div>
                {article.url && (
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-indigo-400 hover:text-indigo-300 ml-4 shrink-0"
                  >
                    Read
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Political Activity */}
      {politics.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-300">City Council Activity</h3>
            <span className="text-xs text-gray-500">{politics.length} items</span>
          </div>
          {politics.map((item) => {
            const matterType = (item.metadata?.matter_type as string) || 'Item'
            const status = (item.metadata?.status as string) || ''

            return (
              <div key={item.id} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h4 className="font-semibold text-gray-100 mb-1 text-sm">{item.title}</h4>
                    <div className="flex items-center gap-2 text-xs text-gray-500 mt-1">
                      <span className="px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">
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
                      className="text-xs text-indigo-400 hover:text-indigo-300 ml-4 shrink-0"
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
