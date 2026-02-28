import { useState, useEffect, useRef } from 'react'

interface Props {
  running: boolean
  onComplete?: (elapsed: number) => void
}

export default function Timer({ running, onComplete }: Props) {
  const [elapsed, setElapsed] = useState(0)
  const startTimeRef = useRef<number>(0)
  const frameRef = useRef<number>(0)

  useEffect(() => {
    if (running) {
      startTimeRef.current = performance.now()
      const tick = () => {
        const now = performance.now()
        setElapsed(now - startTimeRef.current)
        frameRef.current = requestAnimationFrame(tick)
      }
      frameRef.current = requestAnimationFrame(tick)
    } else if (elapsed > 0) {
      cancelAnimationFrame(frameRef.current)
      onComplete?.(elapsed)
    }

    return () => cancelAnimationFrame(frameRef.current)
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
