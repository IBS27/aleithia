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

export default function CityGraph({ activeNeighborhood }: Props) {
  const [graphData, setGraphData] = useState<CityGraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'neighborhood' | 'full'>('neighborhood')
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [filters, setFilters] = useState<Record<string, boolean>>({
    neighborhood: true,
    regulation: true,
    entity: true,
    business_type: true,
  })
  const svgRef = useRef<SVGSVGElement>(null)

  const loadGraph = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = viewMode === 'neighborhood' && activeNeighborhood
        ? await fetchNeighborhoodGraph(activeNeighborhood)
        : await fetchCityGraph()
      setGraphData(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load graph')
    } finally {
      setLoading(false)
    }
  }, [viewMode, activeNeighborhood])

  useEffect(() => { loadGraph() }, [loadGraph])

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
      svg.appendChild(line)
    }

    // Draw nodes
    for (const node of filteredNodes) {
      const pos = positions.get(node.id)
      if (!pos) continue

      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g')
      g.setAttribute('transform', `translate(${pos.x},${pos.y})`)
      g.style.cursor = 'pointer'
      g.addEventListener('click', () => setSelectedNode(node))

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

      svg.appendChild(g)
    }
  }, [graphData, filters, activeNeighborhood])

  return (
    <div className="border border-white/[0.06] bg-white/[0.01]">
      <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
        <h3 className="text-[10px] font-mono uppercase tracking-wider text-white/40">Knowledge Graph</h3>
        <div className="flex items-center gap-3">
          <div className="flex gap-0 border border-white/[0.08] rounded overflow-hidden">
            {(['neighborhood', 'full'] as const).map(mode => (
              <button
                key={mode}
                type="button"
                onClick={() => setViewMode(mode)}
                className={`px-3 py-1 text-[10px] font-mono uppercase tracking-wider transition-colors cursor-pointer ${
                  viewMode === mode
                    ? 'bg-white/[0.06] text-white'
                    : 'text-white/30 hover:text-white/50'
                }`}
              >
                {mode === 'neighborhood' ? '1-Hop' : 'Full'}
              </button>
            ))}
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
        <svg ref={svgRef} width="100%" height="100%" className="bg-transparent" />
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
