import { useState } from 'react'
import type { FormEvent } from 'react'
import { Check, X } from 'lucide-react'
import type { PantryItem } from '../types'
import { formatQuantity } from '../utils'
import { useModal } from '../hooks/useModal'

/** Ask how much was used: presets (1 unit / half / all) or a custom amount. */
export function ConsumeModal({ item, onClose, onConsume }: { item: PantryItem; onClose: () => void; onConsume: (amount: number) => void }) {
  const [custom, setCustom] = useState('')
  const [error, setError] = useState('')
  const panelRef = useModal<HTMLElement>(onClose)
  const presets: { label: string; amount: number }[] = []
  if (item.quantity > 1) presets.push({ label: `1${item.unit}`, amount: 1 })
  if (item.quantity > 1 || item.quantity === 1 && !['個', '本', '枚', '丁', '缶', '玉'].includes(item.unit)) presets.push({ label: '半分', amount: item.quantity / 2 })
  presets.push({ label: `全部（${formatQuantity(item.quantity)}${item.unit}）`, amount: item.quantity })

  function submit(event: FormEvent) {
    event.preventDefault()
    const value = Number(custom)
    if (!Number.isFinite(value) || value <= 0) { setError('0より大きい数字を入力してください。'); return }
    onConsume(Math.min(value, item.quantity))
  }

  return <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}><section ref={panelRef} className="modal-panel consume-panel" role="dialog" aria-modal="true" aria-labelledby="consume-modal-title">
    <div className="modal-header"><div><div className="modal-eyebrow">USE IT UP</div><h2 id="consume-modal-title">{item.emoji} {item.name}をどれくらい使った？</h2><p>残り {formatQuantity(item.quantity)}{item.unit}</p></div><button className="modal-close" onClick={onClose} aria-label="閉じる"><X size={19} /></button></div>
    <div className="ingredient-form">
      <div className="consume-presets">{presets.map((preset) => <button key={preset.label} type="button" className="consume-preset" onClick={() => onConsume(preset.amount)}>{preset.label}</button>)}</div>
      <form onSubmit={submit} className="consume-custom">
        <label className="form-label">量を入力<div className="consume-input"><input type="number" inputMode="decimal" min="0.01" step="any" value={custom} onChange={(e) => { setCustom(e.target.value); setError('') }} placeholder="例：100" /><span>{item.unit}</span></div></label>
        <button type="submit" className="primary-button"><Check size={16} />記録する</button>
      </form>
      {error && <div className="form-error" role="alert">{error}</div>}
    </div>
  </section></div>
}
