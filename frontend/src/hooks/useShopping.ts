import { useRef, useState } from 'react'
import type { ShoppingItem } from '../types'
import { ApiError } from '../api'

type Call = <T>(path: string, options?: { method?: string; body?: unknown }) => Promise<T>
type Show = (message: string, tone?: 'success' | 'error') => void
type ListResponse = { items: ShoppingItem[] }

/**
 * Shopping list state. Checking off and deleting items update the screen at once and do
 * not wait for each other (ticking items in a shop should never say "wait"), so they skip
 * Kitchen's one-at-a-time lock. Each server reply carries the whole list; only the reply to
 * the newest change is applied, so a slow earlier reply cannot undo a later tap.
 */
export function useShopping(call: Call, show: Show) {
  const [items, setItems] = useState<ShoppingItem[]>([])
  const latest = useRef(0)

  /** Set the list from the server (initial load, or a change made through Kitchen's lock). */
  function replace(next: ShoppingItem[]) {
    latest.current += 1
    setItems(next)
  }

  function change(optimistic: (current: ShoppingItem[]) => ShoppingItem[], path: string, method: string, body?: unknown, message?: string) {
    const id = ++latest.current
    setItems(optimistic)
    call<ListResponse>(path, { method, body })
      .then((result) => {
        if (id === latest.current) setItems(result.items)
        if (message) show(message)
      })
      .catch(async (error: unknown) => {
        if (error instanceof ApiError && error.status === 401) return
        show(error instanceof Error ? error.message : '処理に失敗しました。', 'error')
        // Put the screen back in line with what the server actually saved.
        try {
          const result = await call<ListResponse>('/api/shopping')
          if (id === latest.current) setItems(result.items)
        } catch { /* still offline: keep what is shown */ }
      })
  }

  return {
    items,
    replace,
    toggle: (item: ShoppingItem) => change(
      (current) => current.map((row) => row.id === item.id ? { ...row, checked: !item.checked } : row),
      `/api/shopping/${item.id}`, 'PATCH', { checked: !item.checked }),
    remove: (item: ShoppingItem) => change(
      (current) => current.filter((row) => row.id !== item.id), `/api/shopping/${item.id}`, 'DELETE'),
    clearChecked: () => change(
      (current) => current.filter((row) => !row.checked), '/api/shopping/checked', 'DELETE', undefined, 'チェック済みの項目を削除しました'),
  }
}
