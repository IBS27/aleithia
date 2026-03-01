import { motion } from 'framer-motion'
import { useEffect, useRef, useState, useMemo } from 'react'

function buildKeyframes(
  from: Record<string, string | number>,
  steps: Record<string, string | number>[]
): Record<string, (string | number)[]> {
  const keys = new Set([...Object.keys(from), ...steps.flatMap((s) => Object.keys(s))])
  const keyframes: Record<string, (string | number)[]> = {}
  keys.forEach((k) => {
    keyframes[k] = [from[k], ...steps.map((s) => s[k] ?? from[k])]
  })
  return keyframes
}

interface BlurTextProps {
  text?: string
  as?: 'p' | 'div' | 'span'
  delay?: number
  className?: string
  animateBy?: 'words' | 'chars'
  direction?: 'top' | 'bottom'
  threshold?: number
  rootMargin?: string
  animationFrom?: Record<string, string | number>
  animationTo?: Record<string, string | number>[]
  easing?: (t: number) => number
  onAnimationComplete?: () => void
  stepDuration?: number
}

export default function BlurText({
  text = '',
  delay = 200,
  className = '',
  animateBy = 'words',
  direction = 'top',
  threshold = 0.1,
  rootMargin = '0px',
  animationFrom,
  animationTo,
  easing = (t) => t,
  onAnimationComplete,
  stepDuration = 0.35,
  as: Component = 'p',
}: BlurTextProps) {
  const elements = animateBy === 'words' ? text.split(' ') : text.split('')
  const [inView, setInView] = useState(false)
  const ref = useRef<HTMLDivElement | HTMLSpanElement>(null)

  useEffect(() => {
    if (!ref.current) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setInView(true)
          if (ref.current) observer.unobserve(ref.current)
        }
      },
      { threshold, rootMargin }
    )
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [threshold, rootMargin])

  const defaultFrom = useMemo(
    () =>
      direction === 'top'
        ? { filter: 'blur(10px)' as const, opacity: 0, y: -50 }
        : { filter: 'blur(10px)' as const, opacity: 0, y: 50 },
    [direction]
  )

  const defaultTo = useMemo(
    () => [
      {
        filter: 'blur(5px)' as const,
        opacity: 0.5,
        y: direction === 'top' ? 5 : -5,
      },
      { filter: 'blur(0px)' as const, opacity: 1, y: 0 },
    ],
    [direction]
  )

  const fromSnapshot = animationFrom ?? defaultFrom
  const toSnapshots = animationTo ?? defaultTo

  const stepCount = toSnapshots.length + 1
  const totalDuration = stepDuration * (stepCount - 1)
  const times = Array.from({ length: stepCount }, (_, i) =>
    stepCount === 1 ? 0 : i / (stepCount - 1)
  )

  const Wrapper = Component
  return (
    <Wrapper ref={ref as React.Ref<HTMLParagraphElement>} className={className} style={{ display: 'flex', flexWrap: 'wrap' }}>
      {elements.map((segment, index) => {
        const animateKeyframes = buildKeyframes(
          fromSnapshot as Record<string, string | number>,
          toSnapshots as Record<string, string | number>[]
        )

        const spanTransition = {
          duration: totalDuration,
          times,
          delay: (index * delay) / 1000,
          ease: easing,
        }

        return (
          <motion.span
            className="inline-block will-change-[transform,filter,opacity]"
            key={index}
            initial={fromSnapshot}
            animate={inView ? animateKeyframes : fromSnapshot}
            transition={spanTransition}
            onAnimationComplete={
              index === elements.length - 1 ? onAnimationComplete : undefined
            }
          >
            {segment === ' ' ? '\u00A0' : segment}
            {animateBy === 'words' && index < elements.length - 1 && '\u00A0'}
          </motion.span>
        )
      })}
    </Wrapper>
  )
}
