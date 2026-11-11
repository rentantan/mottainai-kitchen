import { useCallback, useEffect, useRef, useState } from 'react'

export type Toast = { message: string; tone: 'success' | 'error' }

/** Single toast; a new message replaces the old one and restarts the hide timer. */
export function useToast(durationMs = 3200) {
  const [toast, setToast] = useState<Toast | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const show = useCallback((message: string, tone: Toast['tone'] = 'success') => {
    window.clearTimeout(timer.current)
    setToast({ message, tone })
    timer.current = window.setTimeout(() => setToast(null), tone === 'error' ? durationMs * 1.6 : durationMs)
  }, [durationMs])
  useEffect(() => () => window.clearTimeout(timer.current), [])
  return { toast, show }
}
