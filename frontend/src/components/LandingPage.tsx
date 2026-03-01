import { Suspense, useEffect, useState } from 'react'
import { SignedIn, SignedOut, SignInButton, SignUpButton, useUser } from '@clerk/clerk-react'
import Spline from '@splinetool/react-spline'
import BlurText from './BlurText'
import type { Application } from '@splinetool/runtime'
import CityGlobe from './CityGlobe'
import LogoLoop from './LogoLoop'
import { ActianVectorAILogo, ArizeAILogo, ModelLogo, OpenAILogo } from './SponsorLogos'

const SPONSOR_LOGO_SVGS = {
  modal: '/logo/modal-wordmark.svg',
  supermemory: '/logo/logo-fullmark.svg',
  huggingface: '/logo/hf-logo.svg',
}

interface Props {
  onGetStarted: () => void
  onViewSource?: () => void
  onViewWhyUs?: () => void
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
  { node: <OpenAILogo />, large: true, extraLarge: true },
  { node: <ModelLogo name="Qwen3-8B" />, large: true },
  { node: <HfLogoWithName name="BART-large-MNLI" />, large: true },
  { node: <ModelLogo name="RoBERTa-Sentiment" />, large: true },
  { node: <ActianVectorAILogo />, large: true },
]

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

const STATS = [
  { value: '9', label: 'Live Sources' },
  { value: '77', label: 'Neighborhoods' },
  { value: '140K+', label: 'Records Indexed' },
  { value: '< 30s', label: 'Analysis Time' },
]

const DATA_PILLARS = [
  { label: '01', title: 'Live Data Ingestion', desc: 'Real-time scraping.' },
  { label: '02', title: 'LLM Enrichment', desc: 'Sentiment, entities, geo.' },
  { label: '03', title: 'City Graph', desc: 'Continuous updates.' },
  { label: '04', title: 'Risk & Opportunity', desc: 'Quantified briefs.' },
]

const MIN_LOAD_TIME_MS = 700
const MAX_LOAD_TIME_MS = 5000

export default function LandingPage({ onGetStarted, onViewSource, onViewWhyUs }: Props) {
  const { user } = useUser()
  const [isReady, setIsReady] = useState(false)
  const [heroLoaded, setHeroLoaded] = useState(false)
  const [minTimeElapsed, setMinTimeElapsed] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setMinTimeElapsed(true), MIN_LOAD_TIME_MS)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    const t = setTimeout(() => setIsReady(true), MAX_LOAD_TIME_MS)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    if (heroLoaded && minTimeElapsed) setIsReady(true)
  }, [heroLoaded, minTimeElapsed])

  const handleHeroLoad = (app: Application) => {
    tuneScene(app)
    setHeroLoaded(true)
  }

  return (
    <div className="bg-[#06080d] text-white relative">
      {/* Loading overlay — hides content until hero + min time */}
      <div
        className={`fixed inset-0 z-[100] bg-[#06080d] flex flex-col items-center justify-center text-white transition-opacity duration-500 ${
          isReady ? 'opacity-0 pointer-events-none' : 'opacity-100'
        }`}
        aria-hidden={isReady}
      >
        <h1 className="text-4xl sm:text-6xl font-bold tracking-tight mb-6">
          ALEITHIA
        </h1>
        <div className="w-8 h-8 border-2 border-white/20 border-t-white/70 rounded-full animate-spin" />
      </div>

      {/* ── Hero ── */}
      <section className="relative min-h-screen overflow-hidden">
        <div className="absolute inset-0 z-0">
          <Spline
            scene="https://prod.spline.design/Mt-87SuFLZp8yZiy/scene.splinecode"
            onLoad={handleHeroLoad}
          />
        </div>

        <div className="absolute inset-0 z-10 bg-gradient-to-b from-[#06080d]/80 via-[#06080d]/40 to-[#06080d]/90 pointer-events-none" />

        <div className="relative z-20 min-h-screen grid grid-cols-[1fr_auto_1fr] grid-rows-[auto_1fr_auto] pointer-events-none">
          {/* HUD-style quadrant nav: top-left */}
          <div className="col-start-1 row-start-1 flex items-center px-6 lg:px-10 py-5">
            <span className="text-lg font-semibold tracking-tight text-white uppercase font-mono">
              Aleithia
            </span>
          </div>
          {/* HUD-style quadrant nav: top-right */}
          <div className="col-start-3 row-start-1 flex items-center justify-end gap-3 px-6 lg:px-10 py-5">
            <SignedOut>
              <SignInButton mode="modal">
                <button className="pointer-events-auto px-4 py-2 text-sm font-medium text-white/80 hover:text-white transition-colors cursor-pointer font-mono uppercase text-[10px] tracking-wider">
                  Sign In
                </button>
              </SignInButton>
              <SignUpButton mode="modal">
                <button className="pointer-events-auto px-6 py-2 text-sm font-medium !bg-white !text-[#06080d] hover:!bg-white/90 transition-colors cursor-pointer">
                  Get Started
                </button>
              </SignUpButton>
            </SignedOut>
            <SignedIn>
              <span className="text-xs font-mono text-white/40 mr-2">{user?.primaryEmailAddress?.emailAddress}</span>
              <button
                onClick={onGetStarted}
                className="pointer-events-auto px-6 py-2 text-sm font-medium !bg-white !text-[#06080d] hover:!bg-white/90 transition-colors cursor-pointer"
              >
                Get Started
              </button>
            </SignedIn>
          </div>

          {/* Hero: center viewport */}
          <div className="col-span-3 col-start-1 row-start-2 flex items-center justify-center px-10">
            <div className="max-w-3xl text-center">
              <BlurText
                text="Business Intelligence Platform"
                delay={80}
                animateBy="words"
                direction="top"
                className="text-xs font-mono font-medium uppercase tracking-[0.3em] text-white/40 mb-6 justify-center"
              />
              <h1 className="text-5xl sm:text-7xl font-bold tracking-tight text-white mb-8 leading-[1.05]">
                <BlurText
                  text="ALEITHIA"
                  delay={120}
                  animateBy="chars"
                  direction="top"
                  as="span"
                  className="w-full justify-center"
                />
              </h1>
              <p className="text-base sm:text-lg text-white/50 mb-12 max-w-xl mx-auto leading-relaxed">
                Live data sources,
                opportunity briefs, and neighborhood insights — before you sign
                the lease.
              </p>
              <div className="flex items-center justify-center gap-4">
                <button
                  onClick={onGetStarted}
                  className="pointer-events-auto px-8 py-3.5 text-sm font-semibold !bg-white !text-[#06080d] hover:!bg-white/90 transition-colors cursor-pointer"
                >
                  Analyze Neighborhood
                </button>
                <button
                  onClick={onViewSource}
                  className="pointer-events-auto px-8 py-3.5 text-sm font-semibold border border-white/20 text-white/70 hover:text-white hover:border-white/40 transition-colors cursor-pointer"
                >
                  Architecture
                </button>
              </div>
            </div>
          </div>

          {/* HUD bottom: scroll cue */}
          <div className="col-span-3 col-start-1 row-start-3 flex justify-center pb-8">
          <button
            type="button"
            onClick={() => document.getElementById('next')?.scrollIntoView({ behavior: 'smooth' })}
            className="pointer-events-auto absolute bottom-8 left-1/2 -translate-x-1/2 text-white/40 hover:text-white/70 transition-colors cursor-pointer"
            aria-label="Scroll to next section"
          >
            <svg
              className="w-12 h-12 animate-bounce"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M7 10l5 6 5-6H7z" />
            </svg>
          </button>
          </div>
        </div>
      </section>

      {/* ── Sponsors Ticker ── */}
      <section id="next" className="relative border-t border-white/[0.04] py-8 scroll-mt-0">
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
      <section className="relative py-20 overflow-hidden border-t border-white/[0.04] isolate" style={{ minHeight: 500 }}>
        <div className="relative z-10 max-w-7xl mx-auto px-10">
          <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-white mb-12">
            One city. Every signal.
          </h2>

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
                  className="group border-t border-white/[0.06] py-5 hover:bg-white/[0.02] transition-colors px-1"
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

        {/* Bottom fade overlay */}
        <div
          className="pointer-events-none absolute bottom-0 left-0 right-0 h-32 z-20"
          style={{
            background: 'linear-gradient(to bottom, transparent, #06080d 85%)',
          }}
          aria-hidden
        />
      </section>

      {/* ── Live Stats ── */}
      <section className="border-t border-white/[0.04] py-12">
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

      {/* ── Self-Deploying AI ── */}
      <section className="border-t border-white/[0.04] py-20">
        <div className="max-w-5xl mx-auto px-10">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            {/* Left: copy */}
            <div>
              <p className="text-xs font-mono uppercase tracking-[0.25em] text-violet-400/60 mb-4">
                Recursive Agent Architecture
              </p>
              <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-white mb-5">
                AI that deploys AI.
              </h2>
              <p className="text-base text-white/45 leading-relaxed mb-6">
                A Lead Analyst agent monitors every enriched document in real time.
                When it detects a high-impact event, it autonomously spawns 4 specialized
                worker agents — real estate, legal, economic, and community sentiment —
                each running in isolated cloud sandboxes. Workers investigate in parallel,
                return findings, and the Lead Analyst synthesizes a single impact brief.
                No human triggers any of this.
              </p>
              <div className="flex items-center gap-6 text-[10px] font-mono text-white/25 uppercase tracking-wider">
                <span>5-min scan cycle</span>
                <span className="text-white/10">|</span>
                <span>4 parallel workers</span>
                <span className="text-white/10">|</span>
                <span>E2B sandboxed</span>
              </div>
            </div>

            {/* Right: mini agent tree diagram */}
            <div className="flex justify-center">
              <div className="flex flex-col items-center gap-0">
                {/* Lead Analyst */}
                <div className="border border-violet-500/30 bg-violet-500/[0.06] px-6 py-3 text-center">
                  <span className="text-[10px] font-mono font-bold text-violet-300 uppercase tracking-wider">
                    Lead Analyst
                  </span>
                  <p className="text-[8px] font-mono text-white/20 mt-0.5">Qwen3-8B</p>
                </div>

                {/* Trunk */}
                <div className="w-px h-6 bg-violet-500/20" />

                {/* Gate */}
                <div className="border border-amber-500/20 bg-amber-500/[0.04] px-4 py-1">
                  <span className="text-[7px] font-mono uppercase tracking-wider text-amber-400/60">
                    score ≥ 7 → spawn
                  </span>
                </div>

                {/* Branch */}
                <div className="relative w-64 h-6">
                  <div className="absolute top-0 left-[10%] right-[10%] h-px bg-white/[0.08]" />
                  {[0, 1, 2, 3].map(i => (
                    <div key={i} className="absolute top-0 h-full w-px bg-white/[0.08]" style={{ left: `${10 + i * 26.67}%` }} />
                  ))}
                </div>

                {/* Workers */}
                <div className="grid grid-cols-4 gap-1.5 w-64">
                  {[
                    { label: 'Real Estate', color: 'text-cyan-400', border: 'border-cyan-500/25' },
                    { label: 'Legal', color: 'text-violet-400', border: 'border-violet-500/25' },
                    { label: 'Economic', color: 'text-amber-400', border: 'border-amber-500/25' },
                    { label: 'Community', color: 'text-emerald-400', border: 'border-emerald-500/25' },
                  ].map(w => (
                    <div key={w.label} className={`border ${w.border} bg-white/[0.02] p-1.5 text-center`}>
                      <div className={`w-1 h-1 rounded-full ${w.color.replace('text-', 'bg-')} mx-auto mb-1 animate-pulse`} />
                      <span className={`text-[7px] font-mono uppercase ${w.color}`}>{w.label}</span>
                      <p className="text-[6px] font-mono text-white/15 mt-0.5">E2B</p>
                    </div>
                  ))}
                </div>

                {/* Merge */}
                <div className="relative w-64 h-4">
                  {[0, 1, 2, 3].map(i => (
                    <div key={i} className="absolute bottom-0 h-full w-px bg-white/[0.06]" style={{ left: `${10 + i * 26.67}%` }} />
                  ))}
                  <div className="absolute bottom-0 left-[10%] right-[10%] h-px bg-white/[0.06]" />
                </div>
                <div className="w-px h-4 bg-white/[0.08]" />

                {/* Output */}
                <div className="border border-emerald-500/25 bg-emerald-500/[0.04] px-6 py-2 text-center">
                  <span className="text-[10px] font-mono font-bold text-emerald-300 uppercase tracking-wider">
                    Impact Brief
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Interactive 3D Section ── */}
      <section className="relative h-[50vh] overflow-hidden border-t border-white/[0.04]">
        <div className="absolute inset-0 scale-[1.8] -rotate-[22deg] origin-center translate-x-1/3 translate-y-[20%] pointer-events-none">
          <Spline
            scene="https://prod.spline.design/2pfbb0RwX88uLSBZ/scene.splinecode"
            onLoad={(app) => makeStatic(app)}
          />
        </div>
      </section>

      {/* ── Memory Graph (chain links) ── */}
      <section className="relative border-t border-white/[0.04]">
        <div className="px-10 py-16 max-w-7xl mx-auto text-left">
          <div className="flex items-center gap-4 mb-2">
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-white">
              Memory Graph
            </h2>
            <span className="text-sm font-mono text-white/40 italic">
              Intelligence in the links.
            </span>
          </div>
          <p className="text-sm text-white/50 mb-8 max-w-xl">
            Documents connected by semantic similarity, powered by Actian VectorAI DB with HNSW-indexed 384-dim embeddings for sub-15ms retrieval.
          </p>
          <button
            onClick={onViewSource}
            className="pointer-events-auto px-8 py-3.5 text-sm font-semibold !bg-white !text-[#06080d] hover:!bg-white/90 transition-colors cursor-pointer"
          >
            Explore Graph
          </button>
        </div>
      </section>

      {/* ── Why Us ── */}
      {onViewWhyUs && (
        <section className="border-t border-white/[0.04] py-16">
          <div className="max-w-5xl mx-auto px-10 text-center">
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-white mb-6">
              Why choose Aleithia?
            </h2>
            <p className="text-base text-white/50 mb-10 max-w-2xl mx-auto">
              Traditional market research costs thousands and takes weeks. Aleithia delivers neighborhood intelligence in seconds, for free.
            </p>
            <button
              onClick={onViewWhyUs}
              className="pointer-events-auto px-8 py-3.5 text-sm font-semibold border border-white/20 text-white/70 hover:text-white hover:border-white/40 transition-colors cursor-pointer"
            >
              Why Us?
            </button>
          </div>
        </section>
      )}

      {/* ── Footer ── */}
      <footer className="px-10 py-6 border-t border-white/[0.04]">
        <p className="text-xs font-mono text-white/20 text-center">
          HackIllinois 2026
        </p>
      </footer>
    </div>
  )
}
