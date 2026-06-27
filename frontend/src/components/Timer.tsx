import { useState, useEffect, useRef } from 'react'

interface Props {
  running: boolean
  onComplete?: (elapsed: number) => void
}

export default function Timer({ running, onComplete }: Props) {
  const [elapsed, setElapsed] = useState(0)
  const startTimeRef = useRef<number>(0)
  const intervalRef = useRef<number>(0)

  useEffect(() => {
    if (running) {
      startTimeRef.current = performance.now()
      setElapsed(0)
      const tick = () => {
        setElapsed(performance.now() - startTimeRef.current)
      }
      tick()
      intervalRef.current = window.setInterval(tick, 100)
      return () => window.clearInterval(intervalRef.current)
    }

    if (startTimeRef.current > 0) {
      window.clearInterval(intervalRef.current)
      const finalElapsed = performance.now() - startTimeRef.current
      setElapsed(finalElapsed)
      onComplete?.(finalElapsed)
      startTimeRef.current = 0
    }
  }, [running])

  const seconds = (elapsed / 1000).toFixed(1)

  return (
    <div className={`font-mono text-lg font-bold transition-colors ${
      running ? 'text-white/60 animate-pulse' : elapsed > 0 ? 'text-green-400/80' : 'text-white/10'
    }`}>
      {seconds}s
    </div>
  )
}
