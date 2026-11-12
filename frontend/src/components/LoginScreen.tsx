import { useState } from 'react'
import type { FormEvent } from 'react'
import { Leaf } from 'lucide-react'
import { apiFetch } from '../api'

export function LoginScreen({ notice, onAuthenticated }: { apiBase: string; notice?: string; onAuthenticated: (token: string, email: string) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await apiFetch<{ token?: string; email?: string }>(`/api/auth/${mode}`, { method: 'POST', body: { email, password } })
      if (!data?.token || !data.email) throw new Error('認証に失敗しました。')
      onAuthenticated(data.token, data.email)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '認証に失敗しました。')
    } finally {
      setLoading(false)
    }
  }

  return <main className="auth-page"><aside className="auth-showcase" aria-hidden="true">
    <div className="auth-showcase-inner">
      <div className="auth-showcase-emoji"><span>🥬</span><span>🥚</span><span>🍅</span><span>🥕</span><span>🍞</span><span>🥛</span></div>
      <h2>食材を、<br />最後までおいしく。</h2>
      <p>大学生の一人暮らしのための、期限管理と節約レシピのキッチンノート。</p>
      <ul className="auth-features">
        <li><span>⏰</span>期限が近い食材をひと目でチェック</li>
        <li><span>🍳</span>冷蔵庫の中身からAIが1人分レシピを提案</li>
        <li><span>🛒</span>足りない食材はそのまま買い物リストへ</li>
      </ul>
    </div>
  </aside><section className="auth-card">
    <div className="auth-brand"><div className="brand-mark"><Leaf size={23} strokeWidth={2.4} /></div><div><div className="brand-name">mottainai</div><div className="brand-sub">KITCHEN</div></div></div>
    <div className="auth-heading"><div className="modal-eyebrow">MY KITCHEN</div><h1>{mode === 'login' ? 'おかえりなさい' : 'キッチンをはじめよう'}</h1><p>{mode === 'login' ? 'ログインして冷蔵庫の中身を確認しましょう。' : 'メールアドレスを登録して食材管理を始めましょう。'}</p></div>
    {notice && !error && <div className="form-notice" role="status">{notice}</div>}
    <form className="auth-form" onSubmit={submit}>
      <label className="form-label">メールアドレス<input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" maxLength={254} required /></label>
      <label className="form-label">パスワード<input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="8文字以上" minLength={8} maxLength={128} required /></label>
      {error && <div className="form-error" role="alert">{error}</div>}
      <button className="primary-button auth-submit" disabled={loading}>{loading ? '確認中…' : mode === 'login' ? 'ログイン' : 'アカウントを作成'}</button>
    </form>
    <button className="auth-switch" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>{mode === 'login' ? 'はじめての方はこちら（新規登録）' : 'すでにアカウントをお持ちの方はこちら'}</button>
  </section></main>
}
