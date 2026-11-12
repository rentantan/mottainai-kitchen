import { useState } from 'react'
import type { FormEvent } from 'react'
import { Check, ListChecks, Plus, Refrigerator, Trash2 } from 'lucide-react'
import type { ShoppingItem } from '../types'

/** Checking off and deleting never wait for other saves (see useShopping); adding and "冷蔵庫へ" do. */
export function ShoppingView({ items, busy, onAdd, onToggle, onDelete, onClearChecked, onMoveToPantry }: {
  items: ShoppingItem[]; busy: boolean
  onAdd: (name: string) => void; onToggle: (item: ShoppingItem) => void; onDelete: (item: ShoppingItem) => void
  onClearChecked: () => void; onMoveToPantry: (item: ShoppingItem) => void
}) {
  const [name, setName] = useState('')
  const open = items.filter((item) => !item.checked)
  const done = items.filter((item) => item.checked)
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!name.trim()) return
    onAdd(name.trim())
    setName('')
  }
  const row = (item: ShoppingItem) => <li className={`shopping-row ${item.checked ? 'is-checked' : ''}`} key={item.id}>
    <button className="shopping-check" role="checkbox" aria-checked={item.checked} aria-label={`${item.name}を${item.checked ? '未購入に戻す' : '購入済みにする'}`} onClick={() => onToggle(item)}>{item.checked && <Check size={14} />}</button>
    <span className="shopping-name">{item.name}</span>
    {!item.checked && <button className="small-action" disabled={busy} onClick={() => onMoveToPantry(item)} title="買ったので冷蔵庫に登録"><Refrigerator size={14} /><span>冷蔵庫へ</span></button>}
    <button className="icon-row-action delete-action" onClick={() => onDelete(item)} aria-label={`${item.name}を削除`}><Trash2 size={15} /></button>
  </li>

  return <>
    <section className="welcome-row"><div><div className="eyebrow"><span className="eyebrow-dot" /> SHOPPING LIST</div><h1>買い物リスト</h1><p className="page-subtitle">レシピの「買い足し」から追加できます。買ったら「冷蔵庫へ」で期限ごと登録しよう。</p></div></section>
    <section className="shopping-panel">
      <form className="shopping-form" onSubmit={submit}><input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="例：もやし" aria-label="買うものを追加" /><button className="primary-button" type="submit" disabled={busy || !name.trim()}><Plus size={16} />追加</button></form>
      {items.length > 0 && <div className="shopping-progress" aria-label={`${items.length}件中${done.length}件を購入済み`}><div className="shopping-progress-text"><strong>{done.length}<small> / {items.length}</small></strong><span>{open.length ? `あと${open.length}品` : 'ぜんぶ買えました 🎉'}</span></div><div className="shopping-progress-bar"><span style={{ width: `${(done.length / items.length) * 100}%` }} /></div></div>}
      {items.length === 0 ? <div className="empty-list"><div className="empty-list-emoji"><ListChecks size={28} /></div><h3>買い物リストは空です</h3><p>レシピの詳細から「買い足しを買い物リストに追加」できます。</p></div> : <>
        <ul className="shopping-list">{open.map(row)}</ul>
        {done.length > 0 && <><div className="shopping-done-heading"><span>購入済み {done.length}件</span><button className="text-action red-text" onClick={onClearChecked}><Trash2 size={13} />まとめて削除</button></div><ul className="shopping-list">{done.map(row)}</ul></>}
      </>}
    </section>
  </>
}
