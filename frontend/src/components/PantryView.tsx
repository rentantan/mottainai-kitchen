import { useMemo, useRef, useState } from 'react'
import { AlertTriangle, ArrowRight, Check, ChevronDown, CircleCheck, Clock3, Flame, Leaf, ListFilter, Pencil, Plus, Refrigerator, Search, ShoppingBasket, Snowflake, Sparkles, Trash2 } from 'lucide-react'
import type { PantryFilter, PantryItem, WasteSummary } from '../types'
import { categoryEmoji, categoryOptions, FREEZABLE_CATEGORIES } from '../lib/constants'
import { daysUntil, expiryClass, expiryText } from '../lib/dates'
import { formatQuantity } from '../lib/format'
import { normalize } from '../lib/ingredients'
import { useDismiss } from '../hooks/useDismiss'
import { WastePanel } from './WastePanel'

/** Not expired, not already frozen, and a kind of food that freezes well. */
export const canFreeze = (item: PantryItem) => !item.frozen && daysUntil(item.expiryDate) >= 0 && FREEZABLE_CATEGORIES.includes(item.category)

export function PantryView({ pantry, loading, filter, onFilter, waste, consumed, onAdd, onEdit, onConsume, onDelete, onShowRecipes, onFreeze, onLoadSample, onClearAll }: {
  pantry: PantryItem[]; loading: boolean; filter: PantryFilter; onFilter: (filter: PantryFilter) => void; waste: WasteSummary; consumed: number
  onAdd: () => void; onEdit: (item: PantryItem) => void; onConsume: (item: PantryItem) => void; onDelete: (item: PantryItem) => void; onShowRecipes: () => void
  onFreeze: (item: PantryItem, frozen: boolean) => void; onLoadSample: () => void; onClearAll: () => void
}) {
  const [query, setQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('すべて')
  const [showCategoryMenu, setShowCategoryMenu] = useState(false)
  const categoryMenuRef = useRef<HTMLDivElement>(null)
  useDismiss(showCategoryMenu, () => setShowCategoryMenu(false), categoryMenuRef)

  const sortedPantry = useMemo(() => [...pantry].sort((a, b) => a.expiryDate.localeCompare(b.expiryDate)), [pantry])
  const expiredCount = pantry.filter((item) => daysUntil(item.expiryDate) < 0).length
  const soonCount = pantry.filter((item) => { const d = daysUntil(item.expiryDate); return d >= 0 && d <= 3 }).length
  const expiringItems = sortedPantry.filter((item) => daysUntil(item.expiryDate) <= 3).slice(0, 4)
  const visibleItems = sortedPantry.filter((item) => {
    const days = daysUntil(item.expiryDate)
    return normalize(item.name).includes(normalize(query))
      && (categoryFilter === 'すべて' || item.category === categoryFilter)
      && (filter === 'all' || (filter === 'urgent' && days >= 0 && days <= 3) || (filter === 'expired' && days < 0))
  })
  const focusList = (next: PantryFilter) => {
    onFilter(filter === next ? 'all' : next)
    document.getElementById('pantry-list')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  const isEmpty = !loading && pantry.length === 0
  const stat = (value: number) => loading ? <span className="skeleton skeleton-number" aria-hidden /> : <>{value}<span>品</span></>

  return <>
    <section className="welcome-row"><div><div className="eyebrow"><span className="eyebrow-dot" /> YOUR DAILY KITCHEN</div><h1>大学生の一人暮らし、<span>冷蔵庫を把握できてる？</span></h1><p className="page-subtitle">食費を抑えながら、食材をムダなく使い切ろう。</p></div><button className="primary-button" onClick={onAdd}><Plus size={18} />食材を追加</button></section>

    <section className="stats-grid" aria-busy={loading}>
      <div className="stat-card"><div className="stat-top"><span className="stat-label">登録中の食材</span><span className="stat-icon pale-green"><ShoppingBasket size={18} /></span></div><div className="stat-number">{stat(pantry.length)}</div><div className="stat-bottom"><span className="stat-caption">冷蔵庫・食品棚の合計</span><span className="stat-trend"><Leaf size={13} />管理中</span></div></div>
      <div className={`stat-card ${soonCount ? 'highlight-stat' : ''}`}><div className="stat-top"><span className="stat-label">期限が近い食材</span><span className="stat-icon pale-orange"><Clock3 size={18} /></span></div><div className="stat-number">{stat(soonCount)}</div><div className="stat-bottom"><span className="stat-caption">3日以内に使おう</span><button className="text-action orange-text" onClick={() => focusList('urgent')}>確認する <ArrowRight size={13} /></button></div></div>
      <div className="stat-card"><div className="stat-top"><span className="stat-label">期限切れ</span><span className="stat-icon pale-red"><AlertTriangle size={18} /></span></div><div className="stat-number">{stat(expiredCount)}</div><div className="stat-bottom"><span className="stat-caption">状態を確認してください</span><button className="text-action red-text" onClick={() => focusList('expired')}>確認する <ArrowRight size={13} /></button></div></div>
    </section>

    {isEmpty ? <section className="onboarding-card" aria-labelledby="onboarding-title">
      <div className="onboarding-emoji" aria-hidden>🧊</div>
      <h2 id="onboarding-title">まずは冷蔵庫の中身を登録しよう</h2>
      <p>買ってきた食材を登録すると、期限が近いものを教えてくれて、その食材で作れる1人分レシピをAIが提案します。</p>
      <ol className="onboarding-steps">
        <li><span>1</span>食材名を入れると、単位や期限の目安は自動で入ります</li>
        <li><span>2</span>期限が近づいたら「使った！」か「冷凍する」</li>
        <li><span>3</span>レシピの足りない食材は買い物リストへ</li>
      </ol>
      <div className="onboarding-actions">
        <button className="primary-button" onClick={onAdd}><Plus size={17} />食材を登録する</button>
        <button className="outline-button" onClick={onLoadSample}><Sparkles size={15} />サンプルで試してみる</button>
      </div>
    </section> : <>
    <section className="urgent-section">
      <div className="section-heading"><div><div className="section-title-with-icon"><div className="section-icon urgent-icon"><Flame size={19} /></div><h2>そろそろ使い切ろう</h2><span className="section-count">{soonCount + expiredCount}</span></div><p className="section-description">期限が近い食材から、今日の献立を考えよう。</p></div><button className="subtle-link" onClick={onShowRecipes}>レシピを見る <ArrowRight size={15} /></button></div>
      {loading ? <div className="urgent-grid">{[0, 1, 2, 3].map((i) => <div className="urgent-card skeleton-card" key={i}><span className="skeleton skeleton-emoji" /><span className="skeleton skeleton-line" /><span className="skeleton skeleton-line short" /></div>)}</div>
        : expiringItems.length ? <div className="urgent-grid">{expiringItems.map((item) => { const days = daysUntil(item.expiryDate); return <article className={`urgent-card urgent-tone-${expiryClass(days)} ${days < 0 ? 'urgent-card-expired' : ''}`} key={item.id}><div className="urgent-card-top"><div className="food-emoji">{item.emoji}</div><span className={`expiry-badge ${expiryClass(days)}`}>{expiryText(days)}</span></div><div className="urgent-food-name">{item.name}</div><div className="urgent-food-meta">残り {formatQuantity(item.quantity)}{item.unit} · {item.category}</div><div className="urgent-actions"><button className="use-button" onClick={() => onConsume(item)}><Check size={14} />使った！</button>{canFreeze(item) && <button className="freeze-button" onClick={() => onFreeze(item, true)} title="冷凍して約1か月もたせる"><Snowflake size={14} />冷凍</button>}{days < 0 && <button className="discard-button" onClick={() => onDelete(item)} title="捨てた・削除する" aria-label={`${item.name}を処分する`}><Trash2 size={14} />処分</button>}</div></article> })}</div>
        : <div className="empty-urgent"><div className="empty-check"><CircleCheck size={22} /></div><div><strong>いい感じ！期限が近い食材はありません</strong><p>この調子で、食材を大切に使い切りましょう。</p></div></div>}
    </section>

    <section className="pantry-section" id="pantry-list">
      <div className="section-heading pantry-heading"><div><div className="section-title-with-icon"><div className="section-icon pantry-icon"><Refrigerator size={19} /></div><h2>冷蔵庫の中身</h2><span className="section-count neutral-count">{visibleItems.length}</span></div><p className="section-description">登録した冷蔵庫と食品棚のストックをまとめて管理できます。</p></div><div className="pantry-heading-actions"><button className="text-action red-text" onClick={onClearAll}><Trash2 size={13} />すべて削除</button><button className="outline-button" onClick={onAdd}><Plus size={16} />追加する</button></div></div>
      <div className="list-toolbar">
        <div className="search-box"><Search size={17} /><input aria-label="食材を検索" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="食材名で検索..." /></div>
        <div className="toolbar-right">
          <div className="filter-wrap" ref={categoryMenuRef}><button className={`filter-button ${showCategoryMenu ? 'filter-open' : ''}`} aria-expanded={showCategoryMenu} onClick={() => setShowCategoryMenu(!showCategoryMenu)}><ListFilter size={16} />{categoryFilter}<ChevronDown size={14} /></button>{showCategoryMenu && <div className="dropdown-menu">{['すべて', ...categoryOptions].map((category) => <button key={category} onClick={() => { setCategoryFilter(category); setShowCategoryMenu(false) }}>{category}{categoryFilter === category && <Check size={14} />}</button>)}</div>}</div>
          <div className="segmented-filter">{(['all', 'urgent', 'expired'] as const).map((key) => <button key={key} className={filter === key ? 'selected' : ''} aria-pressed={filter === key} onClick={() => onFilter(key)}>{{ all: 'すべて', urgent: '期限間近', expired: '期限切れ' }[key]}</button>)}</div>
        </div>
      </div>
      {loading ? <div className="pantry-table-wrap skeleton-list" aria-busy>{[0, 1, 2, 3, 4].map((i) => <div className="skeleton-row" key={i}><span className="skeleton skeleton-emoji" /><span className="skeleton skeleton-line" /><span className="skeleton skeleton-line short" /></div>)}</div>
        : visibleItems.length ? <div className="pantry-table-wrap"><table className="pantry-table"><thead><tr><th>食材</th><th>カテゴリ</th><th>残量</th><th>賞味・消費期限</th><th className="actions-head">アクション</th></tr></thead><tbody>{visibleItems.map((item) => { const days = daysUntil(item.expiryDate); return <tr key={item.id}>
          <td className="cell-food"><div className="table-food"><div className="table-emoji">{item.emoji}</div><div><div className="table-food-name">{item.name}{item.frozen && <span className="frozen-badge" title="冷凍保存中"><Snowflake size={11} />冷凍</span>}</div>{item.note && <div className="table-note">{item.note}</div>}</div></div></td>
          <td className="cell-category"><span className="category-chip">{categoryEmoji[item.category] ?? '🛒'} {item.category}</span></td>
          <td className="cell-quantity"><span className="quantity-text">{formatQuantity(item.quantity)}<small>{item.unit}</small></span></td>
          <td className="cell-expiry"><div className="expiry-cell"><span className={`expiry-dot ${expiryClass(days)}`} /><div><div className="expiry-date">{new Date(`${item.expiryDate}T00:00:00`).toLocaleDateString('ja-JP', { month: 'numeric', day: 'numeric' })}</div><div className={`expiry-sub ${expiryClass(days)}`}>{expiryText(days)}</div><div className={`freshness-bar ${expiryClass(days)}`} aria-hidden><span style={{ width: `${Math.max(6, Math.min(100, ((days + 1) / 8) * 100))}%` }} /></div></div></div></td>
          <td className="cell-actions"><div className="row-actions"><button className="small-action consume-action" onClick={() => onConsume(item)} title="使った量を記録"><Check size={14} /><span>使った</span></button>{item.frozen
            ? <button className="icon-row-action freeze-action is-frozen" onClick={() => onFreeze(item, false)} title="解凍した（期限を明日にする）" aria-label={`${item.name}を解凍した`}><Snowflake size={15} /></button>
            : canFreeze(item) ? <button className="icon-row-action freeze-action" onClick={() => onFreeze(item, true)} title="冷凍する（期限を約1か月延ばす）" aria-label={`${item.name}を冷凍する`}><Snowflake size={15} /></button>
            : <span className="icon-row-spacer" aria-hidden />}<button className="icon-row-action" onClick={() => onEdit(item)} title="編集" aria-label={`${item.name}を編集`}><Pencil size={15} /></button><button className="icon-row-action delete-action" onClick={() => onDelete(item)} title="削除" aria-label={`${item.name}を削除`}><Trash2 size={15} /></button></div></td>
        </tr> })}</tbody></table></div>
        : <div className="empty-list"><div className="empty-list-emoji">{query ? '🔎' : '🥦'}</div><h3>{query ? '食材が見つかりませんでした' : 'この条件に合う食材はありません'}</h3><p>検索条件を変えるか、新しい食材を追加しましょう。</p><button className="outline-button" onClick={() => { setQuery(''); onFilter('all'); setCategoryFilter('すべて') }}>条件をリセット</button></div>}
    </section>
    </>}

    {!loading && <WastePanel waste={waste} consumed={consumed} />}
    {!isEmpty && <button className="fab-add" onClick={onAdd} aria-label="食材を追加"><Plus size={24} /></button>}
  </>
}
