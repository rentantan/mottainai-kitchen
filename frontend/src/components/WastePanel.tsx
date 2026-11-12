import { useMemo } from 'react'
import { Lightbulb, Recycle, Trash2 } from 'lucide-react'
import type { WasteSummary } from '../types'
import { formatQuantity, normalize } from '../utils'

/** "もったいない記録": how much food was thrown away, and which items get wasted most often. */
export function WastePanel({ waste, consumed }: { waste: WasteSummary; consumed: number }) {
  // This month's rate: items used up vs. thrown away this month. The all-time rate is shown as a note.
  const monthUsedUp = waste.monthUsedUp ?? 0
  const monthHandled = monthUsedUp + waste.monthCount
  const monthRate = monthHandled ? Math.round((monthUsedUp / monthHandled) * 100) : null
  const handled = consumed + waste.totalCount
  const totalRate = handled ? Math.round((consumed / handled) * 100) : null
  // Most frequently discarded name among the recent entries (only worth pointing out if repeated).
  const repeated = useMemo(() => {
    const counts = new Map<string, { name: string; emoji: string; count: number }>()
    for (const entry of waste.items) {
      const key = normalize(entry.name)
      const current = counts.get(key)
      counts.set(key, { name: entry.name, emoji: entry.emoji, count: (current?.count ?? 0) + 1 })
    }
    const top = [...counts.values()].sort((a, b) => b.count - a.count)[0]
    return top && top.count >= 2 ? top : null
  }, [waste.items])

  return <section className="waste-section" aria-labelledby="waste-title">
    <div className="section-heading"><div><div className="section-title-with-icon"><div className="section-icon waste-icon"><Recycle size={19} /></div><h2 id="waste-title">もったいない記録</h2></div><p className="section-description">「捨てた」を選んで削除した食材を記録します。値段を登録した食材は金額でも記録します。</p></div></div>
    <div className="waste-card">
      <div className="waste-stats">
        <div><span className="waste-stat-label">今月捨てた</span><strong>{waste.monthCount}<small>品</small></strong>{(waste.monthYen ?? 0) > 0 && <span className="waste-stat-note waste-yen">約{waste.monthYen!.toLocaleString()}円分</span>}</div>
        <div><span className="waste-stat-label">これまで</span><strong>{waste.totalCount}<small>品</small></strong>{(waste.totalYen ?? 0) > 0 && <span className="waste-stat-note waste-yen">約{waste.totalYen!.toLocaleString()}円分</span>}</div>
        <div><span className="waste-stat-label">今月の使い切り率</span><strong>{monthRate === null ? '—' : <>{monthRate}<small>%</small></>}</strong><span className="waste-stat-note">今月 使い切り{monthUsedUp}品 / 捨てた{waste.monthCount}品{totalRate !== null && ` · これまで${totalRate}%`}</span></div>
      </div>
      {repeated && <p className="waste-tip"><Lightbulb size={15} />{repeated.emoji} {repeated.name}を最近{repeated.count}回捨てています。次は少なめに買うか、期限が近づいたら冷蔵庫の一覧の ❄️ で冷凍してみよう。</p>}
      {waste.items.length ? <ul className="waste-list">{waste.items.slice(0, 5).map((entry) => <li key={entry.id}>
        <span className="waste-emoji">{entry.emoji}</span>
        <span className="waste-name"><strong>{entry.name}</strong><small>{formatQuantity(entry.quantity)}{entry.unit}{entry.valueYen != null && ` · 約${entry.valueYen}円`} · 期限 {formatDate(entry.expiryDate)}</small></span>
        <span className="waste-date"><Trash2 size={12} />{formatDate(entry.discardedAt.slice(0, 10))}</span>
      </li>)}</ul>
        : <p className="waste-empty">まだ捨てた食材はありません。この調子！🎉</p>}
    </div>
  </section>
}

function formatDate(isoDate: string) {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString('ja-JP', { month: 'numeric', day: 'numeric' })
}
