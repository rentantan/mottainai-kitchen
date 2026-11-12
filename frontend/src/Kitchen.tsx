import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, CircleCheck, RefreshCw } from 'lucide-react'
import type { PantryItem, PantryState, Recipe, ShoppingItem, WasteSummary } from './types'
import { FREEZER_DAYS, dateOffset, demoItems } from './data'
import type { Equipment } from './data'
import { ApiError, FRONTEND_TIMEOUT_MS, apiFetch } from './api'
import { daysUntil, formatQuantity, getFallbackSuggestions, loadCachedPantry, saveCachedPantry } from './utils'
import { useToast } from './hooks/useToast'
import type { ToastAction } from './hooks/useToast'
import { Sidebar } from './components/Sidebar'
import { Topbar } from './components/Topbar'
import { PantryView } from './components/PantryView'
import { RecipesView } from './components/RecipesView'
import { ShoppingView } from './components/ShoppingView'
import { IngredientModal } from './components/IngredientModal'
import { ConsumeModal } from './components/ConsumeModal'
import { RecipeModal } from './components/RecipeModal'
import { DeleteModal } from './components/DeleteModal'
import { AccountModal } from './components/AccountModal'
import type { DeleteReason } from './components/DeleteModal'

export type Tab = 'pantry' | 'recipes' | 'shopping'
export type PantryFilter = 'all' | 'urgent' | 'expired'
/** loading: first fetch in progress / ready: in sync with SQLite / offline: showing the last cached snapshot. */
export type DataStatus = 'loading' | 'ready' | 'offline'
type Budget = 300 | 500 | 700
type Minutes = 10 | 20 | 30

const EMPTY_WASTE: WasteSummary = { items: [], totalCount: 0, monthCount: 0 }
/** A mutation may return a toast message, optionally with an action button such as "元に戻す". */
type MutationResult = string | { message: string; action?: ToastAction } | void

const toWrite = ({ name, quantity, unit, expiryDate, category, emoji, note, frozen, priceYen, purchasedQuantity }: PantryItem) =>
  ({ name, quantity, unit, expiryDate, category, emoji, note, frozen: frozen ?? false, priceYen: priceYen ?? null, purchasedQuantity: purchasedQuantity ?? null })

export function Kitchen({ token, email, onLogout, onSessionExpired, onAccountDeleted }: { token: string; email: string; onLogout: () => void; onSessionExpired: () => void; onAccountDeleted: () => void }) {
  const [status, setStatus] = useState<DataStatus>('loading')
  const [pantry, setPantry] = useState<PantryItem[]>([])
  const [consumed, setConsumed] = useState(0)
  const [waste, setWaste] = useState<WasteSummary>(EMPTY_WASTE)
  const [shopping, setShopping] = useState<ShoppingItem[]>([])
  const [staples, setStaples] = useState<string[]>([])
  const [activeTab, setActiveTab] = useState<Tab>('pantry')
  const [filter, setFilter] = useState<PantryFilter>('all')
  const [editing, setEditing] = useState<PantryItem | null>(null)
  const [formName, setFormName] = useState<string | null>(null)
  const [consuming, setConsuming] = useState<PantryItem | null>(null)
  const [deleting, setDeleting] = useState<PantryItem | null>(null)
  const [selectedRecipe, setSelectedRecipe] = useState<Recipe | null>(null)
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [recipeLoading, setRecipeLoading] = useState(false)
  const [recipeSource, setRecipeSource] = useState<'gemini' | 'local'>('local')
  const [recipeMessage, setRecipeMessage] = useState('')
  const [requestedKey, setRequestedKey] = useState('')
  const [budgetYen, setBudgetYen] = useState<Budget>(500)
  const [maxCookingMinutes, setMaxCookingMinutes] = useState<Minutes>(20)
  const [equipment, setEquipment] = useState<Equipment>('any')
  const [busy, setBusy] = useState(false)
  // A ref as well: undo buttons in toasts call mutate() from an older render, where `busy` is stale.
  const busyRef = useRef(false)
  const [showAccount, setShowAccount] = useState(false)
  const initialRecipeRequested = useRef(false)
  const { toast, show, hide } = useToast()
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
        // First visit: restore a cached snapshot from older versions if any, else start with an empty
        // fridge (real users should not have to delete sample food; the empty state offers samples).
        const seed = loadCachedPantry(email) ?? []
        state = await call<PantryState>('/api/pantry/reset', { method: 'PUT', body: seed.map(toWrite) })
      }
      const [shoppingState, staplesState] = await Promise.all([
        call<{ items: ShoppingItem[] }>('/api/shopping'),
        call<{ names: string[] }>('/api/staples'),
      ])
      setPantry(state.items)
      setConsumed(state.consumedCount)
      setWaste(state.waste ?? EMPTY_WASTE)
      setShopping(shoppingState.items)
      setStaples(staplesState.names)
      setStatus('ready')
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return
      setPantry(loadCachedPantry(email) ?? [])
      setStatus('offline')
    }
  }

  // Re-render when the date changes (app left open overnight, or reopened from the background)
  // so "今日まで" / "あと○日" never show yesterday's numbers.
  const [today, setToday] = useState(() => dateOffset(0))
  useEffect(() => {
    const check = () => setToday(dateOffset(0))
    const now = new Date()
    const msToMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).getTime() - now.getTime() + 1000
    const timer = window.setTimeout(check, msToMidnight)
    const onVisible = () => { if (document.visibilityState === 'visible') check() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { window.clearTimeout(timer); document.removeEventListener('visibilitychange', onVisible) }
  }, [today])

  useEffect(() => { void loadAll() }, []) // eslint-disable-line react-hooks/exhaustive-deps -- once per mount (Kitchen remounts per session)
  useEffect(() => { if (status === 'ready') saveCachedPantry(email, pantry) }, [pantry, status, email])

  const recipeKey = useMemo(() => JSON.stringify({
    p: pantry.map((item) => [item.name, item.quantity, item.expiryDate, item.frozen ?? false]).sort(), s: [...staples].sort(), b: budgetYen, m: maxCookingMinutes, e: equipment,
  }), [pantry, staples, budgetYen, maxCookingMinutes, equipment])
  const recipesStale = !recipeLoading && requestedKey !== '' && requestedKey !== recipeKey

  /** another=true: same conditions, but the user wants different dishes (skips the server cache). */
  async function refreshRecipes(another = false) {
    const shownNames = another ? recipes.map((recipe) => recipe.name) : []
    setRecipeLoading(true)
    setRequestedKey(recipeKey)
    try {
      const data = await call<{ recipes?: Recipe[]; source?: 'gemini' | 'local'; message?: string }>('/api/recipes/suggest', {
        method: 'POST',
        body: {
          pantry: pantry.map(({ name, quantity, unit, expiryDate, category, frozen }) => ({ name, quantity, unit, expiry_date: expiryDate, category, frozen: frozen ?? false })),
          preferences: { budget_yen: budgetYen, max_minutes: maxCookingMinutes, equipment },
          refresh: another,
          exclude_recipe_names: shownNames,
        },
        timeoutMs: FRONTEND_TIMEOUT_MS,
      })
      const received = Array.isArray(data.recipes) ? data.recipes : []
      setRecipes(received.length ? received : getFallbackSuggestions(pantry, staples, budgetYen, maxCookingMinutes, equipment))
      setRecipeSource(data.source === 'gemini' ? 'gemini' : 'local')
      setRecipeMessage(data.message || '')
    } catch (error) {
      setRecipes(getFallbackSuggestions(pantry, staples, budgetYen, maxCookingMinutes, equipment))
      setRecipeSource('local')
      setRecipeMessage(`${errorText(error)} アプリ内の節約レシピを表示しています。`)
    } finally { setRecipeLoading(false) }
  }

  useEffect(() => {
    if (status === 'loading' || initialRecipeRequested.current) return
    // Suggest once on start. Calling Gemini on every pantry/settings change would burn the free quota,
    // so afterwards suggestions only run from the button.
    initialRecipeRequested.current = true
    if (status === 'ready' && pantry.length === 0) {
      // Nothing registered yet: don't spend AI quota on an empty fridge.
      setRecipes(getFallbackSuggestions(pantry, staples, budgetYen, maxCookingMinutes, equipment))
      setRecipeMessage('食材を登録すると、冷蔵庫の中身と期限に合わせてAIがレシピを提案します。いまはアプリ内の節約レシピを表示しています。')
      setRequestedKey(recipeKey)
    } else if (status === 'ready') void refreshRecipes()
    else { setRecipes(getFallbackSuggestions(pantry, staples, budgetYen, maxCookingMinutes, equipment)); setRecipeMessage('サーバーに接続できないため、アプリ内の節約レシピを表示しています。') }
  }, [status]) // eslint-disable-line react-hooks/exhaustive-deps

  /** Run a mutation with shared busy/error handling. */
  async function mutate(action: () => Promise<MutationResult>) {
    if (busyRef.current) { show('前の操作を保存しています。少し待ってからもう一度押してください', 'error'); return }
    busyRef.current = true
    setBusy(true)
    try {
      const result = await action()
      if (typeof result === 'string') show(result)
      else if (result) show(result.message, 'success', result.action)
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) show(errorText(error), 'error')
    } finally { busyRef.current = false; setBusy(false) }
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
      const result = await call<{ item: PantryItem | null; consumedCount: number; logId: string; waste: WasteSummary }>(`/api/pantry/${item.id}/consume`, { method: 'POST', body: { amount } })
      setPantry((current) => result.item ? current.map((row) => row.id === item.id ? result.item as PantryItem : row) : current.filter((row) => row.id !== item.id))
      setConsumed(result.consumedCount)
      setWaste(result.waste ?? EMPTY_WASTE)
      setConsuming(null)
      return {
        message: result.item ? `${item.name}を${formatQuantity(amount)}${item.unit}使いました（残り${formatQuantity(result.item.quantity)}${item.unit}）` : `${item.name}を使い切りました！`,
        action: { label: '元に戻す', onClick: () => undoConsume([{ logId: result.logId, item }]) },
      }
    })
  }

  /** Undo "使った" / "作った！". `item` is the item as it was before, used to bring back what was used up. */
  function undoConsume(entries: { logId: string; item: PantryItem }[]) {
    hide()
    void mutate(async () => {
      const state = await call<PantryState>('/api/pantry/undo-consume', {
        method: 'POST', body: { entries: entries.map(({ logId, item }) => ({ logId, item: toWrite(item), createdAt: item.createdAt })) },
      })
      setPantry(state.items); setConsumed(state.consumedCount); setWaste(state.waste ?? EMPTY_WASTE)
      return '元に戻しました'
    })
  }

  function handleDelete(item: PantryItem, reason: DeleteReason) {
    void mutate(async () => {
      const result = await call<{ item: PantryItem; wasteId: string | null; waste: WasteSummary }>(`/api/pantry/${item.id}?reason=${reason}`, { method: 'DELETE' })
      setPantry((current) => current.filter((row) => row.id !== item.id))
      setWaste(result.waste)
      setDeleting(null)
      return {
        message: reason === 'discarded' ? `${item.name}をもったいない記録に残しました` : `${item.name}を削除しました`,
        action: { label: '元に戻す', onClick: () => undoDelete(result.item, result.wasteId) },
      }
    })
  }

  function undoDelete(item: PantryItem, wasteId: string | null) {
    hide()
    void mutate(async () => {
      const result = await call<{ item: PantryItem; waste: WasteSummary }>('/api/pantry/restore', { method: 'POST', body: { item: toWrite(item), createdAt: item.createdAt, wasteId } })
      setPantry((current) => [result.item, ...current])
      setWaste(result.waste)
      return `${item.name}を元に戻しました`
    })
  }

  /** Freeze (extends the expiry to about a month) or thaw (use within a day or so). Undoable from the toast. */
  function handleFreeze(item: PantryItem, frozen: boolean) {
    const updated = { ...item, frozen, expiryDate: dateOffset(frozen ? FREEZER_DAYS : 1) }
    void mutate(async () => {
      const saved = await call<PantryItem>(`/api/pantry/${item.id}`, { method: 'PUT', body: toWrite(updated) })
      setPantry((current) => current.map((row) => row.id === item.id ? saved : row))
      const date = new Date(`${saved.expiryDate}T00:00:00`).toLocaleDateString('ja-JP', { month: 'numeric', day: 'numeric' })
      return {
        message: frozen ? `${item.name}を冷凍しました（目安：${date}まで）` : `${item.name}を解凍しました。${date}までに使い切ろう`,
        action: { label: '元に戻す', onClick: () => { hide(); void mutate(async () => {
          const restored = await call<PantryItem>(`/api/pantry/${item.id}`, { method: 'PUT', body: toWrite(item) })
          setPantry((current) => current.map((row) => row.id === item.id ? restored : row))
          return `${item.name}を元に戻しました`
        }) } },
      }
    })
  }

  function resetDemo() {
    const message = pantry.length ? 'サンプル食材に入れ替えますか？ 今登録している食材は消えます（使い切り数ともったいない記録は残ります）。' : null
    if (message && !window.confirm(message)) return
    void mutate(async () => {
      const state = await call<PantryState>('/api/pantry/reset?keep_records=true', { method: 'PUT', body: demoItems.map(toWrite) })
      setPantry(state.items); setConsumed(state.consumedCount); setWaste(state.waste ?? EMPTY_WASTE); setFilter('all')
      return 'サンプル食材を入れました。試し終わったら「冷蔵庫の中身」の「すべて削除」で空に戻せます'
    })
  }

  /** Empty the fridge (e.g. after trying the samples). Records are kept unless the user also asks to reset them. */
  function clearAll() {
    if (!window.confirm('冷蔵庫の食材をすべて削除しますか？')) return
    const hasRecords = consumed > 0 || waste.totalCount > 0
    const resetRecords = hasRecords && window.confirm('使い切り数ともったいない記録もリセットしますか？\n（OK：リセットする／キャンセル：記録は残す）')
    void mutate(async () => {
      const state = await call<PantryState>(`/api/pantry/reset${resetRecords ? '' : '?keep_records=true'}`, { method: 'PUT', body: [] })
      setPantry(state.items); setConsumed(state.consumedCount); setWaste(state.waste ?? EMPTY_WASTE); setFilter('all')
      return resetRecords ? '冷蔵庫と記録をリセットしました' : '冷蔵庫を空にしました（記録は残しています）'
    })
  }

  function handleCooked(entries: { id: string; amount: number }[]) {
    void mutate(async () => {
      const before = new Map(pantry.map((row) => [row.id, row]))
      const state = await call<PantryState & { logIds: string[] }>('/api/pantry/consume-batch', { method: 'POST', body: { items: entries } })
      setPantry(state.items); setConsumed(state.consumedCount); setWaste(state.waste ?? EMPTY_WASTE); setSelectedRecipe(null)
      const undoEntries = entries.map((entry, index) => ({ logId: state.logIds[index], item: before.get(entry.id) as PantryItem }))
      return { message: `ごちそうさま！${entries.length}品の食材を減らしました`, action: { label: '元に戻す', onClick: () => undoConsume(undoEntries) } }
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

  const notificationItems = useMemo(() => [...pantry].filter((item) => daysUntil(item.expiryDate) <= 3).sort((a, b) => a.expiryDate.localeCompare(b.expiryDate)), [pantry, today]) // eslint-disable-line react-hooks/exhaustive-deps -- today: recompute days left after midnight
  const openShopping = shopping.filter((item) => !item.checked).length

  return (
    <div className="app-shell">
      <Sidebar activeTab={activeTab} onTab={setActiveTab} pantryCount={pantry.length} shoppingCount={openShopping} consumed={consumed} wasted={waste.monthCount} onReset={resetDemo} />
      <main className="main-content">
        <Topbar activeTab={activeTab} email={email} status={status} pantryCount={pantry.length} consumed={consumed} notificationItems={notificationItems}
          onNotification={(days) => { setActiveTab('pantry'); setFilter(days < 0 ? 'expired' : 'urgent') }} onReset={resetDemo} onLogout={onLogout} onAccount={() => setShowAccount(true)} />
        {status === 'offline' && <div className="offline-banner" role="alert"><AlertTriangle size={17} /><span>サーバーに接続できません。表示しているのは前回保存した内容で、変更は保存されません。</span><button className="outline-button" onClick={() => void loadAll()}><RefreshCw size={14} />再接続</button></div>}
        {activeTab === 'pantry' && <PantryView pantry={pantry} loading={status === 'loading'} filter={filter} onFilter={setFilter} waste={waste} consumed={consumed}
          onAdd={() => setFormName('')} onEdit={setEditing} onConsume={setConsuming} onDelete={setDeleting} onShowRecipes={() => setActiveTab('recipes')}
          onFreeze={handleFreeze} onLoadSample={resetDemo} onClearAll={clearAll} />}
        {activeTab === 'recipes' && <RecipesView recipes={recipes} loading={recipeLoading || status === 'loading'} stale={recipesStale} source={recipeSource} message={recipeMessage}
          budgetYen={budgetYen} onBudget={setBudgetYen} maxMinutes={maxCookingMinutes} onMaxMinutes={setMaxCookingMinutes} equipment={equipment} onEquipment={setEquipment}
          staples={staples} onSaveStaples={saveStaples} busy={busy} onRefresh={() => void refreshRecipes(!recipesStale)} onSelect={setSelectedRecipe} onShowPantry={() => setActiveTab('pantry')} />}
        {activeTab === 'shopping' && <ShoppingView items={shopping} busy={busy}
          onAdd={(name) => addToShopping([name])}
          onToggle={(item) => updateShopping(() => call(`/api/shopping/${item.id}`, { method: 'PATCH', body: { checked: !item.checked } }))}
          onDelete={(item) => updateShopping(() => call(`/api/shopping/${item.id}`, { method: 'DELETE' }))}
          onClearChecked={() => updateShopping(() => call('/api/shopping/checked', { method: 'DELETE' }), 'チェック済みの項目を削除しました')}
          onMoveToPantry={(item) => setFormName(item.name)} />}
        <footer className="page-footer"><span>© 2026 mottainai kitchen</span><span>{status === 'ready' ? 'SQLiteデータベースに保存中' : status === 'loading' ? '読み込み中…' : 'オフライン（変更は保存されません）'}</span><span>食材を大切に、毎日のごはんを豊かに。</span></footer>
      </main>

      {toast && <div className={`toast ${toast.tone === 'error' ? 'toast-error' : ''}`} role={toast.tone === 'error' ? 'alert' : 'status'}>{toast.tone === 'error' ? <AlertTriangle size={17} /> : <CircleCheck size={17} />}{toast.message}{toast.action && <button type="button" className="toast-action" onClick={toast.action.onClick}>{toast.action.label}</button>}</div>}
      {showForm && <IngredientModal item={editing} initialName={formName ?? ''} onClose={closeForm} onSave={handleSave} />}
      {deleting && <DeleteModal item={deleting} onClose={() => setDeleting(null)} onDelete={(reason) => handleDelete(deleting, reason)} />}
      {consuming && <ConsumeModal item={consuming} onClose={() => setConsuming(null)} onConsume={(amount) => handleConsume(consuming, amount)} />}
      {showAccount && <AccountModal email={email} call={call} onClose={() => setShowAccount(false)} onDone={(message) => show(message)} onDeleted={onAccountDeleted} />}
      {selectedRecipe && <RecipeModal recipe={selectedRecipe} pantry={pantry} staples={staples} busy={busy} onClose={() => setSelectedRecipe(null)} onAddToShopping={addToShopping} onCooked={handleCooked} />}
    </div>
  )
}
