import { useRef, useState } from 'react'
import { ArrowRight, Bell, CalendarDays, Settings2, UserCog } from 'lucide-react'
import type { PantryItem } from '../types'
import type { DataStatus, Tab } from '../Kitchen'
import { daysUntil, expiryText, formatQuantity } from '../utils'
import { useDismiss } from '../hooks/useDismiss'

const TAB_LABEL: Record<Tab, string> = { pantry: '冷蔵庫の中身', recipes: 'レシピを探す', shopping: '買い物リスト' }

export function Topbar({ activeTab, email, status, pantryCount, consumed, notificationItems, onNotification, onReset, onLogout, onAccount }: {
  activeTab: Tab; email: string; status: DataStatus; pantryCount: number; consumed: number; notificationItems: PantryItem[]
  onNotification: (days: number) => void; onReset: () => void; onLogout: () => void; onAccount: () => void
}) {
  const [open, setOpen] = useState<'notifications' | 'profile' | null>(null)
  const menusRef = useRef<HTMLDivElement>(null)
  useDismiss(open !== null, () => setOpen(null), menusRef)
  return <header className="topbar">
    <div className="breadcrumb"><span>マイキッチン</span><span className="crumb-slash">/</span><strong>{TAB_LABEL[activeTab]}</strong></div>
    <div className="topbar-right" ref={menusRef}>
      <div className="today-pill"><CalendarDays size={15} /><span>{new Date().toLocaleDateString('ja-JP', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' })}</span></div>
      <div className="topbar-menu-wrap">
        <button className="icon-button" aria-label="期限アラートを開く" aria-expanded={open === 'notifications'} onClick={() => setOpen(open === 'notifications' ? null : 'notifications')}><Bell size={18} />{notificationItems.length > 0 && <span className="notification-dot" />}</button>
        {open === 'notifications' && <div className="topbar-popover notification-popover">
          <div className="popover-heading"><strong>期限アラート</strong><span>{notificationItems.length}件</span></div>
          {notificationItems.length ? <div className="notification-list">{notificationItems.map((item) => { const days = daysUntil(item.expiryDate); return <button className="notification-item" key={item.id} onClick={() => { onNotification(days); setOpen(null) }}><span className="notification-emoji">{item.emoji}</span><span className="notification-copy"><strong>{item.name}</strong><small>{days < 0 ? '期限切れ' : expiryText(days)} · 残り{formatQuantity(item.quantity)}{item.unit}</small></span><ArrowRight size={14} /></button> })}</div> : <p className="popover-empty">期限が近い食材はありません。</p>}
        </div>}
      </div>
      <div className="topbar-menu-wrap">
        <button className="avatar avatar-button" aria-label="アカウントメニューを開く" aria-expanded={open === 'profile'} onClick={() => setOpen(open === 'profile' ? null : 'profile')}>🥑</button>
        {open === 'profile' && <div className="topbar-popover profile-popover">
          <div className="profile-title"><span className="profile-avatar">🥑</span><span><strong>マイキッチン</strong><small>{email}</small></span></div>
          <div className="profile-stats"><span><strong>{pantryCount}</strong>登録中</span><span><strong>{consumed}</strong>使い切り</span></div>
          <div className="storage-status"><span className={`status-dot ${status === 'ready' ? 'is-online' : ''}`} />{status === 'ready' ? 'SQLiteに保存中' : status === 'loading' ? '読み込み中…' : 'オフライン（変更は保存されません）'}</div>
          <button className="profile-reset" onClick={() => { setOpen(null); onAccount() }}><UserCog size={14} />アカウント設定</button>
          <button className="profile-reset" onClick={() => { setOpen(null); onReset() }}><Settings2 size={14} />サンプル食材を入れる</button>
          <button className="profile-logout" onClick={onLogout}>ログアウト</button>
        </div>}
      </div>
    </div>
  </header>
}
