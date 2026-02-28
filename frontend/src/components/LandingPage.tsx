import { Suspense } from 'react'
import Spline from '@splinetool/react-spline'
import type { Application } from '@splinetool/runtime'
import CityGlobe from './CityGlobe'
import LogoLoop from './LogoLoop'
import { ArizeAILogo, ModelLogo } from './SponsorLogos'
import hfLogo from '../assets/logos/hf-logo.svg?url'

const SPONSOR_LOGO_SVGS = {
  modal: '/logo/modal-wordmark.svg',
  supermemory: '/logo/logo-fullmark.svg',
  chatgpt: '/logo/chatgpt.jpg',
  huggingface: hfLogo,
}

interface Props {
  onGetStarted: () => void
}

function makeStatic(app: Application) {
  const a = app as Record<string, any>
  a._eventManager?.deactivate()
  app.canvas.style.pointerEvents = 'none'
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

const logoImg = (src: string, alt: string, invert?: boolean) => (
  <img
    src={src}
    alt={alt}
    className={`w-auto object-contain ${invert ? 'invert' : ''}`}
  />
)

const HfLogoWithName = ({ name }: { name: string }) => (
  <span className="flex items-center gap-4 h-14">
    <img
      src={SPONSOR_LOGO_SVGS.huggingface}
      alt="Hugging Face"
      className="h-14 w-auto object-contain shrink-0"
      style={{ filter: 'grayscale(1) brightness(0) invert(1)' }}
    />
    <span className="font-semibold text-[1.25rem] whitespace-nowrap leading-none">{name}</span>
  </span>
)

const SPONSOR_LOGOS = [
  { node: logoImg(SPONSOR_LOGO_SVGS.modal, 'Modal'), large: false },
  { node: logoImg(SPONSOR_LOGO_SVGS.supermemory, 'SuperMemory'), large: false },
  { node: <ArizeAILogo />, large: true },
  { node: logoImg(SPONSOR_LOGO_SVGS.chatgpt, 'ChatGPT', true), large: true, extraLarge: true },
  { node: <ModelLogo name="Qwen3-8B" />, large: true },
  { node: <HfLogoWithName name="BART-large-MNLI" />, large: true },
  { node: <ModelLogo name="RoBERTa-Sentiment" />, large: true },
]

const STATS = [
  { value: '9', label: 'Live Sources' },
  { value: '77', label: 'Neighborhoods' },
  { value: '140K+', label: 'Records Indexed' },
  { value: '< 30s', label: 'Analysis Time' },
]

const DATA_PILLARS = [
  {
    label: '01',
    title: 'Live Data Ingestion',
    desc: 'Reddit, Yelp, permits, transit, council meetings — scraped and normalized in real time.',
  },
  {
    label: '02',
    title: 'LLM Enrichment',
    desc: 'Entity extraction, sentiment analysis, geo-tagging, and policy direction inference.',
  },
  {
    label: '03',
    title: 'City Graph',
    desc: 'Entities and weighted relationships updated continuously from enriched events.',
  },
  {
    label: '04',
    title: 'Risk & Opportunity',
    desc: 'Traverses the graph to produce quantified briefs with transparent assumptions.',
  },
]

export default function LandingPage({ onGetStarted }: Props) {
  return (
    <div className="bg-[#06080d] text-white">
      {/* ── Hero ── */}
      <section className="relative min-h-screen overflow-hidden">
        <div className="absolute inset-0 z-0">
          <Spline
            scene="https://prod.spline.design/Mt-87SuFLZp8yZiy/scene.splinecode"
            onLoad={(app) => tuneScene(app)}
          />
        </div>

        <div className="absolute inset-0 z-10 bg-gradient-to-b from-[#06080d]/80 via-[#06080d]/40 to-[#06080d]/90 pointer-events-none" />

        <div className="relative z-20 min-h-screen flex flex-col pointer-events-none">
          {/* Translucent nav */}
          <nav className="flex items-center justify-between px-10 py-5 bg-white/[0.03] backdrop-blur-md border-b border-white/[0.06]">
            <span className="text-lg font-semibold tracking-tight text-white uppercase">
              Alethia
            </span>
            <button
              onClick={onGetStarted}
              className="pointer-events-auto px-6 py-2 text-sm font-medium bg-white text-[#06080d] hover:bg-gray-200 transition-colors cursor-pointer"
            >
              Get Started
            </button>
          </nav>

          <div className="flex-1 flex items-center justify-center px-10">
            <div className="max-w-3xl text-center">
              <p className="text-xs font-mono font-medium uppercase tracking-[0.3em] text-white/40 mb-6">
                Chicago Business Intelligence Platform
              </p>
              <h1 className="text-5xl sm:text-7xl font-bold tracking-tight text-white mb-8 leading-[1.05]">
                Infrastructure-grade
                <br />
                market intelligence.
              </h1>
              <p className="text-base sm:text-lg text-white/50 mb-12 max-w-xl mx-auto leading-relaxed">
                9 live data sources fused into one city graph. Risk scores,
                opportunity briefs, and neighborhood insights — before you sign
                the lease.
              </p>
              <div className="flex items-center justify-center gap-4">
                <button
                  onClick={onGetStarted}
                  className="pointer-events-auto px-8 py-3.5 text-sm font-semibold bg-white text-[#06080d] hover:bg-gray-200 transition-colors cursor-pointer"
                >
                  Analyze a Neighborhood
                </button>
                <a
                  href="https://github.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="pointer-events-auto px-8 py-3.5 text-sm font-semibold border border-white/20 text-white/70 hover:text-white hover:border-white/40 transition-colors"
                >
                  View Source
                </a>
              </div>
            </div>
          </div>

          {/* Floating scroll arrow */}
          <button
            type="button"
            onClick={() => document.getElementById('next')?.scrollIntoView({ behavior: 'smooth' })}
            className="pointer-events-auto absolute bottom-8 left-1/2 -translate-x-1/2 text-white/40 hover:text-white/70 transition-colors cursor-pointer"
            aria-label="Scroll to next section"
          >
            <svg
              className="w-6 h-6 animate-bounce"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M7 10l5 6 5-6H7z" />
            </svg>
          </button>
        </div>
      </section>

      {/* ── Sponsors Ticker ── */}
      <section id="next" className="relative border-t border-white/[0.04] py-10 scroll-mt-0">
        <p className="text-center text-[10px] font-mono uppercase tracking-[0.3em] text-white/20 mb-6">
          Made possible with
        </p>
        <LogoLoop
          logos={SPONSOR_LOGOS.map((s) => {
            const sizeClass = (s as { extraLarge?: boolean }).extraLarge
              ? '[&_img]:h-20 [&_svg]:h-20'
              : s.large
                ? '[&_img]:h-14 [&_svg]:h-14'
                : '[&_img]:h-7 [&_svg]:h-7'
            return {
              node: (
                <span
                  className={`flex items-center px-4 py-2 text-white/30 hover:text-white/60 transition-colors [&_img]:opacity-70 [&:hover_img]:opacity-100 [&_img]:w-auto [&_img]:object-contain [&_svg]:w-auto [&_svg]:shrink-0 ${sizeClass}`}
                >
                  {s.node}
                </span>
              ),
            }
          })}
          speed={40}
          gap={120}
          logoHeight={80}
          pauseOnHover
          fadeOut
          fadeOutColor="#06080d"
        />
      </section>

      {/* ── City Graph Globe ── */}
      <section className="relative py-28 overflow-hidden border-t border-white/[0.04]">
        <div className="relative z-10 max-w-7xl mx-auto px-10">
          <div className="mb-16">
            <p className="text-xs font-mono font-medium uppercase tracking-[0.3em] text-white/30 mb-4">
              How it works
            </p>
            <h2 className="text-4xl sm:text-5xl font-bold tracking-tight text-white leading-[1.1]">
              One city.<br />
              Every signal.
            </h2>
          </div>

          <div className="grid lg:grid-cols-2 gap-16 items-center">
            <Suspense
              fallback={
                <div className="w-full h-[600px] flex items-center justify-center">
                  <div className="w-8 h-8 border border-white/20 border-t-white/60 rounded-full animate-spin" />
                </div>
              }
            >
              <CityGlobe />
            </Suspense>

            <div className="space-y-0">
              {DATA_PILLARS.map((p) => (
                <div
                  key={p.title}
                  className="group border-t border-white/[0.06] py-7 hover:bg-white/[0.02] transition-colors px-1"
                >
                  <div className="flex items-start gap-6">
                    <span className="text-xs font-mono text-white/20 pt-0.5 shrink-0">
                      {p.label}
                    </span>
                    <div>
                      <h3 className="text-base font-semibold text-white/90 mb-1.5 group-hover:text-white transition-colors">
                        {p.title}
                      </h3>
                      <p className="text-sm text-white/35 leading-relaxed">
                        {p.desc}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
              <div className="border-t border-white/[0.06]" />
            </div>
          </div>
        </div>
      </section>

      {/* ── Live Stats ── */}
      <section className="border-t border-white/[0.04] py-16">
        <div className="max-w-5xl mx-auto px-10 grid grid-cols-2 sm:grid-cols-4 gap-8">
          {STATS.map((s) => (
            <div key={s.label} className="text-center">
              <p className="text-3xl sm:text-4xl font-bold tracking-tight text-white mb-1">
                {s.value}
              </p>
              <p className="text-xs font-mono text-white/30 uppercase tracking-wider">
                {s.label}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Interactive 3D Section ── */}
      <section className="relative h-screen overflow-hidden border-t border-white/[0.04]">
        <div className="absolute inset-0 scale-[2] origin-center pointer-events-none">
          <Spline
            scene="https://prod.spline.design/2pfbb0RwX88uLSBZ/scene.splinecode"
            onLoad={(app) => makeStatic(app)}
          />
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="px-10 py-8 border-t border-white/[0.04]">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <p className="text-xs font-mono text-white/20">
            Built at HackIllinois 2026
          </p>
          <p className="text-xs font-mono text-white/20">
            Chicago Open Data / Reddit / Yelp / Legistar
          </p>
        </div>
      </footer>
    </div>
  )
}
