import { Suspense } from 'react'
import Spline from '@splinetool/react-spline'
import type { Application } from '@splinetool/runtime'
import CityGlobe from './CityGlobe'

interface Props {
  onGetStarted: () => void
}

function tuneScene(app: Application) {
  const a = app as Record<string, any>
  const scene = a._scene

  scene?.traverseVisibleEntity?.((entity: any) => {
    if (entity.type === 'ParticleSystem') {
      entity.data.speed *= 0.5
      entity.data.birthRatePerSec = Math.max(1, entity.data.birthRatePerSec * 0.5)
      entity.data.noiseStrength *= 0.5
    }
  })
}

const DATA_PILLARS = [
  {
    icon: '📡',
    title: 'Live Data Ingestion',
    desc: 'Reddit, Yelp, permits, transit, council meetings — scraped and normalized in real time.',
  },
  {
    icon: '🧠',
    title: 'LLM Enrichment',
    desc: 'Entity extraction, sentiment analysis, geo-tagging, and policy direction inference.',
  },
  {
    icon: '🔗',
    title: 'City Graph',
    desc: 'Entities and weighted relationships updated continuously from enriched events.',
  },
  {
    icon: '⚖️',
    title: 'Risk & Opportunity',
    desc: 'Traverses the graph to produce quantified briefs with transparent assumptions.',
  },
]

export default function LandingPage({ onGetStarted }: Props) {
  return (
    <div className="bg-gray-950 text-white">
      {/* ── Hero Section ── */}
      <section className="relative min-h-screen overflow-hidden">
        <div className="absolute inset-0 z-0">
          <Spline
            scene="https://prod.spline.design/Mt-87SuFLZp8yZiy/scene.splinecode"
            onLoad={(app) => tuneScene(app)}
          />
        </div>

        <div className="absolute inset-0 z-10 bg-gradient-to-b from-gray-950/70 via-gray-950/40 to-gray-950/80 pointer-events-none" />

        <div className="relative z-20 min-h-screen flex flex-col pointer-events-none">
          <nav className="flex items-center justify-between px-8 py-6">
            <span className="text-2xl font-bold tracking-tight text-white">
              Alethia
            </span>
            <button
              onClick={onGetStarted}
              className="pointer-events-auto px-5 py-2 text-sm font-medium rounded-full border border-white/20 text-white/90 hover:bg-white/10 backdrop-blur-sm transition-colors cursor-pointer"
            >
              Get Started
            </button>
          </nav>

          <div className="flex-1 flex items-center justify-center px-8">
            <div className="max-w-2xl text-center">
              <h1 className="text-6xl sm:text-7xl font-bold tracking-tight text-white mb-6 leading-[1.1]">
                Chicago business intelligence in{' '}
                <span className="bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">
                  seconds
                </span>
              </h1>
              <p className="text-lg sm:text-xl text-gray-300/90 mb-10 max-w-xl mx-auto leading-relaxed">
                9 live data sources fused into one city graph. Get risk scores,
                opportunity briefs, and neighborhood insights — before you sign
                the lease.
              </p>
              <div className="flex items-center justify-center gap-4">
                <button
                  onClick={onGetStarted}
                  className="pointer-events-auto px-8 py-3.5 text-base font-semibold rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-500/25 transition-colors cursor-pointer"
                >
                  Analyze a Neighborhood
                </button>
                <a
                  href="https://github.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="pointer-events-auto px-8 py-3.5 text-base font-semibold rounded-xl border border-white/15 text-white/90 hover:bg-white/10 backdrop-blur-sm transition-colors"
                >
                  View Source
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── City Graph Globe Section ── */}
      <section className="relative py-24 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-gray-950 via-indigo-950/20 to-gray-950 pointer-events-none" />

        <div className="relative z-10 max-w-7xl mx-auto px-8">
          <div className="text-center mb-12">
            <p className="text-sm font-semibold uppercase tracking-widest text-indigo-400 mb-3">
              How it works
            </p>
            <h2 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4">
              One city.{' '}
              <span className="bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">
                Every signal.
              </span>
            </h2>
            <p className="text-lg text-gray-400 max-w-2xl mx-auto">
              We fuse Chicago's digital exhaust into a living knowledge graph —
              then let you query it like talking to a local who reads everything.
            </p>
          </div>

          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <Suspense
              fallback={
                <div className="w-full h-[600px] flex items-center justify-center">
                  <div className="w-12 h-12 rounded-full border-2 border-indigo-400/30 border-t-indigo-400 animate-spin" />
                </div>
              }
            >
              <CityGlobe />
            </Suspense>

            <div className="grid sm:grid-cols-2 gap-6">
              {DATA_PILLARS.map((p) => (
                <div
                  key={p.title}
                  className="rounded-2xl border border-white/[0.06] bg-white/[0.02] backdrop-blur-sm p-6 hover:border-indigo-500/30 transition-colors"
                >
                  <span className="text-2xl mb-3 block">{p.icon}</span>
                  <h3 className="text-base font-semibold mb-1">{p.title}</h3>
                  <p className="text-sm text-gray-400 leading-relaxed">
                    {p.desc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="px-8 py-6 text-center border-t border-white/[0.06]">
        <p className="text-sm text-gray-500">
          Built at HackIllinois 2026 — Powered by Chicago Open Data, Reddit,
          Yelp, and more
        </p>
      </footer>
    </div>
  )
}
