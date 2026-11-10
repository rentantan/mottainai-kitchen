import { useState } from 'react'
import type { FormEvent } from 'react'
import { Leaf } from 'lucide-react'

export function LoginScreen({ apiBase, onAuthenticated }: { apiBase: string; onAuthenticated: (token: string, email: string) => void }) {
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
      const response = await fetch(`${apiBase}/api/auth/${mode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await response.json() as { token?: string; email?: string; detail?: string }
      if (!response.ok || !data.token || !data.email) throw new Error(data.detail || '認証に失敗しました')
      onAuthenticated(data.token, data.email)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '認証に失敗しました。バックエンドを確認してください。')
    } finally {
      setLoading(false)
    }
  }

  return <main className="auth-page"><section className="auth-card"><div className="auth-brand"><div className="brand-mark"><Leaf size={23} strokeWidth={2.4} /></div><div><div className="brand-name">mottainai</div><div className="brand-sub">KITCHEN</div></div></div><div className="auth-heading"><div className="modal-eyebrow">MY KITCHEN</div><h1>{mode === 'login' ? 'おかえりなさい' : 'キッチンをはじめよう'}</h1><p>{mode === 'login' ? 'ログインして冷蔵庫の中身を確認しましょう。' : 'メールアドレスを登録して食材管理を始めましょう。'}</p></div><form className="auth-form" onSubmit={submit}><label className="form-label">メールアドレス<input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" required /></label><label className="form-label">パスワード<input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="8文字以上" minLength={8} required /></label>{error && <div className="form-error">{error}</div>}<button className="primary-button auth-submit" disabled={loading}>{loading ? '確認中…' : mode === 'login' ? 'ログイン' : 'アカウントを作成'}</button></form><button className="auth-switch" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>{mode === 'login' ? 'はじめての方はこちら（新規登録）' : 'すでにアカウントをお持ちの方はこちら'}</button></section></main>
}

