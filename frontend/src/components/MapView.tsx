import { useEffect, useRef, useState, useCallback } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { api } from '../api.ts'

type HeatmapLayer = 'regulatory' | 'business' | 'sentiment'

const LAYER_CONFIG: Record<HeatmapLayer, {
  label: string
  color: string
  property: string
  stops: [number, string][]
}> = {
regulatory: {
  label: 'Regulatory Activity',
  color: '#dc2626',
  property: 'norm_regulatory',
  stops: [
    [0, 'rgba(255,240,230,0)'],
    [10, 'rgba(255,220,200,0.15)'],
    [20, 'rgba(254,200,170,0.25)'],
    [30, 'rgba(253,170,130,0.35)'],
    [40, 'rgba(250,140,90,0.42)'],
    [50, 'rgba(240,100,60,0.5)'],
    [60, 'rgba(220,60,40,0.58)'],
    [70, 'rgba(190,35,30,0.65)'],
    [80, 'rgba(160,25,25,0.72)'],
    [90, 'rgba(130,20,20,0.78)'],
    [100, 'rgba(100,10,10,0.85)'],
  ],
},
business: {
  label: 'Commercial Activity',
  color: '#3b82f6',
  property: 'norm_business',
  stops: [
    [0, 'rgba(230,242,255,0)'],
    [10, 'rgba(200,225,255,0.15)'],
    [20, 'rgba(170,210,254,0.25)'],
    [30, 'rgba(140,190,252,0.33)'],
    [40, 'rgba(110,165,248,0.4)'],
    [50, 'rgba(80,140,240,0.48)'],
    [60, 'rgba(55,110,220,0.55)'],
    [70, 'rgba(40,85,200,0.63)'],
    [80, 'rgba(30,65,175,0.7)'],
    [90, 'rgba(22,50,150,0.78)'],
    [100, 'rgba(15,35,120,0.85)'],
  ],
},
sentiment: {
  label: 'Public Sentiment',
  color: '#22c55e',
  property: 'norm_sentiment',
  stops: [
    [0, 'rgba(255,255,200,0)'],
    [10, 'rgba(240,250,170,0.15)'],
    [20, 'rgba(220,240,140,0.25)'],
    [30, 'rgba(195,230,110,0.33)'],
    [40, 'rgba(165,215,80,0.42)'],
    [50, 'rgba(130,195,55,0.5)'],
    [60, 'rgba(95,170,40,0.58)'],
    [70, 'rgba(65,145,35,0.65)'],
    [80, 'rgba(40,120,30,0.72)'],
    [90, 'rgba(25,95,25,0.78)'],
    [100, 'rgba(10,70,20,0.85)'],
  ],
},
}
// Chicago center coordinates
const CHICAGO_CENTER: [number, number] = [-87.6298, 41.8781]
const DEFAULT_ZOOM = 11

interface Props {
  activeNeighborhood?: string
  geojsonUrl?: string
}

export default function MapView({ activeNeighborhood, geojsonUrl }: Props) {
  const mapContainerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const popupRef = useRef<mapboxgl.Popup | null>(null)
  const [activeLayer, setActiveLayer] = useState<HeatmapLayer>('regulatory')
  const [mapReady, setMapReady] = useState(false)
  const [mapError, setMapError] = useState<string | null>(null)
  const layerKeys = Object.keys(LAYER_CONFIG) as HeatmapLayer[]

  // Initialize the map
  useEffect(() => {
    if (!mapContainerRef.current) return

    const token = import.meta.env.VITE_MAPBOX_TOKEN
    if (!token) {
      setMapError('missing_token')
      return
    }

    mapboxgl.accessToken = token

    const map = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      center: CHICAGO_CENTER,
      zoom: DEFAULT_ZOOM,
      pitch: 0,
      attributionControl: false,
    })

    map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new mapboxgl.AttributionControl({ compact: true }), 'bottom-right')

    map.on('load', () => {
      setMapError(null)

      api.geo()
        .then((geojson) => {
          addSourceAndLayers(map, geojson)
        })
        .catch((error: unknown) => {
          console.error('Failed to load heatmap GeoJSON:', error)
          setMapError('Heatmap data failed to load — check backend /geo routing')
          // Fallback: empty feature collection so layers still exist
          addSourceAndLayers(map, { type: 'FeatureCollection', features: [] })
        })

      setMapReady(true)
    })

    map.on('error', (e) => {
      console.error('Mapbox error:', e)
      setMapError('Map failed to load — check your token')
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [geojsonUrl])

  // Add the GeoJSON source + all three heatmap/circle layers
function addSourceAndLayers(map: mapboxgl.Map, geojson: GeoJSON.FeatureCollection) {
  map.addSource('neighborhoods', {
      type: 'geojson',
      data: geojson,
    })

    // Find the first symbol layer in the style to insert layers before it
    const firstSymbolLayer = map.getStyle().layers?.find(l => l.type === 'symbol')?.id

    for (const [key, config] of Object.entries(LAYER_CONFIG)) {
      const layerId = `heatmap-${key}`

      // Heatmap layer
      map.addLayer({
        id: layerId,
        type: 'heatmap',
        source: 'neighborhoods',
        paint: {
          'heatmap-weight': [
            'interpolate', ['exponential', 0.5],
            ['coalesce', ['get', config.property], 0],
            0, 0.1,
            100, 1,
          ],
          'heatmap-intensity': 1.4,
          'heatmap-radius': 90,
          'heatmap-opacity': key === 'regulatory' ? 0.7 : 0,
          'heatmap-color': [
              'interpolate', ['linear'], ['heatmap-density'],
             0, 'rgba(0,0,0,0)',
              0.1, config.stops[1][1],
              0.2, config.stops[2][1],
              0.3, config.stops[3][1],
              0.4, config.stops[4][1],
              0.5, config.stops[5][1],
              0.6, config.stops[6][1],
              0.7, config.stops[7][1],
              0.8, config.stops[8][1],
              0.9, config.stops[9][1],
              1, config.stops[10][1],
            ], 
        },
      }, firstSymbolLayer)

      // Circle layer for individual points (visible at higher zoom)
      map.addLayer({
        id: `points-${key}`,
        type: 'circle',
        source: 'neighborhoods',
        minzoom: 10,
        paint: {
          'circle-radius': [
            'interpolate', ['linear'],
            ['coalesce', ['get', config.property], 0],
            0, 4,
            100, 12,
          ],
          'circle-color': config.color,
          'circle-opacity': key === 'regulatory' ? 0.85 : 0,
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 1,
          'circle-stroke-opacity': key === 'regulatory' ? 0.6 : 0,
        },
      }, firstSymbolLayer)
    }

    // Popup on hover
    map.on('mouseenter', 'points-regulatory', () => { map.getCanvas().style.cursor = 'pointer' })
    map.on('mouseleave', 'points-regulatory', () => { map.getCanvas().style.cursor = '' })

    for (const key of Object.keys(LAYER_CONFIG)) {
      map.on('click', `points-${key}`, (e) => {
        if (!e.features?.[0]) return
        const props = e.features[0].properties || {}
        const coords = (e.features[0].geometry as GeoJSON.Point).coordinates.slice() as [number, number]

        popupRef.current?.remove()
        popupRef.current = new mapboxgl.Popup({ closeButton: false, className: 'aleithia-popup' })
        .setLngLat(coords)
        .setHTML((() => {
          const na = '<span style="color:#555">N/A</span>'
          const fmt = (v: unknown, suffix = '') => {
            if (v === null || v === undefined || v === 'null' || Number(v) === 0) return na
            return `${Number(v).toFixed(1)}${suffix}`
          }
          return `
          <div style="font-family:system-ui;font-size:13px;color:#ffffff;line-height:1.6;background:#333333;padding:12px 16px;border-radius:8px;border:1px solid rgba(255,255,255,0.1)">
            <strong style="color:#818cf8;font-size:14px">${props.neighborhood || 'Unknown'}</strong>
            <div style="margin-top:6px;display:grid;grid-template-columns:auto auto;gap:2px 12px">
              <span style="color:#aaa">Active Permits</span><span>${props.active_permits && Number(props.active_permits) > 0 ? props.active_permits : na}</span>
              <span style="color:#aaa">Regulatory Score</span><span>${fmt(props.regulatory_density)}</span>
              <span style="color:#aaa">Business Activity</span><span>${fmt(props.business_activity)}</span>
              <span style="color:#aaa">Sentiment Score</span><span>${fmt(props.avg_review_rating, ' / 5')}</span>
              <span style="color:#aaa">Risk Score</span><span>${fmt(props.risk_score)}</span>
            </div>
          </div>`
        })())
          .addTo(map)
      })
    }
  }

  // Switch visible layer when activeLayer changes
  const switchLayer = useCallback((layer: HeatmapLayer) => {
    const map = mapRef.current
    if (!map || !mapReady) return

    for (const key of Object.keys(LAYER_CONFIG) as HeatmapLayer[]) {
      const visible = key === layer
      const hId = `heatmap-${key}`
      const pId = `points-${key}`

      if (map.getLayer(hId)) {
        map.setPaintProperty(hId, 'heatmap-opacity', visible ? 0.85 : 0)
      }
      if (map.getLayer(pId)) {
        map.setPaintProperty(pId, 'circle-opacity', visible ? 0.75 : 0)
        map.setPaintProperty(pId, 'circle-stroke-opacity', visible ? 0.5 : 0)
      }
    }
  }, [mapReady])

  useEffect(() => {
    switchLayer(activeLayer)
  }, [activeLayer, switchLayer])

  // Fly to active neighborhood when it changes
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady || !activeNeighborhood) return

    // Query the source to find the matching feature
    const features = map.querySourceFeatures('neighborhoods', {
      filter: ['==', ['get', 'neighborhood'], activeNeighborhood],
    })

    if (features.length > 0) {
      const coords = (features[0].geometry as GeoJSON.Point).coordinates as [number, number]
      map.flyTo({ center: coords, zoom: 13, duration: 1200 })
    }
  }, [activeNeighborhood, mapReady])

  return (
    <div className="border border-white/[0.06] bg-white/[0.01] overflow-hidden h-full flex flex-col">
      {/* Layer control row */}
      <div className="flex gap-0 border-b border-white/[0.06] bg-white/[0.008]">
        {layerKeys.map((layer, index) => {
          const isActive = activeLayer === layer
          const config = LAYER_CONFIG[layer]
          const previousLayer = layerKeys[index - 1]
          const hidesLeftDivider = index === 0 || isActive || activeLayer === previousLayer
          return (
            <button
              key={layer}
              onClick={() => setActiveLayer(layer)}
              className={`relative flex-1 flex items-center justify-center gap-2 px-3 py-2 text-[10px] font-mono uppercase tracking-wider transition-all cursor-pointer border-b-2 -mb-px border-l ${
                isActive
                  ? 'z-10 border-white/70 text-white bg-white/[0.03]'
                  : 'border-transparent text-white/30 hover:text-white/55 hover:bg-white/[0.015]'
              } ${
                hidesLeftDivider ? 'border-l-transparent' : 'border-l-white/[0.04]'
              }`}
              style={isActive ? { borderBottomColor: config.color } : undefined}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: isActive ? config.color : 'rgba(255,255,255,0.15)' }} />
              {config.label}
            </button>
          )
        })}
      </div>

      <div ref={mapContainerRef} className="flex-1 relative min-h-[300px]">
        {mapError && (
          <div className="absolute inset-0 flex items-center justify-center z-10 bg-[#06080d]/95 backdrop-blur-sm">
            {mapError === 'missing_token' ? (
              <div className="border border-white/[0.08] bg-white/[0.02] p-5 max-w-sm text-left">
                <div className="flex items-center gap-2 mb-3">
                  <span className="w-1 h-1 rounded-full bg-amber-400/70" />
                  <span className="text-[10px] font-mono uppercase tracking-[0.22em] text-amber-300/80">Map Disabled</span>
                </div>
                <p className="text-xs text-white/65 leading-relaxed mb-3">
                  Heatmap console is inactive — no Mapbox token configured.
                </p>
                <p className="text-[10px] font-mono text-white/35 mb-2">Add a token to <code className="text-white/60 bg-white/[0.05] px-1">frontend/.env</code>:</p>
                <code className="block text-[10px] font-mono text-emerald-300/70 bg-black/40 border border-white/[0.05] px-2 py-1.5 mb-3 overflow-x-auto">
                  VITE_MAPBOX_TOKEN=pk.your_token
                </code>
                <a
                  href="https://account.mapbox.com/access-tokens/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] font-mono uppercase tracking-wider text-white/40 hover:text-white/70 transition-colors"
                >
                  Get free token ›
                </a>
              </div>
            ) : (
              <div className="border border-red-500/20 bg-red-500/[0.04] p-4 max-w-sm text-center">
                <div className="text-[10px] font-mono uppercase tracking-wider text-red-300/70 mb-1">Map Error</div>
                <div className="text-xs text-white/65">{mapError}</div>
              </div>
            )}
          </div>
        )}
        {/* Layer legend */}
        {!mapError && mapReady && (
          <div className="absolute bottom-3 left-3 bg-black/70 border border-white/10 px-2.5 py-1.5 backdrop-blur-sm z-10">
            <div className="text-[9px] font-mono uppercase tracking-wider text-white/30 mb-1">Intensity</div>
            <div className="flex items-center gap-1">
              <span className="text-[9px] font-mono text-white/50">Low</span>
              <div className="w-16 h-1.5" style={{ background: `linear-gradient(to right, ${LAYER_CONFIG[activeLayer].stops[1][1]}, ${LAYER_CONFIG[activeLayer].stops[10][1]})` }} />
              <span className="text-[9px] font-mono text-white/50">High</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
const style = document.createElement('style')
style.textContent = `
  .aleithia-popup.mapboxgl-popup .mapboxgl-popup-content {
    background: transparent !important;
    padding: 0 !important;
    box-shadow: none !important;
    border: none !important;
    border-radius: 0 !important;
    margin: 0 !important;
  }
  .aleithia-popup.mapboxgl-popup .mapboxgl-popup-tip {
    border-top-color: #333333 !important;
  }
`
document.head.appendChild(style)
