import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, ArrowRight, Bell, CalendarDays, Check, ChevronDown, CircleCheck, Clock3,
  CookingPot, Flame, Heart, Leaf, ListFilter, Plus, Search, Settings2, ShoppingBasket, Sparkles,
  Trash2, Pencil, Refrigerator, ChefHat, CheckCircle2, Wallet,
} from 'lucide-react'
import type { PantryItem, Recipe } from './types'
import { API_BASE, AUTH_EMAIL_KEY, AUTH_TOKEN_KEY, CONSUMED_KEY, categoryEmoji, categoryOptions, demoItems, STORAGE_KEY } from './data'
import { daysUntil, expiryClass, expiryText, getFallbackSuggestions, normalize, loadConsumed, loadPantry, makeId } from './utils'
import { LoginScreen } from './components/LoginScreen'
import { IngredientModal } from './components/IngredientModal'
import { RecipeModal } from './components/RecipeModal'

function App() {
  const [authToken, setAuthToken] = useState(() => localStorage.getItem(AUTH_TOKEN_KEY) || '')
  const [authEmail, setAuthEmail] = useState(() => localStorage.getItem(AUTH_EMAIL_KEY) || '')
  const localPantryKey = authEmail ? `${STORAGE_KEY}:${authEmail}` : STORAGE_KEY
  const localConsumedKey = authEmail ? `${CONSUMED_KEY}:${authEmail}` : CONSUMED_KEY
  const [pantry, setPantry] = useState<PantryItem[]>(() => loadPantry(localPantryKey))
  const [consumed, setConsumed] = useState<number>(() => loadConsumed(localConsumedKey))
  const [activeTab, setActiveTab] = useState<'pantry' | 'recipes'>('pantry')
  const [filter, setFilter] = useState<'all' | 'urgent' | 'expired'>('all')
  const [query, setQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('すべて')
  const [showCategoryMenu, setShowCategoryMenu] = useState(false)
  const [openTopbarMenu, setOpenTopbarMenu] = useState<'notifications' | 'profile' | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<PantryItem | null>(null)
  const [selectedRecipe, setSelectedRecipe] = useState<Recipe | null>(null)
  const [recipes, setRecipes] = useState<Recipe[]>(() => getFallbackSuggestions(pantry))
  const [recipeLoading, setRecipeLoading] = useState(false)
  const [recipeSource, setRecipeSource] = useState<'gemini' | 'local'>('local')
  const [recipeMessage, setRecipeMessage] = useState('')
  const [budgetYen, setBudgetYen] = useState<300 | 500 | 700>(500)
  const [maxCookingMinutes, setMaxCookingMinutes] = useState<10 | 20 | 30>(20)
  const initialRecipeRequested = useRef(false)
  const [notice, setNotice] = useState('')
  const [databaseMode, setDatabaseMode] = useState<'loading' | 'sqlite' | 'local'>('loading')

  function authFetch(input: string, init: RequestInit = {}) {
    const headers = new Headers(init.headers)
    if (authToken) headers.set('Authorization', `Bearer ${authToken}`)
    return fetch(input, { ...init, headers })
  }

  function handleAuthenticated(token: string, email: string) {
    localStorage.setItem(AUTH_TOKEN_KEY, token)
    localStorage.setItem(AUTH_EMAIL_KEY, email)
    setAuthToken(token)
    setAuthEmail(email)
  }

  function handleLogout() {
    void authFetch(`${API_BASE}/api/auth/logout`, { method: 'POST' }).catch(() => undefined)
    localStorage.removeItem(AUTH_TOKEN_KEY)
    localStorage.removeItem(AUTH_EMAIL_KEY)
    setAuthToken('')
    setAuthEmail('')
    setOpenTopbarMenu(null)
  }

  useEffect(() => {
    if (!authToken) {
      setDatabaseMode('loading')
      return
    }
    let cancelled = false
    async function initializePantry() {
      try {
        const response = await authFetch(`${API_BASE}/api/pantry`)
        if (!response.ok) throw new Error('SQLite API unavailable')
        let state = await response.json() as { items: PantryItem[]; consumedCount: number; initialized: boolean }
        if (!state.initialized && state.items.length === 0) {
          let initialItems = demoItems
          const cached = localStorage.getItem(localPantryKey)
          if (cached) {
            try {
              const parsed = JSON.parse(cached) as PantryItem[]
              if (Array.isArray(parsed)) initialItems = parsed
            } catch { /* Keep sample data when the legacy cache is unreadable. */ }
          }
          const seedResponse = await authFetch(`${API_BASE}/api/pantry/reset`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(initialItems.map(({ name, quantity, unit, expiryDate, category, emoji, note }) => ({ name, quantity, unit, expiryDate, category, emoji, note }))),
          })
          if (!seedResponse.ok) throw new Error('SQLite initialization failed')
          state = await seedResponse.json() as typeof state
        }
        if (!cancelled) {
          setPantry(state.items)
          setConsumed(state.consumedCount)
          setDatabaseMode('sqlite')
        }
      } catch {
        if (!cancelled) {
          setPantry(loadPantry(localPantryKey))
          setConsumed(loadConsumed(localConsumedKey))
          setDatabaseMode('local')
        }
      }
    }
    void initializePantry()
    return () => { cancelled = true }
  }, [authToken, localPantryKey, localConsumedKey])

  useEffect(() => {
    if (databaseMode === 'local') localStorage.setItem(localPantryKey, JSON.stringify(pantry))
  }, [pantry, databaseMode, localPantryKey])
  useEffect(() => {
    if (databaseMode === 'local') localStorage.setItem(localConsumedKey, String(consumed))
  }, [consumed, databaseMode, localConsumedKey])

  const sortedPantry = useMemo(() => [...pantry].sort((a, b) => daysUntil(a.expiryDate) - daysUntil(b.expiryDate)), [pantry])
  const expiredCount = pantry.filter((item) => daysUntil(item.expiryDate) < 0).length
  const soonCount = pantry.filter((item) => daysUntil(item.expiryDate) >= 0 && daysUntil(item.expiryDate) <= 3).length
  const expiringItems = sortedPantry.filter((item) => daysUntil(item.expiryDate) <= 3).slice(0, 4)
  const notificationItems = sortedPantry.filter((item) => daysUntil(item.expiryDate) <= 3)
  const visibleItems = sortedPantry.filter((item) => {
    const matchQuery = normalize(item.name).includes(normalize(query))
    const matchCategory = categoryFilter === 'すべて' || item.category === categoryFilter
    const days = daysUntil(item.expiryDate)
    const matchFilter = filter === 'all' || (filter === 'urgent' && days >= 0 && days <= 3) || (filter === 'expired' && days < 0)
    return matchQuery && matchCategory && matchFilter
  })

  async function refreshRecipes() {
    setRecipeLoading(true)
    try {
      const response = await authFetch(`${API_BASE}/api/recipes/suggest`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pantry: pantry.map(({ name, quantity, unit, expiryDate, category }) => ({ name, quantity, unit, expiry_date: expiryDate, category })),
          preferences: { budget_yen: budgetYen, max_minutes: maxCookingMinutes },
        }),
        signal: AbortSignal.timeout(50000),
      })
      if (!response.ok) throw new Error('API error')
      const data = await response.json() as { recipes?: Recipe[]; source?: 'gemini' | 'local'; message?: string; cached?: boolean }
      const receivedRecipes = Array.isArray(data.recipes) ? data.recipes : []
      setRecipes(receivedRecipes.length ? receivedRecipes : getFallbackSuggestions(pantry, budgetYen, maxCookingMinutes))
      setRecipeSource(data.source === 'gemini' ? 'gemini' : 'local')
      setRecipeMessage(data.message || '')
    } catch {
      setRecipes(getFallbackSuggestions(pantry, budgetYen, maxCookingMinutes))
      setRecipeSource('local')
      setRecipeMessage('バックエンドに接続できないため、アプリ内の節約レシピを表示しています。')
    } finally { setRecipeLoading(false) }
  }
  useEffect(() => {
    if (!authToken || databaseMode === 'loading' || initialRecipeRequested.current) return
    // 起動時に1回だけ提案。食材の追加・編集や設定変更のたびに
    // Geminiを自動呼び出しすると無料枠を消費するため、以後はボタン操作に限定。
    initialRecipeRequested.current = true
    void refreshRecipes()
  }, [authToken, databaseMode])

  async function handleSave(item: Omit<PantryItem, 'id' | 'createdAt'>) {
    try {
      let saved: PantryItem
      if (databaseMode === 'sqlite') {
        const response = await authFetch(`${API_BASE}/api/pantry${editing ? `/${editing.id}` : ''}`, {
          method: editing ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(item),
        })
        if (!response.ok) throw new Error('SQLite save failed')
        saved = await response.json() as PantryItem
      } else {
        saved = { ...item, id: editing?.id ?? makeId(), createdAt: editing?.createdAt ?? new Date().toISOString() }
      }
      if (editing) {
        setPantry((current) => current.map((row) => row.id === editing.id ? saved : row))
        setNotice(`${item.name}の情報を更新しました`)
      } else {
        setPantry((current) => [saved, ...current])
        setNotice(`${item.name}を冷蔵庫に追加しました`)
      }
      setShowForm(false); setEditing(null)
    } catch {
      setNotice('食材を保存できませんでした。バックエンドの状態を確認してください。')
    }
    window.setTimeout(() => setNotice(''), 3200)
  }
  async function handleConsume(item: PantryItem) {
    try {
      if (databaseMode === 'sqlite') {
        const response = await authFetch(`${API_BASE}/api/pantry/${item.id}/consume`, { method: 'POST' })
        if (!response.ok) throw new Error('SQLite consume failed')
        const result = await response.json() as { item: PantryItem | null; consumedCount: number }
        setPantry((current) => result.item ? current.map((row) => row.id === item.id ? result.item as PantryItem : row) : current.filter((row) => row.id !== item.id))
        setConsumed(result.consumedCount)
      } else if (item.quantity <= 1) {
        setPantry((current) => current.filter((row) => row.id !== item.id))
        setConsumed((count) => count + 1)
      } else {
        setPantry((current) => current.map((row) => row.id === item.id ? { ...row, quantity: row.quantity - 1 } : row))
      }
      setNotice(item.quantity <= 1 ? `${item.name}を使い切りました！` : `${item.name}を1${item.unit}分使いました`)
    } catch {
      setNotice('消費記録を保存できませんでした。バックエンドの状態を確認してください。')
    }
    window.setTimeout(() => setNotice(''), 3200)
  }
  async function handleDelete(item: PantryItem) {
    if (!window.confirm(`${item.name}をリストから削除しますか？`)) return
    try {
      if (databaseMode === 'sqlite') {
        const response = await authFetch(`${API_BASE}/api/pantry/${item.id}`, { method: 'DELETE' })
        if (!response.ok) throw new Error('SQLite delete failed')
      }
      setPantry((current) => current.filter((row) => row.id !== item.id))
      setNotice(`${item.name}を削除しました`)
    } catch {
      setNotice('食材を削除できませんでした。バックエンドの状態を確認してください。')
    }
    window.setTimeout(() => setNotice(''), 3200)
  }
  async function resetDemo() {
    if (!window.confirm('サンプル食材に戻しますか？ 今の登録内容は上書きされます。')) return
    try {
      if (databaseMode === 'sqlite') {
        const response = await authFetch(`${API_BASE}/api/pantry/reset`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(demoItems.map(({ name, quantity, unit, expiryDate, category, emoji, note }) => ({ name, quantity, unit, expiryDate, category, emoji, note }))),
        })
        if (!response.ok) throw new Error('SQLite reset failed')
        const state = await response.json() as { items: PantryItem[]; consumedCount: number }
        setPantry(state.items); setConsumed(state.consumedCount)
      } else {
        setPantry(demoItems); setConsumed(0)
      }
      setFilter('all'); setCategoryFilter('すべて'); setQuery('')
      setNotice('サンプルデータに戻しました')
    } catch {
      setNotice('サンプルデータに戻せませんでした。バックエンドの状態を確認してください。')
    }
    window.setTimeout(() => setNotice(''), 3200)
  }

  if (!authToken) return <LoginScreen apiBase={API_BASE} onAuthenticated={handleAuthenticated} />

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup"><div className="brand-mark"><Leaf size={23} strokeWidth={2.4} /></div><div><div className="brand-name">mottainai</div><div className="brand-sub">KITCHEN</div></div></div>
        <div className="side-section-label">MENU</div>
        <button className={`side-link ${activeTab === 'pantry' ? 'active' : ''}`} onClick={() => setActiveTab('pantry')}><Refrigerator size={18} /><span>冷蔵庫の中身</span><span className="side-count">{pantry.length}</span></button>
        <button className={`side-link ${activeTab === 'recipes' ? 'active' : ''}`} onClick={() => setActiveTab('recipes')}><CookingPot size={18} /><span>レシピを探す</span><span className="side-arrow"><ArrowRight size={15} /></span></button>
        <div className="side-section-label side-label-spaced">YOUR KITCHEN</div>
        <div className="side-mini-stat"><div className="mini-stat-icon green"><ShoppingBasket size={17} /></div><div><div className="mini-stat-value">{pantry.length} <small>品</small></div><div className="mini-stat-label">登録中の食材</div></div></div>
        <div className="side-mini-stat"><div className="mini-stat-icon orange"><Heart size={17} /></div><div><div className="mini-stat-value">{consumed} <small>品</small></div><div className="mini-stat-label">使い切った食材</div></div></div>
        <div className="sidebar-bottom"><div className="tip-card"><div className="tip-illustration">🌱</div><div className="tip-title">自炊はゆるく、<br />賢く続けよう。</div><div className="tip-copy">食費を抑えて、<br />食材も使い切ろう。</div></div><button className="side-link reset-link" onClick={resetDemo}><Settings2 size={17} /><span>サンプルに戻す</span></button><div className="sidebar-foot">ひとり暮らしの自炊を応援。</div></div>
      </aside>

      <main className="main-content">
        <header className="topbar"><div className="breadcrumb"><span>マイキッチン</span><span className="crumb-slash">/</span><strong>{activeTab === 'pantry' ? '冷蔵庫の中身' : 'レシピを探す'}</strong></div><div className="topbar-right"><div className="today-pill"><CalendarDays size={15} /><span>{new Date().toLocaleDateString('ja-JP', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' })}</span></div><div className="topbar-menu-wrap"><button className="icon-button" aria-label="期限アラートを開く" aria-expanded={openTopbarMenu === 'notifications'} onClick={() => setOpenTopbarMenu(openTopbarMenu === 'notifications' ? null : 'notifications')}><Bell size={18} />{notificationItems.length > 0 && <span className="notification-dot" />}</button>{openTopbarMenu === 'notifications' && <div className="topbar-popover notification-popover"><div className="popover-heading"><strong>期限アラート</strong><span>{notificationItems.length}件</span></div>{notificationItems.length ? <div className="notification-list">{notificationItems.map((item) => { const days = daysUntil(item.expiryDate); return <button className="notification-item" key={item.id} onClick={() => { setActiveTab('pantry'); setFilter(days < 0 ? 'expired' : 'urgent'); setOpenTopbarMenu(null) }}><span className="notification-emoji">{item.emoji}</span><span className="notification-copy"><strong>{item.name}</strong><small>{days < 0 ? '期限切れ' : expiryText(days)} · 残り{item.quantity}{item.unit}</small></span><ArrowRight size={14} /></button> })}</div> : <p className="popover-empty">期限が近い食材はありません。</p>}</div>}</div><div className="topbar-menu-wrap"><button className="avatar avatar-button" aria-label="アカウントメニューを開く" aria-expanded={openTopbarMenu === 'profile'} onClick={() => setOpenTopbarMenu(openTopbarMenu === 'profile' ? null : 'profile')}>🥑</button>{openTopbarMenu === 'profile' && <div className="topbar-popover profile-popover"><div className="profile-title"><span className="profile-avatar">🥑</span><span><strong>マイキッチン</strong><small>{authEmail}</small></span></div><div className="profile-stats"><span><strong>{pantry.length}</strong>登録中</span><span><strong>{consumed}</strong>使い切り</span></div><div className="storage-status"><span className={`status-dot ${databaseMode === 'sqlite' ? 'is-online' : ''}`} />{databaseMode === 'sqlite' ? 'SQLiteに保存中' : databaseMode === 'loading' ? '保存先を確認中…' : 'このブラウザに保存中'}</div><button className="profile-reset" onClick={() => { setOpenTopbarMenu(null); void resetDemo() }}><Settings2 size={14} />サンプルに戻す</button><button className="profile-logout" onClick={handleLogout}>ログアウト</button></div>}</div></div></header>

        {activeTab === 'pantry' ? <>
          <section className="welcome-row"><div><div className="eyebrow"><span className="eyebrow-dot" /> YOUR DAILY KITCHEN</div><h1>大学生の一人暮らし、<span>冷蔵庫を把握できてる？</span></h1><p className="page-subtitle">食費を抑えながら、食材をムダなく使い切ろう。</p></div><button className="primary-button" onClick={() => { setEditing(null); setShowForm(true) }}><Plus size={18} />食材を追加</button></section>

          <section className="stats-grid">
            <div className="stat-card"><div className="stat-top"><span className="stat-label">登録中の食材</span><span className="stat-icon pale-green"><ShoppingBasket size={18} /></span></div><div className="stat-number">{pantry.length}<span>品</span></div><div className="stat-bottom"><span className="stat-caption">冷蔵庫・食品棚の合計</span><span className="stat-trend"><Leaf size={13} />管理中</span></div></div>
            <div className={`stat-card ${soonCount ? 'highlight-stat' : ''}`}><div className="stat-top"><span className="stat-label">期限が近い食材</span><span className="stat-icon pale-orange"><Clock3 size={18} /></span></div><div className="stat-number">{soonCount}<span>品</span></div><div className="stat-bottom"><span className="stat-caption">3日以内に使おう</span><button className="text-action orange-text" onClick={() => setFilter(filter === 'urgent' ? 'all' : 'urgent')}>確認する <ArrowRight size={13} /></button></div></div>
            <div className="stat-card"><div className="stat-top"><span className="stat-label">期限切れ</span><span className="stat-icon pale-red"><AlertTriangle size={18} /></span></div><div className="stat-number">{expiredCount}<span>品</span></div><div className="stat-bottom"><span className="stat-caption">状態を確認してください</span><button className="text-action red-text" onClick={() => setFilter(filter === 'expired' ? 'all' : 'expired')}>確認する <ArrowRight size={13} /></button></div></div>
          </section>

          <section className="urgent-section"><div className="section-heading"><div><div className="section-title-with-icon"><div className="section-icon urgent-icon"><Flame size={19} /></div><h2>そろそろ使い切ろう</h2><span className="section-count">{soonCount + expiredCount}</span></div><p className="section-description">期限が近い食材から、今日の献立を考えよう。</p></div><button className="subtle-link" onClick={() => setActiveTab('recipes')}>レシピを見る <ArrowRight size={15} /></button></div>
            {expiringItems.length ? <div className="urgent-grid">{expiringItems.map((item) => { const days = daysUntil(item.expiryDate); return <article className={`urgent-card ${days < 0 ? 'urgent-card-expired' : ''}`} key={item.id}><div className="urgent-card-top"><div className="food-emoji">{item.emoji}</div><span className={`expiry-badge ${expiryClass(days)}`}>{expiryText(days)}</span></div><div className="urgent-food-name">{item.name}</div><div className="urgent-food-meta">残り {item.quantity}{item.unit} · {item.category}</div><button className="use-button" onClick={() => handleConsume(item)}><Check size={14} />使った！</button></article> })}</div> : <div className="empty-urgent"><div className="empty-check"><CircleCheck size={22} /></div><div><strong>いい感じ！期限が近い食材はありません</strong><p>この調子で、食材を大切に使い切りましょう。</p></div></div>}
          </section>

          <section className="pantry-section"><div className="section-heading pantry-heading"><div><div className="section-title-with-icon"><div className="section-icon pantry-icon"><Refrigerator size={19} /></div><h2>冷蔵庫の中身</h2><span className="section-count neutral-count">{visibleItems.length}</span></div><p className="section-description">登録した冷蔵庫と食品棚のストックをまとめて管理できます。</p></div><button className="outline-button" onClick={() => { setEditing(null); setShowForm(true) }}><Plus size={16} />追加する</button></div>
            <div className="list-toolbar"><div className="search-box"><Search size={17} /><input aria-label="食材を検索" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="食材名で検索..." /><kbd>⌘ K</kbd></div><div className="toolbar-right"><div className="filter-wrap"><button className={`filter-button ${showCategoryMenu ? 'filter-open' : ''}`} onClick={() => setShowCategoryMenu(!showCategoryMenu)}><ListFilter size={16} />{categoryFilter}<ChevronDown size={14} /></button>{showCategoryMenu && <div className="dropdown-menu">{['すべて', ...categoryOptions].map((category) => <button key={category} onClick={() => { setCategoryFilter(category); setShowCategoryMenu(false) }}>{category}{categoryFilter === category && <Check size={14} />}</button>)}</div>}</div><div className="segmented-filter"><button className={filter === 'all' ? 'selected' : ''} onClick={() => setFilter('all')}>すべて</button><button className={filter === 'urgent' ? 'selected' : ''} onClick={() => setFilter('urgent')}>期限間近</button><button className={filter === 'expired' ? 'selected' : ''} onClick={() => setFilter('expired')}>期限切れ</button></div></div></div>
            {visibleItems.length ? <div className="pantry-table-wrap"><table className="pantry-table"><thead><tr><th>食材</th><th>カテゴリ</th><th>残量</th><th>賞味・消費期限</th><th className="actions-head">アクション</th></tr></thead><tbody>{visibleItems.map((item) => { const days = daysUntil(item.expiryDate); return <tr key={item.id}><td><div className="table-food"><div className="table-emoji">{item.emoji}</div><div><div className="table-food-name">{item.name}</div>{item.note && <div className="table-note">{item.note}</div>}</div></div></td><td><span className="category-chip">{categoryEmoji[item.category]} {item.category}</span></td><td><span className="quantity-text">{item.quantity}<small>{item.unit}</small></span></td><td><div className="expiry-cell"><span className={`expiry-dot ${expiryClass(days)}`} /><div><div className="expiry-date">{new Date(`${item.expiryDate}T00:00:00`).toLocaleDateString('ja-JP', { month: 'numeric', day: 'numeric' })}</div><div className={`expiry-sub ${expiryClass(days)}`}>{expiryText(days)}</div></div></div></td><td><div className="row-actions"><button className="small-action consume-action" onClick={() => handleConsume(item)} title="1単位使う"><Check size={14} /><span>使った</span></button><button className="icon-row-action" onClick={() => { setEditing(item); setShowForm(true) }} title="編集"><Pencil size={15} /></button><button className="icon-row-action delete-action" onClick={() => handleDelete(item)} title="削除"><Trash2 size={15} /></button></div></td></tr> })}</tbody></table></div> : <div className="empty-list"><div className="empty-list-emoji">{query ? '🔎' : '🥦'}</div><h3>{query ? '食材が見つかりませんでした' : 'この条件に合う食材はありません'}</h3><p>検索条件を変えるか、新しい食材を追加しましょう。</p><button className="outline-button" onClick={() => { setQuery(''); setFilter('all'); setCategoryFilter('すべて') }}>条件をリセット</button></div>}
          </section>
        </> : <>
          <section className="welcome-row recipe-welcome"><div><div className="eyebrow"><span className="eyebrow-dot" /> COOK SOMETHING GOOD</div><h1>大学生の自炊を、<span>安く・簡単に。</span></h1><p className="page-subtitle">講義やアルバイトで忙しい日も、一人分・節約・時短。期限が近い食材から献立を考えよう。</p></div><button className="outline-button" onClick={() => setActiveTab('pantry')}><Refrigerator size={16} />食材を確認</button></section>
          <div className="recipe-intro"><div className="recipe-intro-icon"><Sparkles size={23} /></div><div><h2>冷蔵庫から、節約レシピをAI提案</h2><p>Geminiが一人分・低予算・短時間で作れる献立を3つ考えます。</p></div><button className="refresh-recipes" onClick={() => void refreshRecipes()} disabled={recipeLoading}>{recipeLoading ? '提案中…' : '条件を反映して提案'} <Sparkles size={15} /></button></div>
          <section className="student-preferences" aria-label="レシピの希望条件">
            <div className="student-preference-label"><span>🎓</span><div><strong>大学生の一人暮らし節約モード</strong><small>1人分・安い食材・少ない洗い物を優先</small></div></div>
            <label>1食の予算<select value={budgetYen} onChange={(event) => setBudgetYen(Number(event.target.value) as 300 | 500 | 700)}><option value={300}>300円以内</option><option value={500}>500円以内</option><option value={700}>700円以内</option></select></label>
            <label>調理時間<select value={maxCookingMinutes} onChange={(event) => setMaxCookingMinutes(Number(event.target.value) as 10 | 20 | 30)}><option value={10}>10分以内</option><option value={20}>20分以内</option><option value={30}>30分以内</option></select></label>
          </section>
          <div className="recipe-grid">{recipes.map((recipe) => <article className="recipe-card" key={recipe.id}><div className={`recipe-art recipe-art-${recipe.id}`}>{recipe.imageUrl ? <img src={recipe.imageUrl} alt="" loading="lazy" /> : recipe.emoji}<span className="recipe-match"><CheckCircle2 size={14} /> 食材一致 {recipe.matchPercent}%</span></div><div className="recipe-card-content"><div className="recipe-tags"><span><Clock3 size={13} />{recipe.minutes}分</span><span><ChefHat size={13} />{recipe.difficulty}</span>{recipe.estimatedCostYen !== undefined && <span><Wallet size={13} />約{recipe.estimatedCostYen}円/人</span>}{recipe.usesExpiring > 0 && <span className="expiring-tag"><Flame size={12} />期限間近を活用</span>}</div><h3>{recipe.name}</h3><p className="recipe-description">{recipe.description}</p>{recipe.source && <p className="recipe-source-label">提案元：{recipe.source}</p>}<div className="recipe-matched"><span className="matched-label">使える食材</span><div className="ingredient-tags">{recipe.matchedIngredients.length ? recipe.matchedIngredients.map((ingredient) => <span className="ingredient-tag" key={ingredient}>{ingredient}</span>) : <span className="ingredient-tag muted-tag">登録食材と照合中</span>}</div></div><div className="recipe-card-bottom"><span className="missing-copy">{recipe.missingIngredients.length ? `あと${recipe.missingIngredients.length}品で完成` : '食材がそろっています！'}</span><button className="recipe-detail-button" onClick={() => setSelectedRecipe(recipe)}>作り方を見る <ArrowRight size={15} /></button></div></div></article>)}</div>
          <div className="recipe-footnote"><Sparkles size={15} /><span>{recipeMessage || (recipeSource === 'gemini' ? 'Geminiが登録食材と期限、予算、調理時間をもとに提案しています。材料費は地域や購入店で変わる概算です。' : 'Gemini API未設定時は、アプリ内の節約レシピを表示します。')} {recipeSource === 'gemini' ? 'これはWebサイトのリアルタイム検索ではなく、Geminiによるレシピ生成です。食材名・数量・期限・設定はGoogleへ送信され、無料枠ではサービス改善に利用される場合があります。' : ''}</span></div>
        </>}
        <footer className="page-footer"><span>© 2026 mottainai kitchen</span><span>{databaseMode === 'sqlite' ? 'SQLiteデータベースに保存中' : databaseMode === 'loading' ? '保存先を確認中…' : 'このブラウザに保存中（SQLite未接続）'}</span><span>食材を大切に、毎日のごはんを豊かに。</span></footer>
      </main>

      {notice && <div className="toast"><CircleCheck size={17} />{notice}</div>}
      {showForm && <IngredientModal item={editing} onClose={() => { setShowForm(false); setEditing(null) }} onSave={handleSave} />}
      {selectedRecipe && <RecipeModal recipe={selectedRecipe} pantry={pantry} onClose={() => setSelectedRecipe(null)} />}
    </div>
  )
}

export default App
