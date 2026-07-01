type AnalysisNotificationWorkflow = 'analysis' | 'social-trends'
type AnalysisNotificationStatus = 'success' | 'error'

interface AnalysisNotificationOptions {
  workflow: AnalysisNotificationWorkflow
  status: AnalysisNotificationStatus
  neighborhood: string
  businessType?: string
  detail?: string
}

const APP_NAME = 'Aleithia'
const LOGO_PATH = 'favicon.svg'
const DEDUPE_WINDOW_MS = 3000

let permissionRequest: Promise<NotificationPermission> | null = null
const recentNotifications = new Map<string, number>()

function canUseSystemNotifications(): boolean {
  return typeof window !== 'undefined' && 'Notification' in window
}

function appLogoUrl(): string {
  if (typeof window === 'undefined') {
    return `/${LOGO_PATH}`
  }

  const base = import.meta.env.BASE_URL || '/'
  const normalizedBase = base.endsWith('/') ? base : `${base}/`
  return new URL(`${normalizedBase}${LOGO_PATH}`, window.location.origin).toString()
}

export function requestAnalysisNotificationPermission(): void {
  if (!canUseSystemNotifications() || Notification.permission !== 'default' || permissionRequest) {
    return
  }

  try {
    permissionRequest = Notification.requestPermission()
      .catch(() => 'denied' as NotificationPermission)
      .finally(() => {
        permissionRequest = null
      })
  } catch {
    permissionRequest = null
  }
}

function shouldSkipNotification(key: string): boolean {
  const now = Date.now()
  const lastShownAt = recentNotifications.get(key)

  if (lastShownAt && now - lastShownAt < DEDUPE_WINDOW_MS) {
    return true
  }

  recentNotifications.set(key, now)
  for (const [candidateKey, shownAt] of recentNotifications) {
    if (now - shownAt > DEDUPE_WINDOW_MS) {
      recentNotifications.delete(candidateKey)
    }
  }

  return false
}

function buildNotificationText(options: AnalysisNotificationOptions): { title: string; body: string; tag: string } {
  const workflowName = options.workflow === 'social-trends'
    ? 'Social media trends analysis'
    : 'Neighborhood analysis'
  const target = options.businessType
    ? `${options.businessType} in ${options.neighborhood}`
    : options.neighborhood
  const detail = options.detail && options.detail.length > 180
    ? `${options.detail.slice(0, 177)}...`
    : options.detail
  const tag = `aleithia-${options.workflow}-${options.status}-${options.neighborhood}-${options.businessType ?? 'general'}`

  if (options.status === 'success') {
    return {
      title: `${workflowName} complete`,
      body: `${target} is ready.`,
      tag,
    }
  }

  return {
    title: `${workflowName} error`,
    body: detail ? `${target}: ${detail}` : `${target} could not be completed.`,
    tag,
  }
}

function showNotification(options: AnalysisNotificationOptions): void {
  const text = buildNotificationText(options)
  const dedupeKey = `${text.tag}-${text.title}-${text.body}`

  if (shouldSkipNotification(dedupeKey)) {
    return
  }

  const logoUrl = appLogoUrl()
  try {
    new Notification(`${APP_NAME}: ${text.title}`, {
      body: text.body,
      icon: logoUrl,
      badge: logoUrl,
      tag: text.tag,
    })
  } catch {
    // Browsers can reject notifications in insecure or unsupported contexts.
  }
}

export function notifyAnalysisCompletion(options: AnalysisNotificationOptions): void {
  if (!canUseSystemNotifications()) {
    return
  }

  if (Notification.permission === 'granted') {
    showNotification(options)
    return
  }

  if (Notification.permission === 'default' && permissionRequest) {
    void permissionRequest.then((permission) => {
      if (permission === 'granted') {
        showNotification(options)
      }
    })
  }
}
