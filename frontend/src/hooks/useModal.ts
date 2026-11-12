import { useEffect, useRef } from 'react'
import { useDismiss } from './useDismiss'

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * Dialog behaviour for a modal panel: Escape closes it, Tab / Shift+Tab stay inside it,
 * and focus returns to whatever was focused before it opened. Attach the ref to the panel.
 */
export function useModal<T extends HTMLElement = HTMLElement>(onClose: () => void) {
  const ref = useRef<T>(null)
  useDismiss(true, onClose)

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const panel = ref.current
    // Focus the panel itself unless a child already took focus (autoFocus).
    if (panel && !panel.contains(document.activeElement)) {
      panel.setAttribute('tabindex', '-1')
      panel.focus()
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Tab' || !ref.current) return
      const items = [...ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.offsetParent !== null)
      if (!items.length) { event.preventDefault(); return }
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement
      if (event.shiftKey && (active === first || !ref.current.contains(active))) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && (active === last || !ref.current.contains(active))) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      if (previous && document.contains(previous)) previous.focus()
    }
  }, [])

  return ref
}
