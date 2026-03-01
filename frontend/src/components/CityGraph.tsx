import { useState, useEffect, useRef, useCallback } from 'react'
import { fetchCityGraph, fetchNeighborhoodGraph, type CityGraphData, type GraphNode } from '../api.ts'

const NODE_COLORS: Record<string, string> = {
  neighborhood: '#3b82f6',
  regulation: '#ef4444',
  entity: '#f59e0b',
  business_type: '#22c55e',
}

interface Props {
  activeNeighborhood?: string
}

interface Viewport {
  x: number
  y: number
  width: number
  height: number
}

const MIN_ZOOM = 0.6
const MAX_ZOOM = 6
const ZOOM_STEP = 1.15

export default function CityGraph({ activeNeighborhood }: Props) {
  const [graphData, setGraphData] = useState<CityGraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'neighborhood' | 'full'>(activeNeighborhood ? 'neighborhood' : 'full')
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [filters, setFilters] = useState<Record<string, boolean>>({
    neighborhood: true,
    regulation: true,
    entity: true,
    business_type: true,
  })
  const [zoomLevel, setZoomLevel] = useState(1)
  const svgRef = useRef<SVGSVGElement>(null)
  const baseViewportRef = useRef<Viewport | null>(null)
  const viewportRef = useRef<Viewport | null>(null)
  const panStateRef = useRef({ active: false, lastX: 0, lastY: 0, moved: false })
  const suppressNodeClickUntilRef = useRef(0)
  const requestVersionRef = useRef(0)

  const loadGraph = useCallback(async () => {
    const requestVersion = ++requestVersionRef.current
    setLoading(true)
    setError(null)
    try {
      const data = viewMode === 'neighborhood' && activeNeighborhood
        ? await fetchNeighborhoodGraph(activeNeighborhood)
        : await fetchCityGraph()
      if (requestVersion !== requestVersionRef.current) return
      setGraphData(data)
      setSelectedNode(null)
    } catch (e) {
      if (requestVersion !== requestVersionRef.current) return
      setError(e instanceof Error ? e.message : 'Failed to load graph')
    } finally {
      if (requestVersion === requestVersionRef.current) {
        setLoading(false)
      }
    }
  }, [viewMode, activeNeighborhood])

  const applyViewport = useCallback((next: Viewport) => {
    if (!svgRef.current) return
    svgRef.current.setAttribute('viewBox', `${next.x} ${next.y} ${next.width} ${next.height}`)
    viewportRef.current = next

    const base = baseViewportRef.current
    if (base) {
      const zoom = base.width / next.width
      setZoomLevel(Number.isFinite(zoom) ? zoom : 1)
    }
  }, [])

  const resetViewport = useCallback(() => {
    const base = baseViewportRef.current
    if (!base) return
    applyViewport({ ...base })
  }, [applyViewport])

  const zoomViewport = useCallback((zoomIn: boolean, anchor?: { x: number; y: number }) => {
    const svg = svgRef.current
    const base = baseViewportRef.current
    const current = viewportRef.current
    if (!svg || !base || !current) return

    const rect = svg.getBoundingClientRect()
    if (!rect.width || !rect.height) return

    const factor = zoomIn ? 1 / ZOOM_STEP : ZOOM_STEP
    const minWidth = base.width / MAX_ZOOM
    const maxWidth = base.width / MIN_ZOOM
    const nextWidth = Math.min(maxWidth, Math.max(minWidth, current.width * factor))
    const nextHeight = current.height * (nextWidth / current.width)

    const anchorX = anchor ? anchor.x - rect.left : rect.width / 2
    const anchorY = anchor ? anchor.y - rect.top : rect.height / 2

    const nextX = current.x + (anchorX / rect.width) * (current.width - nextWidth)
    const nextY = current.y + (anchorY / rect.height) * (current.height - nextHeight)

    applyViewport({ x: nextX, y: nextY, width: nextWidth, height: nextHeight })
  }, [applyViewport])

  useEffect(() => { loadGraph() }, [loadGraph])
  useEffect(() => {
    if (!activeNeighborhood && viewMode === 'neighborhood') {
      setViewMode('full')
    }
  }, [activeNeighborhood, viewMode])

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return

    const onWheel = (event: WheelEvent) => {
      if (!baseViewportRef.current || !viewportRef.current) return
      event.preventDefault()
      zoomViewport(event.deltaY < 0, { x: event.clientX, y: event.clientY })
    }

    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0 || !viewportRef.current) return
      const target = event.target
      if (target instanceof Element && target.closest('g[data-city-graph-node="true"]')) return

      panStateRef.current = { active: true, lastX: event.clientX, lastY: event.clientY, moved: false }
      svg.style.cursor = 'grabbing'
      svg.setPointerCapture(event.pointerId)
    }

    const onPointerMove = (event: PointerEvent) => {
      if (!panStateRef.current.active || !viewportRef.current) return
      const rect = svg.getBoundingClientRect()
      if (!rect.width || !rect.height) return

      const dx = event.clientX - panStateRef.current.lastX
      const dy = event.clientY - panStateRef.current.lastY
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) {
        panStateRef.current.moved = true
      }

      const current = viewportRef.current
      if (!current) return
      const next = {
        ...current,
        x: current.x - (dx / rect.width) * current.width,
        y: current.y - (dy / rect.height) * current.height,
      }

      applyViewport(next)
      panStateRef.current.lastX = event.clientX
      panStateRef.current.lastY = event.clientY
    }

    const onPointerUp = (event: PointerEvent) => {
      if (!panStateRef.current.active) return
      if (panStateRef.current.moved) {
        suppressNodeClickUntilRef.current = Date.now() + 120
      }
      panStateRef.current.active = false
      if (svg.hasPointerCapture(event.pointerId)) {
        svg.releasePointerCapture(event.pointerId)
      }
      svg.style.cursor = 'grab'
    }

    svg.addEventListener('wheel', onWheel, { passive: false })
    svg.addEventListener('pointerdown', onPointerDown)
    svg.addEventListener('pointermove', onPointerMove)
    svg.addEventListener('pointerup', onPointerUp)
    svg.addEventListener('pointercancel', onPointerUp)

    return () => {
      svg.removeEventListener('wheel', onWheel)
      svg.removeEventListener('pointerdown', onPointerDown)
      svg.removeEventListener('pointermove', onPointerMove)
      svg.removeEventListener('pointerup', onPointerUp)
      svg.removeEventListener('pointercancel', onPointerUp)
    }
  }, [applyViewport, zoomViewport])

  // Run force simulation and render to SVG
  useEffect(() => {
    if (!graphData || !svgRef.current) return

    const svg = svgRef.current
    const width = svg.clientWidth || 800
    const height = svg.clientHeight || 500

    const filteredNodes = graphData.nodes.filter(n => filters[n.type])
    const filteredNodeIds = new Set(filteredNodes.map(n => n.id))
    const filteredEdges = graphData.edges.filter(e =>
      filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target)
    )

    // Initialize positions in a circle
    const positions = new Map<string, { x: number; y: number; vx: number; vy: number }>()
    filteredNodes.forEach((n, i) => {
      const angle = (2 * Math.PI * i) / filteredNodes.length
      const r = Math.min(width, height) * 0.35
      positions.set(n.id, {
        x: width / 2 + r * Math.cos(angle) + (Math.random() - 0.5) * 50,
        y: height / 2 + r * Math.sin(angle) + (Math.random() - 0.5) * 50,
        vx: 0, vy: 0,
      })
    })

    // Run 80 iterations of force simulation
    for (let iter = 0; iter < 80; iter++) {
      const alpha = 0.3 * (1 - iter / 80)

      // Repulsion between all nodes
      const nodeList = Array.from(positions.entries())
      for (let i = 0; i < nodeList.length; i++) {
        for (let j = i + 1; j < nodeList.length; j++) {
          const a = nodeList[i][1]
          const b = nodeList[j][1]
          const dx = b.x - a.x
          const dy = b.y - a.y
          const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy))
          const force = 800 / (dist * dist)
          const fx = (dx / dist) * force * alpha
          const fy = (dy / dist) * force * alpha
          a.vx -= fx
          a.vy -= fy
          b.vx += fx
          b.vy += fy
        }
      }

      // Attraction along edges
      for (const edge of filteredEdges) {
        const a = positions.get(edge.source)
        const b = positions.get(edge.target)
        if (!a || !b) continue
        const dx = b.x - a.x
        const dy = b.y - a.y
        const force = 0.005 * edge.weight
        a.vx += dx * force
        a.vy += dy * force
        b.vx -= dx * force
        b.vy -= dy * force
      }

      // Center gravity + apply velocity
      for (const [, pos] of positions) {
        pos.vx += (width / 2 - pos.x) * 0.01
        pos.vy += (height / 2 - pos.y) * 0.01
        pos.vx *= 0.6
        pos.vy *= 0.6
        pos.x += pos.vx
        pos.y += pos.vy
        pos.x = Math.max(30, Math.min(width - 30, pos.x))
        pos.y = Math.max(30, Math.min(height - 30, pos.y))
      }
    }

    // Render to SVG
    while (svg.firstChild) svg.removeChild(svg.firstChild)
    const viewportLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g')
    svg.appendChild(viewportLayer)

    // Draw edges
    for (const edge of filteredEdges) {
      const a = positions.get(edge.source)
      const b = positions.get(edge.target)
      if (!a || !b) continue
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line')
      line.setAttribute('x1', String(a.x))
      line.setAttribute('y1', String(a.y))
      line.setAttribute('x2', String(b.x))
      line.setAttribute('y2', String(b.y))
      line.setAttribute('stroke', 'rgba(255,255,255,0.08)')
      line.setAttribute('stroke-width', String(Math.max(0.5, edge.weight * 2)))
      viewportLayer.appendChild(line)
    }

    // Draw nodes
    for (const node of filteredNodes) {
      const pos = positions.get(node.id)
      if (!pos) continue

      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g')
      g.setAttribute('transform', `translate(${pos.x},${pos.y})`)
      g.setAttribute('data-city-graph-node', 'true')
      g.style.cursor = 'pointer'
      g.addEventListener('click', () => {
        if (Date.now() < suppressNodeClickUntilRef.current) return
        setSelectedNode(node)
      })

      const isActive = activeNeighborhood && node.id === `nb:${activeNeighborhood}`
      const radius = Math.max(4, (node.size || 10) / 4)

      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
      circle.setAttribute('r', String(radius))
      circle.setAttribute('fill', NODE_COLORS[node.type] || '#666')
      circle.setAttribute('opacity', isActive ? '1' : '0.7')
      if (isActive) {
        circle.setAttribute('stroke', '#fff')
        circle.setAttribute('stroke-width', '2')
      }
      g.appendChild(circle)

      // Label for neighborhood nodes and larger nodes
      if (node.size >= 20 || node.type === 'neighborhood') {
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text')
        text.textContent = node.label.length > 15 ? node.label.slice(0, 15) + '\u2026' : node.label
        text.setAttribute('x', String(radius + 4))
        text.setAttribute('y', '3')
        text.setAttribute('fill', 'rgba(255,255,255,0.4)')
        text.setAttribute('font-size', '9')
        text.setAttribute('font-family', 'monospace')
        g.appendChild(text)
      }

      viewportLayer.appendChild(g)
    }

    const defaultViewport = { x: 0, y: 0, width, height }
    baseViewportRef.current = defaultViewport
    applyViewport(defaultViewport)
  }, [graphData, filters, activeNeighborhood, applyViewport])

  return (
    <div className="border border-white/[0.06] bg-white/[0.01]">
      <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
        <h3 className="text-[10px] font-mono uppercase tracking-wider text-white/40">Knowledge Graph</h3>
        <div className="flex items-center gap-3">
          <div className="flex gap-0 border border-white/[0.08] rounded overflow-hidden">
            {(['neighborhood', 'full'] as const).map((mode) => {
              const disabled = mode === 'neighborhood' && !activeNeighborhood
              return (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setViewMode(mode)}
                  disabled={disabled}
                  className={`px-3 py-1 text-[10px] font-mono uppercase tracking-wider transition-colors ${
                    viewMode === mode
                      ? 'bg-white/[0.06] text-white'
                      : disabled
                        ? 'text-white/15 cursor-not-allowed'
                        : 'text-white/30 hover:text-white/50 cursor-pointer'
                  }`}
                >
                  {mode === 'neighborhood' ? '1-Hop' : 'Full'}
                </button>
              )
            })}
          </div>
          {graphData?.stats && (
            <span className="text-[10px] font-mono text-white/20">
              {graphData.stats.total_nodes} nodes &middot; {graphData.stats.total_edges} edges
            </span>
          )}
        </div>
      </div>

      {/* Filter checkboxes */}
      <div className="px-4 py-2 border-b border-white/[0.04] flex items-center gap-4">
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <label key={type} className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={filters[type] ?? true}
              onChange={e => setFilters(prev => ({ ...prev, [type]: e.target.checked }))}
              className="sr-only"
            />
            <span
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: color, opacity: filters[type] ? 1 : 0.2 }}
            />
            <span className={`text-[10px] font-mono ${filters[type] ? 'text-white/40' : 'text-white/15'}`}>
              {type.replace('_', ' ')}
            </span>
          </label>
        ))}
      </div>

      {/* Graph canvas */}
      <div className="relative" style={{ height: 500 }}>
        <div className="absolute top-3 right-3 z-10 flex items-center gap-2 pointer-events-none">
          <span className="hidden sm:inline text-[10px] font-mono text-white/25">
            scroll zoom · drag pan
          </span>
          <div className="flex items-center gap-1 pointer-events-auto">
            <button
              type="button"
              onClick={() => zoomViewport(false)}
              className="w-6 h-6 border border-white/[0.12] bg-[#06080d]/90 text-white/60 hover:text-white hover:border-white/35 transition-colors cursor-pointer"
              aria-label="Zoom out"
              disabled={!graphData || loading}
            >
              -
            </button>
            <button
              type="button"
              onClick={() => zoomViewport(true)}
              className="w-6 h-6 border border-white/[0.12] bg-[#06080d]/90 text-white/60 hover:text-white hover:border-white/35 transition-colors cursor-pointer"
              aria-label="Zoom in"
              disabled={!graphData || loading}
            >
              +
            </button>
            <button
              type="button"
              onClick={resetViewport}
              className="px-2 h-6 border border-white/[0.12] bg-[#06080d]/90 text-[10px] font-mono text-white/50 hover:text-white hover:border-white/35 transition-colors cursor-pointer"
              disabled={!graphData || loading}
            >
              reset
            </button>
            <span className="text-[10px] font-mono text-white/25 min-w-[40px] text-right">
              {zoomLevel.toFixed(1)}x
            </span>
          </div>
        </div>
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-5 h-5 border border-white/20 border-t-white/60 rounded-full animate-spin" />
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-red-400/60 font-mono">
            {error}
          </div>
        )}
        {!loading && graphData && graphData.nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-white/20 font-mono">
            No graph data &mdash; run <code className="text-white/30">modal run -m modal_app.graph::build_city_graph</code>
          </div>
        )}
        <svg ref={svgRef} width="100%" height="100%" className="bg-transparent touch-none cursor-grab" />
      </div>

      {/* Selected node panel */}
      {selectedNode && (
        <div className="px-4 py-3 border-t border-white/[0.06] bg-white/[0.02]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: NODE_COLORS[selectedNode.type] }}
              />
              <span className="text-xs font-medium text-white/70">{selectedNode.label}</span>
              <span className="text-[10px] font-mono text-white/20 border border-white/[0.08] px-1.5 py-0.5">
                {selectedNode.type.replace('_', ' ')}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setSelectedNode(null)}
              className="text-white/20 hover:text-white/50 text-xs cursor-pointer"
            >
              &times;
            </button>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-4 text-[10px] font-mono">
            <div>
              <span className="text-white/20">ID</span>
              <div className="text-white/40 mt-0.5">{selectedNode.id}</div>
            </div>
            <div>
              <span className="text-white/20">Size</span>
              <div className="text-white/40 mt-0.5">{selectedNode.size}</div>
            </div>
            {selectedNode.sentiment !== undefined && (
              <div>
                <span className="text-white/20">Sentiment</span>
                <div className={`mt-0.5 ${selectedNode.sentiment > 0 ? 'text-emerald-400/60' : selectedNode.sentiment < 0 ? 'text-red-400/60' : 'text-white/40'}`}>
                  {selectedNode.sentiment.toFixed(2)}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
