import type { Document } from './types/index.ts'

// Strip scraped markup and common entities before comparing titles/snippets.
export function cleanArticleText(raw: string): string {
  if (!raw) return ''
  const stripped = raw
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<[^>]+>/g, ' ')
  const entityMap: Record<string, string> = {
    '&amp;': '&',
    '&lt;': '<',
    '&gt;': '>',
    '&quot;': '"',
    '&#039;': "'",
    '&apos;': "'",
    '&nbsp;': ' ',
    '&hellip;': '…',
    '&ldquo;': '"',
    '&rdquo;': '"',
    '&lsquo;': "'",
    '&rsquo;': "'",
    '&mdash;': '—',
    '&ndash;': '–',
  }
  return stripped
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(parseInt(code, 10)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCharCode(parseInt(code, 16)))
    .replace(/&[a-z]+;/gi, (m) => entityMap[m.toLowerCase()] ?? m)
    .replace(/\s+/g, ' ')
    .trim()
}

export function dedupePolicy(items: Document[]): Document[] {
  const seen = new Set<string>()
  const deduped: Document[] = []
  for (const item of items) {
    const matterId = (item.metadata?.matter_id as string) || (item.metadata?.record_no as string) || ''
    const stableRef = matterId || item.url || item.id
    const key = (stableRef || cleanArticleText(item.title).toLowerCase()).trim()
    if (!key || seen.has(key)) continue
    seen.add(key)
    deduped.push(item)
  }
  return deduped
}

export function dedupeNews(items: Document[]): Document[] {
  const seen = new Set<string>()
  const deduped: Document[] = []
  for (const item of items) {
    const key = ((item.url || '') + '|' + cleanArticleText(item.title).toLowerCase()).trim()
    if (!key || seen.has(key)) continue
    seen.add(key)
    deduped.push(item)
  }
  return deduped
}
