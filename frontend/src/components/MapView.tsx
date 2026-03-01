import { useEffect, useRef, useState, useCallback } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'

const API_BASE = import.meta.env.VITE_MODAL_URL || '/api/data'

type HeatmapLayer = 'regulatory' | 'business' | 'sentiment'

const LAYER_CONFIG: Record<HeatmapLayer, {
  label: string
  color: string
  property: string
  stops: [number, string][]
}> = {
regulatory: {
  label: 'Regulatory',
  color: '#dc2626',
  property: 'active_permits',
  stops: [
    [0, 'rgba(255,240,230,0)'],
    [5, 'rgba(255,220,200,0.08)'],
    [10, 'rgba(254,200,170,0.14)'],
    [15, 'rgba(253,170,130,0.2)'],
    [20, 'rgba(250,140,90,0.28)'],
    [25, 'rgba(240,100,60,0.36)'],
    [30, 'rgba(220,60,40,0.44)'],
    [35, 'rgba(190,35,30,0.52)'],
    [40, 'rgba(160,25,25,0.6)'],
    [45, 'rgba(130,20,20,0.7)'],
    [50, 'rgba(100,10,10,0.8)'],
  ],
},
business: {
  label: 'Business',
  color: '#3b82f6',
  property: 'business_activity',
  stops: [
    [0, 'rgba(230,242,255,0)'],
    [10, 'rgba(200,225,255,0.08)'],
    [20, 'rgba(170,210,254,0.14)'],
    [30, 'rgba(140,190,252,0.2)'],
    [40, 'rgba(110,165,248,0.28)'],
    [50, 'rgba(80,140,240,0.36)'],
    [60, 'rgba(55,110,220,0.44)'],
    [70, 'rgba(40,85,200,0.52)'],
    [80, 'rgba(30,65,175,0.6)'],
    [90, 'rgba(22,50,150,0.7)'],
    [100, 'rgba(15,35,120,0.8)'],
  ],
},
sentiment: {
  label: 'Sentiment',
  color: '#22c55e',
  property: 'avg_review_rating',
  stops: [
    [0, 'rgba(255,255,200,0)'],
    [0.5, 'rgba(240,250,170,0.08)'],
    [1, 'rgba(220,240,140,0.14)'],
    [1.5, 'rgba(195,230,110,0.2)'],
    [2, 'rgba(165,215,80,0.28)'],
    [2.5, 'rgba(130,195,55,0.36)'],
    [3, 'rgba(95,170,40,0.44)'],
    [3.5, 'rgba(65,145,35,0.52)'],
    [4, 'rgba(40,120,30,0.6)'],
    [4.5, 'rgba(25,95,25,0.7)'],
    [5, 'rgba(10,70,20,0.8)'],
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

  // Initialize the map
  useEffect(() => {
    if (!mapContainerRef.current) return

    const token = import.meta.env.VITE_MAPBOX_TOKEN
    if (!token) {
      setMapError('Set VITE_MAPBOX_TOKEN in your .env file')
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
      // Always fetch GeoJSON from modal volume
      const sourceUrl = `${API_BASE}/geo`
      console.log('Fetching GeoJSON from:', sourceUrl) // Debug: check URL being fetched

      // Try fetching the GeoJSON; if it fails, use an empty collection
      fetch(sourceUrl)
        .then((res) => (res.ok ? res.json() : Promise.reject(res.statusText)))
        .then((geojson) => {
          console.log('Loaded GeoJSON:', geojson) // Debug: print API response
          addSourceAndLayers(map, geojson)
        })
        .catch(() => {
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
  // Default missing sentiment to midpoint so all neighborhoods show gradient
  for (const feature of geojson.features) {
    const props = feature.properties as any
    if (!props.avg_review_rating || props.avg_review_rating === 0) {
      props.avg_review_rating = 2.5
    }
    if (!props.business_activity || props.business_activity === 0) {
      props.business_activity = 5
    }
    if (!props.active_permits || props.active_permits === 0) {
      props.active_permits = 1
    }
  }

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
            'interpolate', ['exponential',0.5],
            ['get', config.property],
            0, 0.1,
            config.stops[config.stops.length - 1][0] as number, 1,
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
            ['get', config.property],
            0, key === 'sentiment' ? 2 : 5,
            (config.stops[config.stops.length - 1][0] as number), 10,
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
        popupRef.current = new mapboxgl.Popup({ closeButton: false, className: 'alethia-popup' })
        .setLngLat(coords)
        .setHTML(`
          <div style="font-family:system-ui;font-size:13px;color:#e2e8f0;line-height:1.5;background:#1e1e2e;padding:10px 14px;border-radius:8px;border:1px solid rgba(255,255,255,0.08)">
            <strong style="color:#818cf8">${props.neighborhood || 'Unknown'}</strong><br/>
            Permits: ${props.active_permits ?? '—'}<br/>
            Reviews: ${props.review_count ?? '—'}<br/>
            Activity: ${props.business_activity ?? '—'}
          </div>
        `)
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
        {mapError && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="text-center space-y-2">
              <div className="text-red-400/60 text-sm font-mono">{mapError}</div>
              <code className="text-[10px] text-white/15 block font-mono">
                echo "VITE_MAPBOX_TOKEN=pk.your_token" &gt; .env
              </code>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
const style = document.createElement('style')
style.textContent = `
  .alethia-popup.mapboxgl-popup .mapboxgl-popup-content {
    background: transparent !important;
    padding: 0 !important;
    box-shadow: none !important;
    border: none !important;
    border-radius: 0 !important;
    margin: 0 !important;
  }
  .alethia-popup.mapboxgl-popup .mapboxgl-popup-tip {
    border-top-color: #1e1e2e !important;
  }
`
document.head.appendChild(style)