import { useState } from 'react'
import type { FormEvent } from 'react'
import { KeyRound, LogOut, Trash2, X } from 'lucide-react'
import { useModal } from '../hooks/useModal'

type Call = <T>(path: string, options?: { method?: string; body?: unknown }) => Promise<T>

/** Password change, logging out other devices (lost phone, shared PC), and deleting the account. */
export function AccountModal({ email, call, onClose, onDone, onDeleted }: {
  email: string; call: Call; onClose: () => void; onDone: (message: string) => void; onDeleted: () => void
}) {
  const panelRef = useModal<HTMLElement>(onClose)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [deletePassword, setDeletePassword] = useState('')
  const [deleteConfirmed, setDeleteConfirmed] = useState(false)
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)

  async function run(action: () => Promise<void>) {
    setError('')
    setWorking(true)
    try { await action() } catch (cause) { setError(cause instanceof Error ? cause.message : '処理に失敗しました。') } finally { setWorking(false) }
  }

  function changePassword(event: FormEvent) {
    event.preventDefault()
    if (next.length < 8) { setError('新しいパスワードは8文字以上にしてください。'); return }
    if (next !== confirm) { setError('新しいパスワード（確認）が一致しません。'); return }
    void run(async () => {
      await call('/api/auth/password', { method: 'POST', body: { currentPassword: current, newPassword: next } })
      onDone('パスワードを変更しました。ほかの端末はログアウトしました')
      onClose()
    })
  }

  function logoutOthers() {
    void run(async () => {
      const result = await call<{ loggedOut: number }>('/api/auth/logout-others', { method: 'POST' })
      onDone(result.loggedOut ? `ほかの端末（${result.loggedOut}件）をログアウトしました` : 'ほかにログイン中の端末はありませんでした')
      onClose()
    })
  }

  function deleteAccount(event: FormEvent) {
    event.preventDefault()
    void run(async () => {
      await call('/api/auth/account', { method: 'DELETE', body: { password: deletePassword } })
      onDeleted()
    })
  }

  return <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}><section ref={panelRef} className="modal-panel" role="dialog" aria-modal="true" aria-labelledby="account-modal-title">
    <div className="modal-header"><div><div className="modal-eyebrow">ACCOUNT</div><h2 id="account-modal-title">アカウント設定</h2><p>{email}</p></div><button className="modal-close" onClick={onClose} aria-label="閉じる"><X size={19} /></button></div>
    <div className="ingredient-form account-form">
      {error && <div className="form-error" role="alert">{error}</div>}

      <form className="account-section" onSubmit={changePassword}>
        <h3><KeyRound size={16} />パスワードを変更</h3>
        <label className="form-label">現在のパスワード<input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required maxLength={128} /></label>
        <div className="form-two-col">
          <label className="form-label">新しいパスワード<input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} placeholder="8文字以上" required minLength={8} maxLength={128} /></label>
          <label className="form-label">新しいパスワード（確認）<input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required minLength={8} maxLength={128} /></label>
        </div>
        <button type="submit" className="primary-button" disabled={working}>パスワードを変更</button>
      </form>

      <div className="account-section">
        <h3><LogOut size={16} />ほかの端末からログアウト</h3>
        <p className="account-note">スマホをなくしたときや、大学・友だちのPCでログインしたままにしたときに。この端末はログインしたままです。</p>
        <button type="button" className="outline-button" onClick={logoutOthers} disabled={working}>ほかの端末をすべてログアウト</button>
      </div>

      <form className="account-section account-danger" onSubmit={deleteAccount}>
        <h3><Trash2 size={16} />アカウントを削除</h3>
        <p className="account-note">食材・買い物リスト・記録など、すべてのデータが削除されます。元に戻せません。</p>
        <label className="form-label">パスワード<input type="password" autoComplete="current-password" value={deletePassword} onChange={(e) => setDeletePassword(e.target.value)} required maxLength={128} /></label>
        <label className="account-check"><input type="checkbox" checked={deleteConfirmed} onChange={(e) => setDeleteConfirmed(e.target.checked)} />すべてのデータが削除されることを理解しました</label>
        <button type="submit" className="danger-button" disabled={working || !deleteConfirmed || !deletePassword}>アカウントを削除する</button>
      </form>
    </div>
  </section></div>
}
