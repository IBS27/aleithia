import { useState } from 'react'
import type { CCTVData } from '../types/index.ts'
import { api } from '../api.ts'

interface Props {
  cctv: CCTVData
}

export default function CCTVFeedCard({ cctv }: Props) {
  const [selected, setSelected] = useState<string | null>(null)

  if (!cctv.cameras.length) return null

  const cameras = cctv.cameras.slice(0, 4)
  const selectedCamera = selected ? cameras.find(c => c.camera_id === selected) : null

  return (
    <div className="border border-white/[0.06] bg-white/[0.02]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
          <span className="text-[10px] font-mono uppercase tracking-wider text-white/40">
            CCTV Feeds — Live Detection
          </span>
        </div>
        <span className="text-[10px] font-mono text-white/20">
          {cctv.cameras.length} camera{cctv.cameras.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Camera grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-white/[0.04]">
        {cameras.map(cam => {
          const isSelected = selected === cam.camera_id
          return (
            <button
              key={cam.camera_id}
              type="button"
              onClick={() => setSelected(isSelected ? null : cam.camera_id)}
              className={`relative bg-[#06080d] p-0 cursor-pointer transition-all ${
                isSelected ? 'ring-1 ring-white/30' : 'hover:ring-1 hover:ring-white/10'
              }`}
            >
              {/* Frame image */}
              <div className="relative aspect-video bg-black/40 overflow-hidden">
                <img
                  src={api.cctvFrameUrl(cam.camera_id)}
                  alt={`Camera ${cam.camera_id}`}
                  className="w-full h-full object-cover"
                  loading="lazy"
                  onError={e => {
                    const target = e.currentTarget
                    target.style.display = 'none'
                    const parent = target.parentElement
                    if (parent && !parent.querySelector('.fallback')) {
                      const fb = document.createElement('div')
                      fb.className = 'fallback absolute inset-0 flex items-center justify-center'
                      fb.innerHTML = '<span class="text-[10px] font-mono text-white/15">NO SIGNAL</span>'
                      parent.appendChild(fb)
                    }
                  }}
                />

                {/* Detection count badges */}
                <div className="absolute top-1.5 right-1.5 flex gap-1">
                  <span className="px-1.5 py-0.5 text-[9px] font-mono font-bold bg-green-500/80 text-white rounded-sm">
                    P:{cam.pedestrians}
                  </span>
                  <span className="px-1.5 py-0.5 text-[9px] font-mono font-bold bg-blue-500/80 text-white rounded-sm">
                    V:{cam.vehicles}
                  </span>
                </div>
              </div>

              {/* Camera info */}
              <div className="px-2 py-1.5 text-left">
                <div className="text-[10px] font-mono text-white/50 truncate">{cam.camera_id}</div>
                <div className="flex items-center justify-between mt-0.5">
                  <span className="text-[9px] font-mono text-white/20">{cam.distance_km.toFixed(1)}km</span>
                  <span className={`text-[9px] font-mono ${
                    cam.density_level === 'high' ? 'text-green-400/60' :
                    cam.density_level === 'medium' ? 'text-yellow-400/60' :
                    'text-white/20'
                  }`}>
                    {cam.density_level}
                  </span>
                </div>
              </div>
            </button>
          )
        })}
      </div>

      {/* Expanded view */}
      {selectedCamera && (
        <div className="border-t border-white/[0.06] p-4">
          <div className="flex gap-4">
            <div className="flex-1 aspect-video bg-black/40 overflow-hidden relative">
              <img
                src={api.cctvFrameUrl(selectedCamera.camera_id)}
                alt={`Camera ${selectedCamera.camera_id} — expanded`}
                className="w-full h-full object-contain"
              />
              <div className="absolute top-2 right-2 flex gap-1.5">
                <span className="px-2 py-1 text-[10px] font-mono font-bold bg-green-500/80 text-white rounded-sm">
                  P:{selectedCamera.pedestrians}
                </span>
                <span className="px-2 py-1 text-[10px] font-mono font-bold bg-blue-500/80 text-white rounded-sm">
                  V:{selectedCamera.vehicles}
                </span>
                {selectedCamera.bicycles > 0 && (
                  <span className="px-2 py-1 text-[10px] font-mono font-bold bg-amber-500/80 text-white rounded-sm">
                    B:{selectedCamera.bicycles}
                  </span>
                )}
              </div>
            </div>
            <div className="w-48 space-y-3">
              <div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-white/20 mb-1">Camera</div>
                <div className="text-xs font-mono text-white/60">{selectedCamera.camera_id}</div>
              </div>
              <div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-white/20 mb-1">Distance</div>
                <div className="text-xs font-mono text-white/60">{selectedCamera.distance_km.toFixed(1)} km</div>
              </div>
              <div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-white/20 mb-1">Density</div>
                <div className={`text-xs font-mono ${
                  selectedCamera.density_level === 'high' ? 'text-green-400' :
                  selectedCamera.density_level === 'medium' ? 'text-yellow-400' :
                  'text-white/40'
                }`}>
                  {selectedCamera.density_level}
                </div>
              </div>
              <div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-white/20 mb-1">Timestamp</div>
                <div className="text-[10px] font-mono text-white/40">
                  {new Date(selectedCamera.timestamp).toLocaleString()}
                </div>
              </div>
              <div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-white/20 mb-1">Coordinates</div>
                <div className="text-[10px] font-mono text-white/30">
                  {selectedCamera.lat.toFixed(4)}, {selectedCamera.lng.toFixed(4)}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
