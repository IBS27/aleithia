import { useEffect, useState } from 'react'
import { useUser } from '@clerk/clerk-react'
import type { UserProfile } from './types/index.ts'
import { api } from './api.ts'
import LandingPage from './components/LandingPage.tsx'
import OnboardingForm from './components/OnboardingForm.tsx'
import Dashboard from './components/Dashboard.tsx'

type View = 'landing' | 'onboarding' | 'dashboard'

function App() {
  const { isLoaded, isSignedIn, user } = useUser()
  const [view, setView] = useState<View>('landing')
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [savedProfile, setSavedProfile] = useState<UserProfile | null>(null)

  useEffect(() => {
    if (!isLoaded || !isSignedIn || !user) return

    let cancelled = false

    api.getUserSettings(user.id)
      .then((settings) => {
        if (cancelled) return
        setSavedProfile({
          business_type: settings.location_type,
          neighborhood: settings.neighborhood,
        })
      })
      .catch(() => {
        if (cancelled) return
        setSavedProfile(null)
      })

    return () => {
      cancelled = true
    }
  }, [isLoaded, isSignedIn, user])

  const handleProfileSubmit = async (p: UserProfile) => {
    setProfile(p)
    setView('dashboard')

    if (isSignedIn && user) {
      try {
        await api.saveUserSettings(user.id, p.business_type, p.neighborhood)
        setSavedProfile(p)
      } catch {
        // Non-blocking save failure
      }
    }
  }

  if (!isLoaded) {
    return <div className="min-h-screen bg-[#06080d]" />
  }

  if (view === 'landing') {
    return <LandingPage onGetStarted={() => setView('onboarding')} />
  }

  if (view === 'onboarding' || !profile) {
    return <OnboardingForm onSubmit={handleProfileSubmit} onCancel={() => setView('landing')} initialProfile={savedProfile} />
  }

  return <Dashboard profile={profile} onReset={() => { setProfile(null); setView('landing') }} />
}

export default App
