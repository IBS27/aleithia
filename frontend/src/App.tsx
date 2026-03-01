import { useEffect, useState } from 'react'
import { Routes, Route, useNavigate } from 'react-router-dom'
import { useUser, useAuth } from '@clerk/clerk-react'
import type { UserProfile } from './types/index.ts'
import { api } from './api.ts'
import LandingPage from './components/LandingPage.tsx'
import OnboardingForm from './components/OnboardingForm.tsx'
import Dashboard from './components/Dashboard.tsx'
import HowItWorks from './components/HowItWorks.tsx'
import MemoryGraphPage from './components/MemoryGraphPage.tsx'
import ProfilePage from './components/ProfilePage.tsx'

function App() {
  const { isLoaded, isSignedIn, user } = useUser()
  const { getToken } = useAuth()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [savedProfile, setSavedProfile] = useState<UserProfile | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (!isLoaded || !isSignedIn || !user) return

    let cancelled = false

    const loadToken = async () => {
      try {
        const sessionToken = await getToken()
        if (!cancelled) {
          setToken(sessionToken)
        }
      } catch (error) {
        console.error('Failed to get token:', error)
      }
    }

    loadToken()

    return () => {
      cancelled = true
    }
  }, [isLoaded, isSignedIn, user, getToken])

  const handleProfileSubmit = async (p: UserProfile) => {
    setProfile(p)
    navigate('/analysis')

    if (isSignedIn && user && token) {
      try {
        await api.updateUserProfile(token, p.business_type, p.neighborhood)
        setSavedProfile(p)
      } catch {
        // Non-blocking save failure
      }
    }
  }

  if (!isLoaded) {
    return <div className="min-h-screen bg-[#06080d]" />
  }

  return (
    <Routes>
      <Route path="/how-it-works" element={<HowItWorks onBack={() => navigate('/')} />} />
      <Route path="/memory-graph" element={<MemoryGraphPage onBack={() => navigate('/')} />} />
      <Route path="/profile" element={<ProfilePage token={token} onClose={() => navigate('/')} onProfileUpdate={() => setSavedProfile(null)} />} />
      <Route
        path="/"
        element={
          <LandingPage
            onGetStarted={() => navigate('/onboarding')}
            onViewSource={() => navigate('/how-it-works')}
          />
        }
      />
      <Route
        path="/onboarding"
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
    </Routes>
  )
}

export default App
