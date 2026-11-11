import { useMemo, useState } from 'react'
import { AlertTriangle, ArrowLeft, Check, ChefHat, Clock3, ListPlus, Plus, ShoppingBasket, Utensils, Wallet, X } from 'lucide-react'
import type { PantryItem, Recipe } from '../types'
import { daysUntil, expiryText, formatQuantity, guessAmount, isStaple, pantryMatchesFor } from '../utils'

type CookLine = { item: PantryItem; detail: string; checked: boolean; amount: string }

export function RecipeModal({ recipe, pantry, staples, busy, onClose, onAddToShopping, onCooked }: {
  recipe: Recipe
  pantry: PantryItem[]
  staples: string[]
  busy: boolean
  onClose: () => void
  onAddToShopping: (names: string[]) => void
  onCooked: (entries: { id: string; amount: number }[]) => void
}) {
  const rows = useMemo(() => recipe.ingredients.map((ingredient, index) => {
    const detail = recipe.ingredientDetails?.[index] || ingredient
    const stock = pantryMatchesFor(ingredient, pantry)[0]
    const status: 'pantry' | 'staple' | 'missing' = stock ? 'pantry' : isStaple(ingredient, staples) ? 'staple' : 'missing'
    return { ingredient, detail, stock, status }
  }), [recipe, pantry, staples])
  const missing = rows.filter((row) => row.status === 'missing').map((row) => row.ingredient)
  const [cookLines, setCookLines] = useState<CookLine[] | null>(null)

  function startCooking() {
    const seen = new Set<string>()
    const lines: CookLine[] = []
    for (const row of rows) {
      if (!row.stock || seen.has(row.stock.id)) continue
      seen.add(row.stock.id)
      const guess = guessAmount(row.detail, row.stock.unit)
      const amount = guess === null ? '' : formatQuantity(Math.min(guess, row.stock.quantity))
      lines.push({ item: row.stock, detail: row.detail, checked: guess !== null, amount })
    }
    setCookLines(lines)
  }

  function updateLine(index: number, patch: Partial<CookLine>) {
    setCookLines((current) => current && current.map((line, i) => i === index ? { ...line, ...patch } : line))
  }

  const cookEntries = (cookLines ?? []).filter((line) => line.checked && Number(line.amount) > 0)
    .map((line) => ({ id: line.item.id, amount: Math.min(Number(line.amount), line.item.quantity) }))
  const cookInvalid = (cookLines ?? []).some((line) => line.checked && !(Number(line.amount) > 0))

  return <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}><section className="modal-panel recipe-modal-panel" role="dialog" aria-modal="true" aria-labelledby="recipe-modal-title">
    <div className="recipe-modal-hero"><div className="recipe-modal-emoji">{recipe.emoji}</div><button className="modal-close recipe-modal-close" onClick={onClose} aria-label="閉じる"><X size={19} /></button><div className="modal-eyebrow">RECIPE IDEA</div><h2 id="recipe-modal-title">{recipe.name}</h2><p>{recipe.description}</p><div className="recipe-modal-meta"><span><Clock3 size={14} />約{recipe.minutes}分</span><span><ChefHat size={14} />{recipe.difficulty}</span><span><Wallet size={14} />約{recipe.estimatedCostYen ?? '—'}円/人</span><span>1人分</span></div></div>
    {cookLines === null ? <div className="recipe-modal-body">
      <h3><ShoppingBasket size={17} />材料の目安</h3>
      <div className="recipe-ingredient-list">{rows.map((row, index) => <div className="recipe-ingredient-row" key={`${row.ingredient}-${index}`}>
        <span className={`ingredient-status ${row.status !== 'missing' ? 'have-it' : ''}`}>{row.status !== 'missing' ? <Check size={13} /> : <Plus size={13} />}</span>
        <span>{row.detail}</span>
        <span className={`ingredient-status-label ${row.status !== 'missing' ? 'have-text' : ''}`}>{row.status === 'pantry' ? '冷蔵庫にある' : row.status === 'staple' ? '常備調味料' : '買い足し'}</span>
      </div>)}</div>
      {missing.length > 0 && <button className="outline-button recipe-shopping-button" onClick={() => onAddToShopping(missing)} disabled={busy}><ListPlus size={16} />買い足し{missing.length}品を買い物リストに追加</button>}
      <h3 className="steps-heading"><Utensils size={17} />作り方</h3>
      {recipe.steps.length ? <ol className="recipe-steps">{recipe.steps.map((step, index) => <li key={index}><span>{index + 1}</span><p>{step}</p></li>)}</ol> : <p className="recipe-external-note">作り方の情報が取得できませんでした。別のレシピを提案し直してください。</p>}
      <div className="recipe-safety-note"><AlertTriangle size={15} /><p>期限切れの食材は状態を確認し、異臭・変色などがある場合は使用しないでください。肉や卵は十分に加熱してください。</p></div>
      <button className="primary-button recipe-modal-done" onClick={startCooking}><Check size={16} />作った！食材を減らす</button>
    </div> : <div className="recipe-modal-body">
      <h3><ChefHat size={17} />使った食材を冷蔵庫から減らす</h3>
      {cookLines.length ? <>
        <p className="cook-hint">分量はレシピから推測しています。実際に使った量に直してください。</p>
        <div className="cook-list">{cookLines.map((line, index) => <div className={`cook-row ${line.checked ? '' : 'cook-row-off'}`} key={line.item.id}>
          <label className="cook-check"><input type="checkbox" checked={line.checked} onChange={(e) => updateLine(index, { checked: e.target.checked })} /><span className="cook-emoji">{line.item.emoji}</span><span className="cook-name"><strong>{line.item.name}</strong><small>残り{formatQuantity(line.item.quantity)}{line.item.unit} · {expiryText(daysUntil(line.item.expiryDate))} · レシピ：{line.detail}</small></span></label>
          <div className="consume-input cook-amount"><input type="number" inputMode="decimal" min="0.01" step="any" aria-label={`${line.item.name}の使用量`} value={line.amount} onChange={(e) => updateLine(index, { amount: e.target.value, checked: true })} placeholder="量" /><span>{line.item.unit}</span></div>
        </div>)}</div>
        {cookInvalid && <div className="form-error" role="alert">チェックした食材には使った量を入力してください。</div>}
      </> : <p className="recipe-external-note">冷蔵庫に登録された食材はこのレシピに使われていません。</p>}
      <div className="modal-actions cook-actions">
        <button type="button" className="cancel-button" onClick={() => setCookLines(null)}><ArrowLeft size={14} />戻る</button>
        <button type="button" className="primary-button" disabled={busy || cookInvalid || cookEntries.length === 0} onClick={() => onCooked(cookEntries)}><Check size={16} />{cookEntries.length}品を減らす</button>
      </div>
    </div>}
  </section></div>
}
