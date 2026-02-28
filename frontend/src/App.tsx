import { useEffect, useState } from 'react'
import './App.css'

function App() {
  const [backendStatus, setBackendStatus] = useState<string>('checking...')

  useEffect(() => {
    fetch('/api/health')
      .then((res) => res.json())
      .then((data) => setBackendStatus(data.status))
      .catch(() => setBackendStatus('unreachable'))
  }, [])

  return (
    <div className="app">
      <h1>HackIllinois 2026</h1>
      <p>Backend: <strong>{backendStatus}</strong></p>
    </div>
  )
}

export default App
