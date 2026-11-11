import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, CircleCheck, RefreshCw } from 'lucide-react'
import type { PantryItem, PantryState, Recipe, ShoppingItem } from './types'
import { demoItems } from './data'
import { ApiError, FRONTEND_TIMEOUT_MS, apiFetch } from './api'
import { daysUntil, formatQuantity, getFallbackSuggestions, loadCachedPantry, saveCachedPantry } from './utils'
import { useToast } from './hooks/useToast'
import { Sidebar } from './components/Sidebar'
import { Topbar } from './components/Topbar'
import { PantryView } from './components/PantryView'
import { RecipesView } from './components/RecipesView'
import { ShoppingView } from './components/ShoppingView'
import { IngredientModal } from './components/IngredientModal'
import { ConsumeModal } from './components/ConsumeModal'
import { RecipeModal } from './components/RecipeModal'

export type Tab = 'pantry' | 'recipes' | 'shopping'
export type PantryFilter = 'all' | 'urgent' | 'expired'
/** loading: first fetch in progress / ready: in sync with SQLite / offline: showing the last cached snapshot. */
export type DataStatus = 'loading' | 'ready' | 'offline'
type Budget = 300 | 500 | 700
type Minutes = 10 | 20 | 30

const toWrite = ({ name, quantity, unit, expiryDate, category, emoji, note }: PantryItem) => ({ name, quantity, unit, expiryDate, category, emoji, note })

export function Kitchen({ token, email, onLogout, onSessionExpired }: { token: string; email: string; onLogout: () => void; onSessionExpired: () => void }) {
  const [status, setStatus] = useState<DataStatus>('loading')
  const [pantry, setPantry] = useState<PantryItem[]>([])
  const [consumed, setConsumed] = useState(0)
  const [shopping, setShopping] = useState<ShoppingItem[]>([])
  const [staples, setStaples] = useState<string[]>([])
  const [activeTab, setActiveTab] = useState<Tab>('pantry')
  const [filter, setFilter] = useState<PantryFilter>('all')
  const [editing, setEditing] = useState<PantryItem | null>(null)
  const [formName, setFormName] = useState<string | null>(null)
  const [consuming, setConsuming] = useState<PantryItem | null>(null)
  const [selectedRecipe, setSelectedRecipe] = useState<Recipe | null>(null)
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [recipeLoading, setRecipeLoading] = useState(false)
  const [recipeSource, setRecipeSource] = useState<'gemini' | 'local'>('local')
  const [recipeMessage, setRecipeMessage] = useState('')
  const [requestedKey, setRequestedKey] = useState('')
  const [budgetYen, setBudgetYen] = useState<Budget>(500)
  const [maxCookingMinutes, setMaxCookingMinutes] = useState<Minutes>(20)
  const [busy, setBusy] = useState(false)
  const initialRecipeRequested = useRef(false)
  const { toast, show } = useToast()
  const showForm = editing !== null || formName !== null

  /** apiFetch with this session's token. A 401 ends the session instead of failing silently. */
  async function call<T>(path: string, options: { method?: string; body?: unknown; timeoutMs?: number } = {}) {
    try {
      return await apiFetch<T>(path, { ...options, token })
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onSessionExpired()
      throw error
    }
  }
  const errorText = (error: unknown) => error instanceof Error ? error.message : '処理に失敗しました。'

  async function loadAll() {
    setStatus('loading')
    try {
      let state = await call<PantryState>('/api/pantry')
      if (!state.initialized && state.items.length === 0) {
        // First visit: restore a cached snapshot from older versions if any, else seed sample items.
        const seed = loadCachedPantry(email) ?? demoItems
        state = await call<PantryState>('/api/pantry/reset', { method: 'PUT', body: seed.map(toWrite) })
      }
      const [shoppingState, staplesState] = await Promise.all([
        call<{ items: ShoppingItem[] }>('/api/shopping'),
        call<{ names: string[] }>('/api/staples'),
      ])
      setPantry(state.items)
      setConsumed(state.consumedCount)
      setShopping(shoppingState.items)
      setStaples(staplesState.names)
      setStatus('ready')
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return
      setPantry(loadCachedPantry(email) ?? [])
      setStatus('offline')
    }
  }

  useEffect(() => { void loadAll() }, []) // eslint-disable-line react-hooks/exhaustive-deps -- once per mount (Kitchen remounts per session)
  useEffect(() => { if (status === 'ready') saveCachedPantry(email, pantry) }, [pantry, status, email])

  const recipeKey = useMemo(() => JSON.stringify({
    p: pantry.map((item) => [item.name, item.quantity, item.expiryDate]).sort(), s: [...staples].sort(), b: budgetYen, m: maxCookingMinutes,
  }), [pantry, staples, budgetYen, maxCookingMinutes])
  const recipesStale = !recipeLoading && requestedKey !== '' && requestedKey !== recipeKey

  async function refreshRecipes() {
    setRecipeLoading(true)
    setRequestedKey(recipeKey)
    try {
      const data = await call<{ recipes?: Recipe[]; source?: 'gemini' | 'local'; message?: string }>('/api/recipes/suggest', {
        method: 'POST',
        body: {
          pantry: pantry.map(({ name, quantity, unit, expiryDate, category }) => ({ name, quantity, unit, expiry_date: expiryDate, category })),
          preferences: { budget_yen: budgetYen, max_minutes: maxCookingMinutes },
        },
        timeoutMs: FRONTEND_TIMEOUT_MS,
      })
      const received = Array.isArray(data.recipes) ? data.recipes : []
      setRecipes(received.length ? received : getFallbackSuggestions(pantry, staples, budgetYen, maxCookingMinutes))
      setRecipeSource(data.source === 'gemini' ? 'gemini' : 'local')
      setRecipeMessage(data.message || '')
    } catch (error) {
      setRecipes(getFallbackSuggestions(pantry, staples, budgetYen, maxCookingMinutes))
      setRecipeSource('local')
      setRecipeMessage(`${errorText(error)} アプリ内の節約レシピを表示しています。`)
    } finally { setRecipeLoading(false) }
  }

  useEffect(() => {
    if (status === 'loading' || initialRecipeRequested.current) return
    // Suggest once on start. Calling Gemini on every pantry/settings change would burn the free quota,
    // so afterwards suggestions only run from the button.
    initialRecipeRequested.current = true
    if (status === 'ready') void refreshRecipes()
    else { setRecipes(getFallbackSuggestions(pantry, staples, budgetYen, maxCookingMinutes)); setRecipeMessage('サーバーに接続できないため、アプリ内の節約レシピを表示しています。') }
  }, [status]) // eslint-disable-line react-hooks/exhaustive-deps

  /** Run a mutation with shared busy/error handling. */
  async function mutate(action: () => Promise<string | void>) {
    if (busy) return
    setBusy(true)
    try {
      const message = await action()
      if (message) show(message)
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) show(errorText(error), 'error')
    } finally { setBusy(false) }
  }

  const closeForm = () => { setEditing(null); setFormName(null) }

  function handleSave(item: Omit<PantryItem, 'id' | 'createdAt'>) {
    const target = editing
    const fromShopping = formName ? shopping.find((row) => row.name === formName && !row.checked) : undefined
    void mutate(async () => {
      const saved = await call<PantryItem>(`/api/pantry${target ? `/${target.id}` : ''}`, { method: target ? 'PUT' : 'POST', body: item })
      setPantry((current) => target ? current.map((row) => row.id === target.id ? saved : row) : [saved, ...current])
      closeForm()
      if (fromShopping) {
        const next = await call<{ items: ShoppingItem[] }>(`/api/shopping/${fromShopping.id}`, { method: 'PATCH', body: { checked: true } })
        setShopping(next.items)
      }
      return target ? `${item.name}の情報を更新しました` : `${item.name}を冷蔵庫に追加しました`
    })
  }

  function handleConsume(item: PantryItem, amount: number) {
    void mutate(async () => {
      const result = await call<{ item: PantryItem | null; consumedCount: number }>(`/api/pantry/${item.id}/consume`, { method: 'POST', body: { amount } })
      setPantry((current) => result.item ? current.map((row) => row.id === item.id ? result.item as PantryItem : row) : current.filter((row) => row.id !== item.id))
      setConsumed(result.consumedCount)
      setConsuming(null)
      return result.item ? `${item.name}を${formatQuantity(amount)}${item.unit}使いました（残り${formatQuantity(result.item.quantity)}${item.unit}）` : `${item.name}を使い切りました！`
    })
  }

  function handleDelete(item: PantryItem) {
    if (!window.confirm(`${item.name}をリストから削除しますか？`)) return
    void mutate(async () => {
      await call(`/api/pantry/${item.id}`, { method: 'DELETE' })
      setPantry((current) => current.filter((row) => row.id !== item.id))
      return `${item.name}を削除しました`
    })
  }

  function resetDemo() {
    if (!window.confirm('サンプル食材に戻しますか？ 今の登録内容は上書きされます。')) return
    void mutate(async () => {
      const state = await call<PantryState>('/api/pantry/reset', { method: 'PUT', body: demoItems.map(toWrite) })
      setPantry(state.items); setConsumed(state.consumedCount); setFilter('all')
      return 'サンプルデータに戻しました'
    })
  }

  function handleCooked(entries: { id: string; amount: number }[]) {
    void mutate(async () => {
      const state = await call<PantryState>('/api/pantry/consume-batch', { method: 'POST', body: { items: entries } })
      setPantry(state.items); setConsumed(state.consumedCount); setSelectedRecipe(null)
      return `ごちそうさま！${entries.length}品の食材を減らしました`
    })
  }

  function addToShopping(names: string[]) {
    void mutate(async () => {
      const result = await call<{ items: ShoppingItem[]; added: number }>('/api/shopping', { method: 'POST', body: { names } })
      setShopping(result.items)
      return result.added ? `買い物リストに${result.added}品を追加しました` : 'すでに買い物リストに入っています'
    })
  }

  function updateShopping(request: () => Promise<{ items: ShoppingItem[] }>, message?: string) {
    void mutate(async () => { setShopping((await request()).items); return message })
  }

  function saveStaples(names: string[]) {
    void mutate(async () => {
      const result = await call<{ names: string[] }>('/api/staples', { method: 'PUT', body: { names } })
      setStaples(result.names)
    })
  }

  const notificationItems = useMemo(() => [...pantry].filter((item) => daysUntil(item.expiryDate) <= 3).sort((a, b) => a.expiryDate.localeCompare(b.expiryDate)), [pantry])
  const openShopping = shopping.filter((item) => !item.checked).length

  return (
    <div className="app-shell">
      <Sidebar activeTab={activeTab} onTab={setActiveTab} pantryCount={pantry.length} shoppingCount={openShopping} consumed={consumed} onReset={resetDemo} />
      <main className="main-content">
        <Topbar activeTab={activeTab} email={email} status={status} pantryCount={pantry.length} consumed={consumed} notificationItems={notificationItems}
          onNotification={(days) => { setActiveTab('pantry'); setFilter(days < 0 ? 'expired' : 'urgent') }} onReset={resetDemo} onLogout={onLogout} />
        {status === 'offline' && <div className="offline-banner" role="alert"><AlertTriangle size={17} /><span>サーバーに接続できません。表示しているのは前回保存した内容で、変更は保存されません。</span><button className="outline-button" onClick={() => void loadAll()}><RefreshCw size={14} />再接続</button></div>}
        {activeTab === 'pantry' && <PantryView pantry={pantry} loading={status === 'loading'} filter={filter} onFilter={setFilter}
          onAdd={() => setFormName('')} onEdit={setEditing} onConsume={setConsuming} onDelete={handleDelete} onShowRecipes={() => setActiveTab('recipes')} />}
        {activeTab === 'recipes' && <RecipesView recipes={recipes} loading={recipeLoading || status === 'loading'} stale={recipesStale} source={recipeSource} message={recipeMessage}
          budgetYen={budgetYen} onBudget={setBudgetYen} maxMinutes={maxCookingMinutes} onMaxMinutes={setMaxCookingMinutes}
          staples={staples} onSaveStaples={saveStaples} busy={busy} onRefresh={() => void refreshRecipes()} onSelect={setSelectedRecipe} onShowPantry={() => setActiveTab('pantry')} />}
        {activeTab === 'shopping' && <ShoppingView items={shopping} busy={busy}
          onAdd={(name) => addToShopping([name])}
          onToggle={(item) => updateShopping(() => call(`/api/shopping/${item.id}`, { method: 'PATCH', body: { checked: !item.checked } }))}
          onDelete={(item) => updateShopping(() => call(`/api/shopping/${item.id}`, { method: 'DELETE' }))}
          onClearChecked={() => updateShopping(() => call('/api/shopping/checked', { method: 'DELETE' }), 'チェック済みの項目を削除しました')}
          onMoveToPantry={(item) => setFormName(item.name)} />}
        <footer className="page-footer"><span>© 2026 mottainai kitchen</span><span>{status === 'ready' ? 'SQLiteデータベースに保存中' : status === 'loading' ? '読み込み中…' : 'オフライン（変更は保存されません）'}</span><span>食材を大切に、毎日のごはんを豊かに。</span></footer>
      </main>

      {toast && <div className={`toast ${toast.tone === 'error' ? 'toast-error' : ''}`} role={toast.tone === 'error' ? 'alert' : 'status'}>{toast.tone === 'error' ? <AlertTriangle size={17} /> : <CircleCheck size={17} />}{toast.message}</div>}
      {showForm && <IngredientModal item={editing} initialName={formName ?? ''} onClose={closeForm} onSave={handleSave} />}
      {consuming && <ConsumeModal item={consuming} onClose={() => setConsuming(null)} onConsume={(amount) => handleConsume(consuming, amount)} />}
      {selectedRecipe && <RecipeModal recipe={selectedRecipe} pantry={pantry} staples={staples} busy={busy} onClose={() => setSelectedRecipe(null)} onAddToShopping={addToShopping} onCooked={handleCooked} />}
    </div>
  )
}
