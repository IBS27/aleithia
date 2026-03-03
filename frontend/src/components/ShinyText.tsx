import { memo, useEffect, useId, useState, useCallback } from 'react'

export interface ShinyTextProps {
  text: string
  speed?: number
  delay?: number
  color?: string
  shineColor?: string
  spread?: number
  direction?: 'left' | 'right'
  yoyo?: boolean
  pauseOnHover?: boolean
  disabled?: boolean
  className?: string
}

function ShinyText({
  text = '',
  speed = 2,
  delay = 0,
  color = '#b5b5b5',
  shineColor = '#ffffff',
  spread = 120,
  direction = 'left',
  yoyo = false,
  pauseOnHover = false,
  disabled = false,
  className = '',
}: ShinyTextProps) {
  const id = useId().replace(/:/g, '')
  const [isPaused, setIsPaused] = useState(false)

  const duration = 1 / speed
  const gradientAngle = direction === 'left' ? 90 + spread / 2 : 90 - spread / 2
  const gradient = `linear-gradient(${gradientAngle}deg, ${color} 0%, ${color} 35%, ${shineColor} 50%, ${color} 65%, ${color} 100%)`
  const gradientSize = 300
  const cls = `shiny-${id}`

  // Inject ALL styles (including animation) as CSS so React never touches them.
  // This prevents any re-render from restarting the CSS animation.
  useEffect(() => {
    const fromPos = direction === 'left' ? `${gradientSize}%` : `-${gradientSize}%`
    const toPos = direction === 'left' ? `-${gradientSize}%` : `${gradientSize}%`

    const style = document.createElement('style')
    style.setAttribute('data-shiny', cls)
    style.textContent = `
      .${cls} {
        background: ${gradient};
        background-size: ${gradientSize * 2}% 100%;
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        -webkit-text-fill-color: transparent;
        animation: ${cls}-sweep ${duration}s linear ${delay}s infinite;
        animation-direction: ${yoyo ? 'alternate' : 'normal'};
      }
      @keyframes ${cls}-sweep {
        0%   { background-position: ${fromPos} 50%; }
        100% { background-position: ${toPos} 50%; }
      }
    `
    document.head.appendChild(style)
    return () => { style.remove() }
  }, [cls, gradient, gradientSize, direction, duration, delay, yoyo])

  const onEnter = useCallback(() => pauseOnHover && setIsPaused(true), [pauseOnHover])
  const onLeave = useCallback(() => pauseOnHover && setIsPaused(false), [pauseOnHover])

  if (disabled) {
    return <span className={className} style={{ color }}>{text}</span>
  }

  return (
    <span
      className={`inline-block ${cls} ${className}`}
      style={isPaused && pauseOnHover ? { animationPlayState: 'paused' } : undefined}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
    >
      {text}
    </span>
  )
}

export default memo(ShinyText)
