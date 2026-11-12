import { useState } from 'react'
import { Refrigerator, X } from 'lucide-react'
import type { PantryItem, ShoppingItem } from '../types'
import { dateOffset } from '../data'
import { findFoodPreset } from '../foodPresets'
import { daysUntil, expiryText } from '../utils'
import { useModal } from '../hooks/useModal'

export type StockEntry = { shoppingId: string; item: Omit<PantryItem, 'id' | 'createdAt'> }
/** "1 g" of chicken is never right; start weight / volume units at a typical pack size. */
const DEFAULT_QUANTITY: Record<string, string> = { g: '200', ml: '500' }
type Line = { shopping: ShoppingItem; selected: boolean; quantity: string; unit: string; expiryDate: string }

/**
 * Register several bought items at once. Quantity, unit and expiry start from the usual values
 * for each name (same guesses as the add form), so most rows only need a glance.
 * Items still on the list are selected; items already ticked in the shop can be added too.
 */
export function StockModal({ items, busy, onClose, onSave }: { items: ShoppingItem[]; busy: boolean; onClose: () => void; onSave: (entries: StockEntry[]) => void }) {
  const panelRef = useModal<HTMLElement>(onClose)
  const [lines, setLines] = useState<Line[]>(() => [...items].sort((a, b) => Number(a.checked) - Number(b.checked)).map((shopping) => {
    const preset = findFoodPreset(shopping.name)
    const unit = preset?.unit ?? '個'
    return { shopping, selected: !shopping.checked, quantity: DEFAULT_QUANTITY[unit] ?? '1', unit, expiryDate: dateOffset(preset?.days ?? 3) }
  }))
  const update = (index: number, patch: Partial<Line>) => setLines((current) => current.map((line, i) => i === index ? { ...line, ...patch } : line))
  const chosen = lines.filter((line) => line.selected)
  const invalid = chosen.some((line) => !(Number(line.quantity) > 0) || !line.unit.trim() || !line.expiryDate)

  function save() {
    onSave(chosen.map(({ shopping, quantity, unit, expiryDate }) => {
      const preset = findFoodPreset(shopping.name)
      return {
        shoppingId: shopping.id,
        item: { name: shopping.name, quantity: Number(quantity), unit: unit.trim(), expiryDate, category: preset?.category ?? 'その他', emoji: preset?.emoji ?? '🛒', note: '', frozen: false, priceYen: null },
      }
    }))
  }

  return <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}><section ref={panelRef} className="modal-panel stock-panel" role="dialog" aria-modal="true" aria-labelledby="stock-modal-title">
    <div className="modal-header"><div><div className="modal-eyebrow">BACK FROM SHOPPING</div><h2 id="stock-modal-title">買ったものを冷蔵庫へ</h2><p>買ったものを選んでください。量と期限は目安を入れています。</p></div><button className="modal-close" onClick={onClose} aria-label="閉じる"><X size={19} /></button></div>
    <div className="ingredient-form">
      <ul className="stock-list">{lines.map((line, index) => {
        const preset = findFoodPreset(line.shopping.name)
        return <li key={line.shopping.id} className={`stock-row ${line.selected ? '' : 'stock-row-off'}`}>
          <label className="stock-check"><input type="checkbox" checked={line.selected} onChange={(e) => update(index, { selected: e.target.checked })} /><span className="cook-emoji">{preset?.emoji ?? '🛒'}</span><span className="stock-name"><strong>{line.shopping.name}</strong>{line.shopping.checked && <small>チェック済み</small>}</span></label>
          <div className="stock-fields">
            <div className="consume-input stock-qty"><input type="number" inputMode="decimal" min="0.01" step="any" aria-label={`${line.shopping.name}の量`} value={line.quantity} onChange={(e) => update(index, { quantity: e.target.value, selected: true })} /><input className="stock-unit" aria-label={`${line.shopping.name}の単位`} value={line.unit} maxLength={20} onChange={(e) => update(index, { unit: e.target.value, selected: true })} /></div>
            <label className="stock-date"><input type="date" aria-label={`${line.shopping.name}の期限`} value={line.expiryDate} onChange={(e) => update(index, { expiryDate: e.target.value, selected: true })} /><small>{line.expiryDate ? expiryText(daysUntil(line.expiryDate)) : ''}</small></label>
          </div>
        </li>
      })}</ul>
      {invalid && <div className="form-error" role="alert">選んだ食材の量・単位・期限を入力してください。</div>}
      <p className="price-hint">カテゴリや値段はあとから冷蔵庫の一覧の ✏️ で直せます。</p>
      <div className="modal-actions sticky-actions"><button type="button" className="cancel-button" onClick={onClose}>キャンセル</button><button type="button" className="primary-button" disabled={busy || invalid || chosen.length === 0} onClick={save}><Refrigerator size={16} />{chosen.length}品を登録</button></div>
    </div>
  </section></div>
}
