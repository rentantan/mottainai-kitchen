import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'

/**
 * Close a modal / popover with the Escape key, and (when `containerRef` is given)
 * with a click outside that element. Does nothing while `active` is false.
 */
export function useDismiss(active: boolean, onDismiss: () => void, containerRef?: RefObject<HTMLElement>) {
  // Keep the latest callback without re-registering listeners on every render.
  const callback = useRef(onDismiss)
  callback.current = onDismiss

  useEffect(() => {
    if (!active) return
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') callback.current() }
    const onPointer = (event: MouseEvent) => {
      const container = containerRef?.current
      if (container && !container.contains(event.target as Node)) callback.current()
    }
    document.addEventListener('keydown', onKey)
    if (containerRef) document.addEventListener('mousedown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      if (containerRef) document.removeEventListener('mousedown', onPointer)
    }
  }, [active, containerRef])
}
