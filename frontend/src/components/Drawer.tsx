import { useEffect } from 'react'

interface Props {
  open: boolean
  onClose: () => void
  children: React.ReactNode
  title?: string
  /** Slide from 'left' or 'right' */
  side?: 'left' | 'right'
  /** Width in Tailwind class e.g. w-96, max-w-md */
  width?: string
}

export default function Drawer({ open, onClose, children, title, side = 'right', width = 'w-96' }: Props) {
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  if (!open) return null

  const slideClass = side === 'right' ? 'right-0' : 'left-0'
  const translateClass = side === 'right' ? 'translate-x-0' : 'translate-x-0'

  return (
    <div className="fixed inset-0 z-50" aria-modal="true" role="dialog">
      {/* Backdrop */}
      <button
        type="button"
        onClick={onClose}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
        aria-label="Close"
      />

      {/* Panel */}
      <div
        className={`absolute top-0 bottom-0 ${slideClass} ${width} max-w-full bg-[#06080d] flex flex-col ${side === 'right' ? 'border-l-2 border-[#2B95D6]/40' : 'border-r-2 border-[#2B95D6]/40'} transform transition-transform duration-200 ease-out`}
        style={{
          boxShadow: side === 'right' ? '-4px 0 24px rgba(43, 149, 214, 0.12)' : '4px 0 24px rgba(43, 149, 214, 0.12)',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06] shrink-0">
          {title && (
            <h2 className="text-sm font-semibold text-white font-mono uppercase tracking-wider">
              {title}
            </h2>
          )}
          <button
            type="button"
            onClick={onClose}
            className="ml-auto p-2 text-white/40 hover:text-white hover:bg-white/[0.06] rounded transition-colors cursor-pointer"
            aria-label="Close"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {children}
        </div>
      </div>
    </div>
  )
}
