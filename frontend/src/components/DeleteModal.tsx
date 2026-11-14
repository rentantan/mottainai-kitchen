import { Eraser, Trash2, X } from 'lucide-react'
import type { PantryItem } from '../types'
import { daysUntil, expiryText } from '../lib/dates'
import { formatQuantity } from '../lib/format'
import { useModal } from '../hooks/useModal'

export type DeleteReason = 'discarded' | 'removed'

/** Ask why an item is removed, so thrown-away food can be counted in the waste log. */
export function DeleteModal({ item, onClose, onDelete }: { item: PantryItem; onClose: () => void; onDelete: (reason: DeleteReason) => void }) {
  const panelRef = useModal<HTMLElement>(onClose)
  const days = daysUntil(item.expiryDate)
  return <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}><section ref={panelRef} className="modal-panel consume-panel" role="dialog" aria-modal="true" aria-labelledby="delete-modal-title">
    <div className="modal-header"><div><div className="modal-eyebrow">REMOVE ITEM</div><h2 id="delete-modal-title">{item.emoji} {item.name}を削除</h2><p>残り {formatQuantity(item.quantity)}{item.unit} · {expiryText(days)}</p></div><button className="modal-close" onClick={onClose} aria-label="閉じる"><X size={19} /></button></div>
    <div className="ingredient-form">
      {days < 0 && <p className="delete-hint">期限切れです。状態を確認して、食べられないと判断したら「捨てた」を選んでください。</p>}
      <div className="delete-choices">
        <button type="button" className="delete-choice delete-choice-waste" onClick={() => onDelete('discarded')}>
          <Trash2 size={18} /><span><strong>捨てた</strong><small>もったいない記録に残して、次の買い物の参考にします</small></span>
        </button>
        <button type="button" className="delete-choice" onClick={() => onDelete('removed')}>
          <Eraser size={18} /><span><strong>登録ミスなどで削除</strong><small>記録には残しません</small></span>
        </button>
      </div>
      <div className="modal-actions"><button type="button" className="cancel-button" onClick={onClose} autoFocus>キャンセル</button></div>
    </div>
  </section></div>
}
