interface Props {
  sources: { name: string; count: number; active: boolean }[]
}

export default function DataSourceBadge({ sources }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      {sources.map((s) => (
        <div
          key={s.name}
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[10px] font-mono uppercase tracking-wider border ${
            s.active
              ? 'text-green-400/60 border-green-500/15'
              : 'text-white/15 border-white/[0.06]'
          }`}
        >
          <span className={`w-1 h-1 rounded-full ${s.active ? 'bg-green-400/60' : 'bg-white/10'}`} />
          {s.name}
          {s.count > 0 && <span className="text-white/15">{s.count}</span>}
        </div>
      ))}
    </div>
  )
}
