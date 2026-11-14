import { useEffect, useMemo, useRef, useState } from 'react'
import type { PantryItem, Recipe } from '../types'
import type { Equipment } from '../data'
import type { DataStatus } from '../Kitchen'
import { FRONTEND_TIMEOUT_MS } from '../api'
import { getFallbackSuggestions, scoreRecipe } from '../utils'

export type Budget = 300 | 500 | 700
export type Minutes = 10 | 20 | 30
type Call = <T>(path: string, options?: { method?: string; body?: unknown; timeoutMs?: number }) => Promise<T>
type SuggestResponse = { recipes?: Recipe[]; source?: 'gemini' | 'local'; message?: string }
type Preferences = { budgetYen: Budget; maxMinutes: Minutes; equipment: Equipment }

export const PREFS_KEY = 'mottainai-kitchen-recipe-prefs-v1'
const DEFAULT_PREFS: Preferences = { budgetYen: 500, maxMinutes: 20, equipment: 'any' }

/** The conditions picked last time on this device (per account), so a student without a stove picks "レンジだけ" once. */
export function loadPreferences(email: string): Preferences {
  try {
    const saved = JSON.parse(localStorage.getItem(`${PREFS_KEY}:${email}`) ?? 'null') as Partial<Preferences> | null
    return {
      budgetYen: ([300, 500, 700] as const).find((value) => value === saved?.budgetYen) ?? DEFAULT_PREFS.budgetYen,
      maxMinutes: ([10, 20, 30] as const).find((value) => value === saved?.maxMinutes) ?? DEFAULT_PREFS.maxMinutes,
      equipment: saved?.equipment === 'microwave' ? 'microwave' : 'any',
    }
  } catch { return DEFAULT_PREFS }
}
function savePreferences(email: string, prefs: Preferences) {
  try { localStorage.setItem(`${PREFS_KEY}:${email}`, JSON.stringify(prefs)) } catch { /* storage full or disabled */ }
}

/**
 * Recipe suggestions: conditions (budget / time / equipment), the current results, and whether
 * they are out of date because the fridge or the conditions changed since they were requested.
 *
 * Suggests once when the data has loaded. After that only the button asks again: calling
 * Gemini on every pantry or settings change would burn the shared free quota.
 */
export function useRecipes({ call, email, status, pantry, staples }: { call: Call; email: string; status: DataStatus; pantry: PantryItem[]; staples: string[] }) {
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [loading, setLoading] = useState(false)
  const [source, setSource] = useState<'gemini' | 'local'>('local')
  const [message, setMessage] = useState('')
  const [requestedKey, setRequestedKey] = useState('')
  const [initialPrefs] = useState(() => loadPreferences(email))
  const [budgetYen, setBudgetYen] = useState<Budget>(initialPrefs.budgetYen)
  const [maxMinutes, setMaxMinutes] = useState<Minutes>(initialPrefs.maxMinutes)
  const [equipment, setEquipment] = useState<Equipment>(initialPrefs.equipment)
  useEffect(() => savePreferences(email, { budgetYen, maxMinutes, equipment }), [email, budgetYen, maxMinutes, equipment])
  const initialRequested = useRef(false)

  const key = useMemo(() => JSON.stringify({
    p: pantry.map((item) => [item.name, item.quantity, item.expiryDate, item.frozen ?? false]).sort(), s: [...staples].sort(), b: budgetYen, m: maxMinutes, e: equipment,
  }), [pantry, staples, budgetYen, maxMinutes, equipment])
  const stale = !loading && requestedKey !== '' && requestedKey !== key

  const fallback = () => getFallbackSuggestions(pantry, staples, budgetYen, maxMinutes, equipment)
  function showLocal(text: string) {
    setRecipes(fallback())
    setSource('local')
    setMessage(text)
  }

  /** another=true: same conditions, but the user wants different dishes (skips the server cache). */
  async function refresh(another = false) {
    const shownNames = another ? recipes.map((recipe) => recipe.name) : []
    setLoading(true)
    setRequestedKey(key)
    try {
      // The server suggests from the pantry stored in SQLite, so the fridge is not sent here.
      const data = await call<SuggestResponse>('/api/recipes/suggest', {
        method: 'POST',
        body: { preferences: { budget_yen: budgetYen, max_minutes: maxMinutes, equipment }, refresh: another, exclude_recipe_names: shownNames },
        timeoutMs: FRONTEND_TIMEOUT_MS,
      })
      const received = Array.isArray(data.recipes) ? data.recipes : []
      setRecipes(received.length ? received : fallback())
      setSource(data.source === 'gemini' ? 'gemini' : 'local')
      setMessage(data.message || '')
    } catch (error) {
      showLocal(`${error instanceof Error ? error.message : '処理に失敗しました。'} アプリ内の節約レシピを表示しています。`)
    } finally { setLoading(false) }
  }

  // App recipes cost nothing to recompute, so follow the fridge and the conditions right away.
  // (Gemini results are only re-matched below; asking Gemini again stays a button press.)
  useEffect(() => {
    if (source === 'local' && !loading && requestedKey !== '') setRecipes(fallback())
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps -- only when the fridge or the conditions change

  // "冷蔵庫にある" marks and match % always reflect the current fridge, even for older results.
  const shown = recipes.map((recipe) => scoreRecipe(recipe, pantry, staples))

  useEffect(() => {
    if (status === 'loading' || initialRequested.current) return
    initialRequested.current = true
    if (status === 'offline') showLocal('サーバーに接続できないため、アプリ内の節約レシピを表示しています。')
    else if (pantry.length === 0) {
      // Nothing registered yet: don't spend AI quota on an empty fridge.
      showLocal('食材を登録すると、冷蔵庫の中身と期限に合わせてAIがレシピを提案します。いまはアプリ内の節約レシピを表示しています。')
      setRequestedKey(key)
    } else void refresh()
  }, [status]) // eslint-disable-line react-hooks/exhaustive-deps -- only the first time the data is ready

  return { recipes: shown, loading, source, message, stale, refresh, budgetYen, setBudgetYen, maxMinutes, setMaxMinutes, equipment, setEquipment }
}
