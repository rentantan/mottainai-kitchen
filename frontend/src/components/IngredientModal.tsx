import { useState } from 'react'
import type { FormEvent } from 'react'
import { Check, Sparkles, X } from 'lucide-react'
import type { Category, PantryItem } from '../types'
import { FREEZER_DAYS, categoryEmoji, categoryOptions, dateOffset } from '../data'
import { findFoodPreset } from '../foodPresets'
import type { FoodPreset } from '../foodPresets'
import { useModal } from '../hooks/useModal'

const UNIT_SUGGESTIONS = ['個', '本', '枚', '袋', 'パック', '丁', '玉', '束', '缶', '切れ', 'g', 'kg', 'ml', 'L']
const EXPIRY_SHORTCUTS: { label: string; days: number }[] = [
  { label: '今日', days: 0 }, { label: '明日', days: 1 }, { label: '3日後', days: 3 }, { label: '1週間後', days: 7 }, { label: '2週間後', days: 14 },
]

type Field = 'unit' | 'expiryDate' | 'category'

export function IngredientModal({ item, initialName = '', onClose, onSave }: { item: PantryItem | null; initialName?: string; onClose: () => void; onSave: (item: Omit<PantryItem, 'id' | 'createdAt'>) => void }) {
  // For a new item, start from the typical values for the given name (e.g. coming from the shopping list).
  const [preset, setPreset] = useState<FoodPreset | null>(() => item ? null : findFoodPreset(initialName))
  const [name, setName] = useState(item?.name ?? initialName)
  const [quantity, setQuantity] = useState(String(item?.quantity ?? 1))
  const [unit, setUnit] = useState(item?.unit ?? preset?.unit ?? '個')
  const [expiryDate, setExpiryDate] = useState(item?.expiryDate ?? dateOffset(preset?.days ?? 3))
  const [category, setCategory] = useState<Category>(item?.category ?? preset?.category ?? '野菜・果物')
  // Fields the user changed by hand are never overwritten by the name-based guess.
  const [touched, setTouched] = useState<ReadonlySet<Field>>(() => new Set())
  const [note, setNote] = useState(item?.note ?? '')
  const [frozen, setFrozen] = useState(item?.frozen ?? false)
  const [price, setPrice] = useState(item?.priceYen != null ? String(item.priceYen) : '')
  const [validation, setValidation] = useState('')
  const panelRef = useModal<HTMLElement>(onClose)

  // Keep a custom emoji only while the category is unchanged; otherwise follow the guess or the category.
  const emoji = item && item.category === category ? item.emoji
    : preset && preset.category === category ? preset.emoji
      : categoryEmoji[category]

  const touch = (field: Field) => setTouched((current) => new Set(current).add(field))

  function changeName(value: string) {
    setName(value)
    if (item) return
    const next = findFoodPreset(value)
    setPreset(next)
    if (!next) return
    if (!touched.has('unit')) setUnit(next.unit)
    if (!touched.has('expiryDate')) setExpiryDate(dateOffset(frozen ? FREEZER_DAYS : next.days))
    if (!touched.has('category')) setCategory(next.category)
  }

  function changeFrozen(value: boolean) {
    setFrozen(value)
    // Frozen food keeps for about a month; follow that unless the date was set by hand.
    if (!touched.has('expiryDate')) setExpiryDate(dateOffset(value ? FREEZER_DAYS : preset?.days ?? 3))
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) { setValidation('食材名を入力してください。'); return }
    if (!Number.isFinite(Number(quantity)) || Number(quantity) <= 0) { setValidation('残量は0より大きい数字にしてください。'); return }
    if (!unit.trim()) { setValidation('単位を入力してください。'); return }
    if (!expiryDate) { setValidation('期限を入力してください。'); return }
    const priceYen = price.trim() === '' ? null : Number(price)
    if (priceYen !== null && !(Number.isInteger(priceYen) && priceYen >= 0 && priceYen <= 100000)) { setValidation('値段は0〜100000の整数（円）で入力してください。'); return }
    onSave({ name: name.trim(), quantity: Number(quantity), unit: unit.trim(), expiryDate, category, emoji, note: note.trim(), frozen, priceYen })
  }
  return <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}><section ref={panelRef} className="modal-panel" role="dialog" aria-modal="true" aria-labelledby="ingredient-modal-title">
    <div className="modal-header"><div><div className="modal-eyebrow">YOUR PANTRY</div><h2 id="ingredient-modal-title">{item ? '食材を編集' : '食材を追加'}</h2><p>食材の情報を入力してください。</p></div><button className="modal-close" onClick={onClose} aria-label="閉じる"><X size={19} /></button></div>
    <form onSubmit={submit} className="ingredient-form">
      <label className="form-label">食材名 <span>必須</span><input autoFocus value={name} maxLength={80} onChange={(e) => changeName(e.target.value)} placeholder="例：キャベツ" /></label>
      {preset && <p className="preset-hint" role="status"><Sparkles size={13} />{emoji} よくある単位・カテゴリ・期限の目安を入れました。パッケージの表示に合わせて直してください。</p>}
      <div className="form-two-col">
        <label className="form-label">残量<input type="number" inputMode="decimal" min="0.01" step="any" max={100000} value={quantity} onChange={(e) => setQuantity(e.target.value)} /></label>
        <label className="form-label">単位<input list="unit-suggestions" value={unit} maxLength={20} onChange={(e) => { setUnit(e.target.value); touch('unit') }} placeholder="個、g、本など" /><datalist id="unit-suggestions">{UNIT_SUGGESTIONS.map((option) => <option key={option} value={option} />)}</datalist></label>
      </div>
      <div className="form-label">
        <label htmlFor="ingredient-expiry">賞味・消費期限 <span>必須</span></label>
        <input id="ingredient-expiry" type="date" value={expiryDate} onChange={(e) => { setExpiryDate(e.target.value); touch('expiryDate') }} />
        <div className="expiry-shortcuts" role="group" aria-label="期限をすばやく選ぶ">{EXPIRY_SHORTCUTS.map((shortcut) => {
          const value = dateOffset(shortcut.days)
          return <button type="button" key={shortcut.label} className={expiryDate === value ? 'selected' : ''} aria-pressed={expiryDate === value} onClick={() => { setExpiryDate(value); touch('expiryDate') }}>{shortcut.label}</button>
        })}</div>
      </div>
      <label className="frozen-toggle"><input type="checkbox" checked={frozen} onChange={(e) => changeFrozen(e.target.checked)} /><span>❄️ 冷凍保存している<small>期限の目安が約1か月になります。使う前に解凍してください</small></span></label>
      <label className="form-label">カテゴリ<select value={category} onChange={(e) => { setCategory(e.target.value as Category); touch('category') }}>{categoryOptions.map((option) => <option key={option} value={option}>{categoryEmoji[option]} {option}</option>)}</select></label>
      <details className="form-optional" open={Boolean(item?.priceYen != null || item?.note)}>
        <summary>値段・メモ <small>任意</small></summary>
        <div className="form-optional-body">
          <label className="form-label">値段 <small>円</small><input type="number" inputMode="numeric" min="0" max={100000} step="1" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="例：198" /></label>
          <p className="price-hint">値段を入れておくと、捨ててしまったときに「もったいない記録」へ金額で残ります。</p>
          <label className="form-label">メモ <small>300文字まで</small><textarea rows={2} value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} placeholder="例：開封済み、冷凍保存中..." /></label>
        </div>
      </details>
      {validation && <div className="form-error" role="alert">{validation}</div>}
      <div className="modal-actions sticky-actions"><button type="button" className="cancel-button" onClick={onClose}>キャンセル</button><button type="submit" className="primary-button"><Check size={16} />{item ? '変更を保存' : '食材を追加'}</button></div>
    </form>
  </section></div>
}
