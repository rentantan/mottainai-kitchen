import type { PantryItem } from '../types'
import { STORAGE_KEY } from './config'

/** Last pantry snapshot from the server, used only for read-only display while offline. */
export function loadCachedPantry(email: string): PantryItem[] | null {
  try {
    const raw = localStorage.getItem(`${STORAGE_KEY}:${email}`)
    const parsed = raw ? JSON.parse(raw) : null
    return Array.isArray(parsed) ? parsed as PantryItem[] : null
  } catch { return null }
}
/** Forget everything this device kept for an account (after the account is deleted). */
export function clearLocalData(email: string, keys: string[]) {
  for (const key of [STORAGE_KEY, ...keys]) {
    try { localStorage.removeItem(`${key}:${email}`) } catch { /* storage disabled */ }
  }
}
export function saveCachedPantry(email: string, items: PantryItem[]) {
  try { localStorage.setItem(`${STORAGE_KEY}:${email}`, JSON.stringify(items)) } catch { /* storage full or disabled */ }
}
