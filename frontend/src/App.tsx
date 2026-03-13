import { lazy, Suspense, useState } from 'react'
import { Routes, Route, useNavigate, Navigate } from 'react-router-dom'
import type { UserProfile } from './types/index.ts'
import { api } from './api.ts'
import LandingPage from './components/LandingPage.tsx'
import OnboardingForm from './components/OnboardingForm.tsx'
import Dashboard from './components/Dashboard.tsx'
import ProfilePage from './components/ProfilePage.tsx'
import Drawer from './components/Drawer.tsx'
import WhyUs from './components/WhyUs.tsx'
import LeadAnalystPage from './components/LeadAnalystPage.tsx'

// Lazy-load pages that import @supermemory/memory-graph (its CSS has a global
// button reset that conflicts with Tailwind's bg-white utility)
const HowItWorks = lazy(() => import('./components/HowItWorks.tsx'))
const MemoryGraphPage = lazy(() => import('./components/MemoryGraphPage.tsx'))

function App() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [savedProfile, setSavedProfile] = useState<UserProfile | null>(null)
  const [sessionDrawerOpen, setSessionDrawerOpen] = useState(false)
  const navigate = useNavigate()

  const handleProfileSubmit = async (p: UserProfile) => {
    setProfile(p)
    setSessionDrawerOpen(false)
    navigate('/analysis')

    try {
      await api.updateUserProfile(p.business_type, p.neighborhood)
      setSavedProfile(p)
    } catch {
      // Non-blocking save failure
    }
  }

  return (
    <Routes>
      <Route path="/how-it-works" element={<Suspense fallback={<div className="min-h-screen bg-[#06080d]" />}><HowItWorks onBack={() => navigate('/')} /></Suspense>} />
      <Route path="/why-us" element={<WhyUs onBack={() => navigate('/')} />} />
      <Route path="/lead-analyst" element={<LeadAnalystPage onBack={() => navigate('/')} />} />
      <Route path="/memory-graph" element={<Suspense fallback={<div className="min-h-screen bg-[#06080d]" />}><MemoryGraphPage onBack={() => navigate('/')} /></Suspense>} />
      <Route
        path="/profile"
        element={
          (profile ?? savedProfile) ? (
            <Dashboard
              profile={profile ?? savedProfile!}
              onReset={() => { setProfile(null); navigate('/') }}
              onProfileUpdate={() => setSavedProfile(null)}
              initialProfileDrawerOpen
            />
          ) : (
            <ProfilePage onClose={() => navigate('/')} onProfileUpdate={() => setSavedProfile(null)} />
          )
        }
      />
      <Route
        path="/"
        element={
          <>
            <LandingPage
              onGetStarted={() => setSessionDrawerOpen(true)}
              onViewSource={() => navigate('/how-it-works')}
              onViewWhyUs={() => navigate('/why-us')}
            />
            <Drawer
              open={sessionDrawerOpen}
              onClose={() => setSessionDrawerOpen(false)}
              title="Initialize Session"
              width="max-w-md"
            >
              <OnboardingForm
                onSubmit={handleProfileSubmit}
                onCancel={() => setSessionDrawerOpen(false)}
                initialProfile={savedProfile}
                embedded
              />
            </Drawer>
          </>
        }
      />
      <Route
        path="/start"
        element={
          <OnboardingForm
            onSubmit={handleProfileSubmit}
            onCancel={() => navigate('/')}
            initialProfile={savedProfile}
          />
        }
      />
      <Route
        path="/analysis"
        element={
          (profile ?? savedProfile) ? (
            <Dashboard
              profile={profile ?? savedProfile!}
              onReset={() => { setProfile(null); navigate('/') }}
              onProfileUpdate={() => setSavedProfile(null)}
            />
          ) : (
            <OnboardingForm
              onSubmit={handleProfileSubmit}
              onCancel={() => navigate('/')}
              initialProfile={savedProfile}
            />
          )
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
