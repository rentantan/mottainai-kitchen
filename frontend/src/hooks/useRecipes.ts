import { useEffect, useMemo, useRef, useState } from 'react'
import type { PantryItem, Recipe } from '../types'
import type { Equipment } from '../data'
import type { DataStatus } from '../Kitchen'
import { FRONTEND_TIMEOUT_MS } from '../api'
import { getFallbackSuggestions } from '../utils'

export type Budget = 300 | 500 | 700
export type Minutes = 10 | 20 | 30
type Call = <T>(path: string, options?: { method?: string; body?: unknown; timeoutMs?: number }) => Promise<T>
type SuggestResponse = { recipes?: Recipe[]; source?: 'gemini' | 'local'; message?: string }

/**
 * Recipe suggestions: conditions (budget / time / equipment), the current results, and whether
 * they are out of date because the fridge or the conditions changed since they were requested.
 *
 * Suggests once when the data has loaded. After that only the button asks again: calling
 * Gemini on every pantry or settings change would burn the shared free quota.
 */
export function useRecipes({ call, status, pantry, staples }: { call: Call; status: DataStatus; pantry: PantryItem[]; staples: string[] }) {
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [loading, setLoading] = useState(false)
  const [source, setSource] = useState<'gemini' | 'local'>('local')
  const [message, setMessage] = useState('')
  const [requestedKey, setRequestedKey] = useState('')
  const [budgetYen, setBudgetYen] = useState<Budget>(500)
  const [maxMinutes, setMaxMinutes] = useState<Minutes>(20)
  const [equipment, setEquipment] = useState<Equipment>('any')
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

  return { recipes, loading, source, message, stale, refresh, budgetYen, setBudgetYen, maxMinutes, setMaxMinutes, equipment, setEquipment }
}
