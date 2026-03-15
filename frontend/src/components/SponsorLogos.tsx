const cls = "h-5 w-auto fill-current"

export function ModalLogo() {
  return (
    <svg className={cls} viewBox="0 0 508 120" xmlns="http://www.w3.org/2000/svg">
      <path d="M198.4 95.3V38.7l-27.1 42.1h-7.8l-27.1-42.1v56.6h-12.8V24.7h14.1l29.7 46.2 29.7-46.2h14.1v70.6h-12.8ZM252.5 96.7c-19.4 0-33.5-14-33.5-32.1 0-18.2 14.1-32.1 33.5-32.1s33.5 14 33.5 32.1c0 18.2-14.1 32.1-33.5 32.1Zm0-12.3c12 0 20.5-8.7 20.5-19.8 0-11.1-8.5-19.8-20.5-19.8s-20.5 8.7-20.5 19.8c0 11.1 8.5 19.8 20.5 19.8ZM334.4 24.7v70.6h-12.1V85c-5.5 7.5-13.8 11.7-23.5 11.7-17.6 0-31.3-14-31.3-32.1 0-18.2 13.7-32.1 31.3-32.1 9.7 0 18 4.2 23.5 11.7V24.7h12.1Zm-33.6 59.7c12 0 21.2-8.7 21.2-19.8 0-11.1-9.2-19.8-21.2-19.8-12 0-20.5 8.7-20.5 19.8 0 11.1 8.5 19.8 20.5 19.8ZM389.9 95.3V85c-5.5 7.5-13.8 11.7-23.5 11.7-17.6 0-31.3-14-31.3-32.1 0-18.2 13.7-32.1 31.3-32.1 9.7 0 18 4.2 23.5 11.7V34h12.1v61.3h-12.1Zm-21.5-10.9c12 0 21.2-8.7 21.2-19.8 0-11.1-9.2-19.8-21.2-19.8-12 0-20.5 8.7-20.5 19.8 0 11.1 8.5 19.8 20.5 19.8ZM416.3 95.3V24.7h12.8v70.6h-12.8Z" />
      <rect width="80" height="80" x="10" y="20" rx="16" />
      <path fill="#06080d" d="M35 50h10v20H35zM55 40h10v30H55z" />
    </svg>
  )
}

export function SuperMemoryLogo() {
  return (
    <svg className={cls} viewBox="0 0 200 32" xmlns="http://www.w3.org/2000/svg">
      <circle cx="16" cy="16" r="12" strokeWidth="2.5" stroke="currentColor" fill="none" />
      <circle cx="16" cy="16" r="5" />
      <path d="M16 4v4M16 24v4M4 16h4M24 16h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <text x="36" y="22" fontFamily="system-ui, sans-serif" fontWeight="600" fontSize="16" fill="currentColor">SuperMemory</text>
    </svg>
  )
}

export function ArizeAILogo() {
  return (
    <svg className={cls} viewBox="0 0 140 32" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 28L16 4l12 24H4Z" strokeWidth="2" stroke="currentColor" fill="none" />
      <path d="M10 20h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <text x="36" y="22" fontFamily="system-ui, sans-serif" fontWeight="600" fontSize="16" fill="currentColor">Arize AI</text>
    </svg>
  )
}

export function OpenAILogo() {
  return (
    <svg className={cls} viewBox="0 0 140 32" xmlns="http://www.w3.org/2000/svg">
      <text x="0" y="22" fontFamily="system-ui, sans-serif" fontWeight="600" fontSize="20" fill="currentColor">OpenAI</text>
    </svg>
  )
}

export function ModelLogo({ name }: { name: string }) {
  return (
    <svg className={cls} viewBox={`0 0 ${Math.max(120, name.length * 11 + 36)} 32`} xmlns="http://www.w3.org/2000/svg">
      <rect x="2" y="6" width="20" height="20" rx="4" strokeWidth="2" stroke="currentColor" fill="none" />
      <path d="M8 13h8M8 17h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <text x="30" y="22" fontFamily="system-ui, sans-serif" fontWeight="600" fontSize="14" fill="currentColor">{name}</text>
    </svg>
  )
}
