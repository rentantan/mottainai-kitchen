import { useState } from 'react'
import type { FormEvent } from 'react'
import { Check, X } from 'lucide-react'
import type { Category, PantryItem } from '../types'
import { categoryEmoji, categoryOptions, dateOffset } from '../data'

const UNIT_SUGGESTIONS = ['個', '本', '枚', '袋', 'パック', '丁', '玉', '束', '缶', 'g', 'kg', 'ml', 'L']

export function IngredientModal({ item, initialName = '', onClose, onSave }: { item: PantryItem | null; initialName?: string; onClose: () => void; onSave: (item: Omit<PantryItem, 'id' | 'createdAt'>) => void }) {
  const [name, setName] = useState(item?.name ?? initialName)
  const [quantity, setQuantity] = useState(String(item?.quantity ?? 1))
  const [unit, setUnit] = useState(item?.unit ?? '個')
  const [expiryDate, setExpiryDate] = useState(item?.expiryDate ?? dateOffset(3))
  const [category, setCategory] = useState<Category>(item?.category ?? '野菜・果物')
  const [note, setNote] = useState(item?.note ?? '')
  const [validation, setValidation] = useState('')
  // Keep a custom emoji only while the category is unchanged; otherwise follow the new category.
  const emoji = item && item.category === category ? item.emoji : categoryEmoji[category]
  function submit(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) { setValidation('食材名を入力してください。'); return }
    if (!Number.isFinite(Number(quantity)) || Number(quantity) <= 0) { setValidation('残量は0より大きい数字にしてください。'); return }
    if (!unit.trim()) { setValidation('単位を入力してください。'); return }
    if (!expiryDate) { setValidation('期限を入力してください。'); return }
    onSave({ name: name.trim(), quantity: Number(quantity), unit: unit.trim(), expiryDate, category, emoji, note: note.trim() })
  }
  return <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}><section className="modal-panel" role="dialog" aria-modal="true" aria-labelledby="ingredient-modal-title">
    <div className="modal-header"><div><div className="modal-eyebrow">YOUR PANTRY</div><h2 id="ingredient-modal-title">{item ? '食材を編集' : '食材を追加'}</h2><p>食材の情報を入力してください。</p></div><button className="modal-close" onClick={onClose} aria-label="閉じる"><X size={19} /></button></div>
    <form onSubmit={submit} className="ingredient-form">
      <label className="form-label">食材名 <span>必須</span><input autoFocus value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="例：キャベツ" /></label>
      <div className="form-two-col">
        <label className="form-label">残量<input type="number" inputMode="decimal" min="0.01" step="any" max={100000} value={quantity} onChange={(e) => setQuantity(e.target.value)} /></label>
        <label className="form-label">単位<input list="unit-suggestions" value={unit} maxLength={20} onChange={(e) => setUnit(e.target.value)} placeholder="個、g、本など" /><datalist id="unit-suggestions">{UNIT_SUGGESTIONS.map((option) => <option key={option} value={option} />)}</datalist></label>
      </div>
      <label className="form-label">賞味・消費期限 <span>必須</span><input type="date" value={expiryDate} onChange={(e) => setExpiryDate(e.target.value)} /></label>
      <label className="form-label">カテゴリ<select value={category} onChange={(e) => setCategory(e.target.value as Category)}>{categoryOptions.map((option) => <option key={option} value={option}>{categoryEmoji[option]} {option}</option>)}</select></label>
      <label className="form-label">メモ <small>任意・300文字まで</small><textarea rows={2} value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} placeholder="例：開封済み、冷凍保存中..." /></label>
      {validation && <div className="form-error" role="alert">{validation}</div>}
      <div className="modal-actions"><button type="button" className="cancel-button" onClick={onClose}>キャンセル</button><button type="submit" className="primary-button"><Check size={16} />{item ? '変更を保存' : '食材を追加'}</button></div>
    </form>
  </section></div>
}
