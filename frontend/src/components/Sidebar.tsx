import { CookingPot, Heart, Leaf, ListChecks, Refrigerator, Settings2, ShoppingBasket, Trash2 } from 'lucide-react'
import type { Tab } from '../Kitchen'

export function Sidebar({ activeTab, onTab, pantryCount, shoppingCount, consumed, wasted, onReset }: { activeTab: Tab; onTab: (tab: Tab) => void; pantryCount: number; shoppingCount: number; consumed: number; wasted: number; onReset: () => void }) {
  const link = (tab: Tab, icon: JSX.Element, label: string, count?: number) => (
    <button className={`side-link ${activeTab === tab ? 'active' : ''}`} aria-current={activeTab === tab ? 'page' : undefined} onClick={() => onTab(tab)}>
      {icon}<span className="side-label">{label}</span>{count ? <span className="side-count">{count}</span> : null}
    </button>
  )
  return <aside className="sidebar">
    <div className="brand-lockup"><div className="brand-mark"><Leaf size={23} strokeWidth={2.4} /></div><div><div className="brand-name">mottainai</div><div className="brand-sub">KITCHEN</div></div></div>
    <div className="side-section-label">MENU</div>
    <nav className="side-nav" aria-label="メインメニュー">
      {link('pantry', <Refrigerator size={18} />, '冷蔵庫', pantryCount)}
      {link('recipes', <CookingPot size={18} />, 'レシピ')}
      {link('shopping', <ListChecks size={18} />, '買い物', shoppingCount)}
    </nav>
    <div className="side-section-label side-label-spaced">YOUR KITCHEN</div>
    <div className="side-mini-stat"><div className="mini-stat-icon green"><ShoppingBasket size={17} /></div><div><div className="mini-stat-value">{pantryCount} <small>品</small></div><div className="mini-stat-label">登録中の食材</div></div></div>
    <div className="side-mini-stat"><div className="mini-stat-icon orange"><Heart size={17} /></div><div><div className="mini-stat-value">{consumed} <small>品</small></div><div className="mini-stat-label">使い切った食材</div></div></div>
    <div className="side-mini-stat"><div className="mini-stat-icon red"><Trash2 size={17} /></div><div><div className="mini-stat-value">{wasted} <small>品</small></div><div className="mini-stat-label">今月捨てた食材</div></div></div>
    <div className="sidebar-bottom"><div className="tip-card"><div className="tip-illustration">🌱</div><div className="tip-title">自炊はゆるく、<br />賢く続けよう。</div><div className="tip-copy">食費を抑えて、<br />食材も使い切ろう。</div></div><button className="side-link reset-link" onClick={onReset}><Settings2 size={17} /><span>サンプルに戻す</span></button><div className="sidebar-foot">ひとり暮らしの自炊を応援。</div></div>
  </aside>
}
