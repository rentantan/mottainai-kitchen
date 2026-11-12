import { useCallback, useEffect, useRef, useState } from 'react'

export type ToastAction = { label: string; onClick: () => void }
export type Toast = { message: string; tone: 'success' | 'error'; action?: ToastAction }

/** Single toast; a new message replaces the old one and restarts the hide timer. */
export function useToast(durationMs = 3200) {
  const [toast, setToast] = useState<Toast | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const hide = useCallback(() => { window.clearTimeout(timer.current); setToast(null) }, [])
  const show = useCallback((message: string, tone: Toast['tone'] = 'success', action?: ToastAction) => {
    window.clearTimeout(timer.current)
    setToast({ message, tone, action })
    // Toasts with an action (e.g. "元に戻す") stay longer so there is time to press it.
    const duration = action ? durationMs * 2 : tone === 'error' ? durationMs * 1.6 : durationMs
    timer.current = window.setTimeout(() => setToast(null), duration)
  }, [durationMs])
  useEffect(() => () => window.clearTimeout(timer.current), [])
  return { toast, show, hide }
}
