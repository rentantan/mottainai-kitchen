import { useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowRight, BookmarkCheck, CheckCircle2, ChefHat, Clock3, Flame, Plus, Refrigerator, Sparkles, Wallet, X } from 'lucide-react'
import type { PantryItem, Recipe, SavedRecipe } from '../types'
import { daysUntil, rankSavedRecipes } from '../utils'
import type { Equipment } from '../data'

/** "今日" / "昨日" / "3日前" / "11/2" for the last time a saved recipe was cooked. */
function lastCookedText(iso: string) {
  const days = -daysUntil(iso.slice(0, 10))
  if (days <= 0) return '今日'
  if (days === 1) return '昨日'
  if (days < 7) return `${days}日前`
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : `${date.getMonth() + 1}/${date.getDate()}`
}

const STAPLE_SUGGESTIONS = ['しょうゆ', '塩', 'こしょう', '砂糖', 'サラダ油', 'みりん', '酒', '味噌', 'マヨネーズ', 'ケチャップ', 'ごま油', '酢']

export function RecipesView({ recipes, loading, stale, source, message, budgetYen, onBudget, maxMinutes, onMaxMinutes, equipment, onEquipment, staples, onSaveStaples, savedRecipes, pantry, busy, onRefresh, onSelect, onShowPantry }: {
  recipes: Recipe[]; loading: boolean; stale: boolean; source: 'gemini' | 'local'; message: string
  budgetYen: 300 | 500 | 700; onBudget: (value: 300 | 500 | 700) => void; maxMinutes: 10 | 20 | 30; onMaxMinutes: (value: 10 | 20 | 30) => void
  equipment: Equipment; onEquipment: (value: Equipment) => void
  staples: string[]; onSaveStaples: (names: string[]) => void; savedRecipes: SavedRecipe[]; pantry: PantryItem[]; busy: boolean
  onRefresh: () => void; onSelect: (recipe: Recipe) => void; onShowPantry: () => void
}) {
  const [stapleInput, setStapleInput] = useState('')
  // Re-matched against the fridge on every render (cheap: at most 50), so the marks follow pantry changes and the date.
  const saved = rankSavedRecipes(savedRecipes, pantry, staples)
  const suggestions = STAPLE_SUGGESTIONS.filter((name) => !staples.includes(name))
  function addStaple(event: FormEvent) {
    event.preventDefault()
    const name = stapleInput.trim()
    if (name && !staples.includes(name)) onSaveStaples([...staples, name])
    setStapleInput('')
  }

  return <>
    <section className="welcome-row recipe-welcome"><div><div className="eyebrow"><span className="eyebrow-dot" /> COOK SOMETHING GOOD</div><h1>大学生の自炊を、<span>安く・簡単に。</span></h1><p className="page-subtitle">講義やアルバイトで忙しい日も、一人分・節約・時短。期限が近い食材から献立を考えよう。</p></div><button className="outline-button" onClick={onShowPantry}><Refrigerator size={16} />食材を確認</button></section>
    <div className="recipe-intro"><div className="recipe-intro-icon"><Sparkles size={23} /></div><div><h2>冷蔵庫から、節約レシピをAI提案</h2><p>Geminiが一人分・低予算・短時間で作れる献立を3つ考えます。</p></div>
      <button className={`refresh-recipes ${stale ? 'refresh-stale' : ''}`} onClick={onRefresh} disabled={loading}>{loading ? '提案中…' : stale ? '新しい条件で提案' : '別のレシピを提案'} <Sparkles size={15} /></button></div>
    {stale && <p className="stale-note" role="status">{source === 'local' ? '食材や条件に合わせてアプリ内レシピを選び直しました。「新しい条件で提案」を押すとAIにも提案してもらえます。' : '食材や条件が変わりました。「新しい条件で提案」を押すと反映されます。'}</p>}
    <section className="student-preferences" aria-label="レシピの希望条件">
      <div className="student-preference-label"><span>🎓</span><div><strong>大学生の一人暮らし節約モード</strong><small>1人分・安い食材・少ない洗い物を優先</small></div></div>
      <label>1食の予算<select value={budgetYen} onChange={(event) => onBudget(Number(event.target.value) as 300 | 500 | 700)}><option value={300}>300円以内</option><option value={500}>500円以内</option><option value={700}>700円以内</option></select></label>
      <label>調理時間<select value={maxMinutes} onChange={(event) => onMaxMinutes(Number(event.target.value) as 10 | 20 | 30)}><option value={10}>10分以内</option><option value={20}>20分以内</option><option value={30}>30分以内</option></select></label>
      <label>調理器具<select value={equipment} onChange={(event) => onEquipment(event.target.value as Equipment)}><option value="any">コンロ・レンジ</option><option value="microwave">電子レンジだけ</option></select></label>
      <div className="staples-editor">
        <div className="staples-heading"><strong>常備している調味料</strong><small>ここにある調味料は「買い足し」に数えません</small></div>
        <div className="staple-chips">
          {staples.map((name) => <span className="staple-chip" key={name}>{name}<button aria-label={`${name}を外す`} disabled={busy} onClick={() => onSaveStaples(staples.filter((s) => s !== name))}><X size={12} /></button></span>)}
          <form className="staple-form" onSubmit={addStaple}><input value={stapleInput} maxLength={30} onChange={(e) => setStapleInput(e.target.value)} placeholder="調味料を追加" aria-label="常備調味料を追加" /><button type="submit" disabled={busy || !stapleInput.trim()} aria-label="追加"><Plus size={14} /></button></form>
        </div>
        {suggestions.length > 0 && <div className="staple-suggestions">{suggestions.map((name) => <button key={name} disabled={busy} onClick={() => onSaveStaples([...staples, name])}><Plus size={11} />{name}</button>)}</div>}
      </div>
    </section>
    <div className="recipe-grid" aria-busy={loading}>{loading ? [0, 1, 2].map((i) => <article className="recipe-card skeleton-card" key={i}><div className="recipe-art skeleton" /><div className="recipe-card-content"><span className="skeleton skeleton-line short" /><span className="skeleton skeleton-line" /><span className="skeleton skeleton-line" /></div></article>)
      : recipes.map((recipe, index) => <article className={`recipe-card ${stale && source !== 'local' ? 'recipe-card-stale' : ''}`} key={recipe.id}>
        <div className={`recipe-art recipe-art-${recipe.id} recipe-tone-${index % 3}`}><span className="recipe-plate">{recipe.emoji}</span><span className="recipe-match"><CheckCircle2 size={14} /> 食材一致 {recipe.matchPercent}%</span></div>
        <div className="recipe-card-content">
          <div className="recipe-tags"><span><Clock3 size={13} />{recipe.minutes}分</span><span><ChefHat size={13} />{recipe.difficulty}</span>{recipe.estimatedCostYen !== undefined && <span><Wallet size={13} />約{recipe.estimatedCostYen}円/人</span>}{recipe.usesExpiring > 0 && <span className="expiring-tag"><Flame size={12} />期限間近を活用</span>}{recipe.microwaveOnly && <span>レンジだけ</span>}</div>
          <h3>{recipe.name}</h3><p className="recipe-description">{recipe.description}</p>{recipe.source && <p className="recipe-source-label">提案元：{recipe.source}</p>}
          <div className="recipe-matched"><span className="matched-label">使える食材</span><div className="ingredient-tags">{recipe.matchedIngredients.length ? recipe.matchedIngredients.map((ingredient) => <span className="ingredient-tag" key={ingredient}>{ingredient}</span>) : <span className="ingredient-tag muted-tag">冷蔵庫の食材は使いません</span>}</div></div>
          <div className="recipe-card-bottom"><span className="missing-copy">{recipe.missingIngredients.length ? `あと${recipe.missingIngredients.length}品で完成` : '食材がそろっています！'}</span><button className="recipe-detail-button" onClick={() => onSelect(recipe)}>作り方を見る <ArrowRight size={15} /></button></div>
        </div>
      </article>)}</div>
    {loading && <p className="loading-note" role="status">Geminiがレシピを考えています。混雑時は最大1分ほどかかります…</p>}
    <section className="saved-recipes" aria-labelledby="saved-recipes-title">
      <div className="saved-recipes-heading"><BookmarkCheck size={18} /><h2 id="saved-recipes-title">保存したレシピ</h2>{saved.length > 0 && <span className="saved-count">{saved.length}件</span>}</div>
      {saved.length === 0 ? <p className="saved-empty">気に入ったレシピは「作り方を見る」から保存できます。保存したレシピはAIの提案回数を使わずに、いつでも今の冷蔵庫の中身と照らし合わせて作れます。</p>
        : <><p className="saved-hint">今の冷蔵庫の中身で照らし合わせ、期限が近い食材を使えるものから並べています。</p>
          <ul className="saved-list">{saved.map((recipe) => <li key={recipe.id}><button type="button" className="saved-row" onClick={() => onSelect(recipe)}>
            <span className="saved-emoji">{recipe.emoji}</span>
            <span className="saved-body"><strong>{recipe.name}</strong>{recipe.usesExpiring > 0 && <span className="expiring-tag saved-expiring"><Flame size={12} />期限間近を活用</span>}<small><Clock3 size={12} />{recipe.minutes}分{recipe.estimatedCostYen != null && <> · 約{recipe.estimatedCostYen}円</>} · {recipe.missingIngredients.length ? `買い足し${recipe.missingIngredients.length}品` : '食材がそろっています'}</small>{recipe.cookedCount ? <small className="saved-cooked">{recipe.cookedCount}回作った{recipe.lastCookedAt && <> · 最後は{lastCookedText(recipe.lastCookedAt)}</>}</small> : null}</span>
            <ArrowRight size={15} className="saved-arrow" />
          </button></li>)}</ul></>}
    </section>
    <div className="recipe-footnote"><Sparkles size={15} /><span>{message || (source === 'gemini' ? 'Geminiが登録食材と期限、予算、調理時間をもとに提案しています。材料費は地域や購入店で変わる概算です。' : 'Gemini API未設定時は、アプリ内の節約レシピを表示します。')} {source === 'gemini' ? 'これはWebサイトのリアルタイム検索ではなく、Geminiによるレシピ生成です。食材名・数量・期限・設定はGoogleへ送信され、無料枠ではサービス改善に利用される場合があります。' : ''}</span></div>
  </>
}
