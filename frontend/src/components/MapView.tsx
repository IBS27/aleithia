import { useEffect, useRef, useState } from 'react'

type HeatmapLayer = 'regulatory' | 'business' | 'sentiment'

const LAYER_CONFIG: Record<HeatmapLayer, { label: string; color: string }> = {
  regulatory: { label: 'Regulatory', color: '#ef4444' },
  business: { label: 'Business', color: '#3b82f6' },
  sentiment: { label: 'Sentiment', color: '#22c55e' },
}

interface Props {
  activeNeighborhood?: string
}

export default function MapView({ activeNeighborhood }: Props) {
  const mapContainerRef = useRef<HTMLDivElement>(null)
  const [activeLayer, setActiveLayer] = useState<HeatmapLayer>('regulatory')
  const [mapLoaded, setMapLoaded] = useState(false)

  useEffect(() => {
    setMapLoaded(true)
  }, [])

  return (
    <div className="border border-white/[0.06] bg-white/[0.01] overflow-hidden h-full flex flex-col">
      <div className="flex gap-0 p-0 border-b border-white/[0.06]">
        {(Object.keys(LAYER_CONFIG) as HeatmapLayer[]).map((layer) => (
          <button
            key={layer}
            onClick={() => setActiveLayer(layer)}
            className={`px-4 py-2 text-[10px] font-mono uppercase tracking-wider transition-colors cursor-pointer border-b-2 -mb-px ${
              activeLayer === layer
                ? 'border-white text-white/70'
                : 'border-transparent text-white/20 hover:text-white/40'
            }`}
          >
            {LAYER_CONFIG[layer].label}
          </button>
        ))}
      </div>

      <div ref={mapContainerRef} className="flex-1 relative min-h-[300px]">
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="relative w-full h-full overflow-hidden">
            <div className="absolute inset-0 opacity-[0.04]"
              style={{
                backgroundImage: 'linear-gradient(rgba(255,255,255,0.4) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.4) 1px, transparent 1px)',
                backgroundSize: '40px 40px',
              }}
            />

            {[
              { name: 'Lincoln Park', x: 52, y: 30 },
              { name: 'Wicker Park', x: 42, y: 35 },
              { name: 'Logan Square', x: 38, y: 28 },
              { name: 'West Loop', x: 48, y: 45 },
              { name: 'Loop', x: 53, y: 48 },
              { name: 'Pilsen', x: 47, y: 58 },
              { name: 'Hyde Park', x: 60, y: 70 },
              { name: 'River North', x: 50, y: 40 },
              { name: 'Chinatown', x: 52, y: 60 },
              { name: 'Uptown', x: 55, y: 20 },
              { name: 'Rogers Park', x: 56, y: 10 },
              { name: 'Bridgeport', x: 48, y: 62 },
              { name: 'Lakeview', x: 54, y: 25 },
              { name: 'South Loop', x: 54, y: 55 },
              { name: 'Bronzeville', x: 56, y: 58 },
            ].map((dot) => (
              <div
                key={dot.name}
                className="absolute transform -translate-x-1/2 -translate-y-1/2 group"
                style={{ left: `${dot.x}%`, top: `${dot.y}%` }}
              >
                <div
                  className={`rounded-full transition-all ${
                    activeNeighborhood === dot.name
                      ? 'w-4 h-4 ring-1 ring-white/60'
                      : 'w-2 h-2'
                  }`}
                  style={{
                    backgroundColor: LAYER_CONFIG[activeLayer].color,
                    opacity: activeNeighborhood === dot.name ? 1 : 0.3 + Math.random() * 0.4,
                    boxShadow: `0 0 ${6 + Math.random() * 8}px ${LAYER_CONFIG[activeLayer].color}40`,
                  }}
                />
                <div className="absolute left-1/2 -translate-x-1/2 -top-6 bg-white/[0.06] backdrop-blur-sm text-[10px] font-mono text-white/50 px-2 py-0.5 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none border border-white/[0.06]">
                  {dot.name}
                </div>
              </div>
            ))}

            <div className="absolute bottom-3 left-3 text-[10px] font-mono text-white/15 uppercase tracking-wider">
              Chicago — {LAYER_CONFIG[activeLayer].label}
            </div>

            {mapLoaded && !mapContainerRef.current?.querySelector('canvas') && (
              <div className="absolute top-3 right-3 text-[10px] font-mono text-white/10 border border-white/[0.04] px-2 py-1">
                MAPBOX_TOKEN required for full map
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
