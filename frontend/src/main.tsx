import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ClerkProvider } from '@clerk/clerk-react'
import './index.css'
import App from './App.tsx'

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

function SetupRequired() {
  return (
    <div className="min-h-screen bg-[#06080d] flex items-center justify-center p-6">
      <div className="max-w-md border border-amber-500/30 bg-amber-500/5 rounded-lg p-6 text-center">
        <h1 className="text-lg font-semibold text-amber-400 mb-2">Setup required</h1>
        <p className="text-sm text-white/70 mb-4">
          Add <code className="font-mono text-amber-300/80 bg-white/5 px-1.5 py-0.5 rounded">VITE_CLERK_PUBLISHABLE_KEY</code> to <code className="font-mono text-white/50">frontend/.env</code>
        </p>
        <p className="text-xs text-white/40">
          Get a free key at{' '}
          <a href="https://clerk.com" target="_blank" rel="noreferrer" className="text-amber-400/80 hover:underline">
            clerk.com
          </a>
        </p>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      {PUBLISHABLE_KEY ? (
        <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/">
          <App />
        </ClerkProvider>
      ) : (
        <SetupRequired />
      )}
    </BrowserRouter>
  </StrictMode>,
)
