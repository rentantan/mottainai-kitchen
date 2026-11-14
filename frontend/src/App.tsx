import { useState } from 'react'
import { API_BASE, AUTH_EMAIL_KEY, AUTH_TOKEN_KEY } from './data'
import { apiFetch } from './api'
import { LoginScreen } from './components/LoginScreen'
import { Kitchen } from './Kitchen'
import { PREFS_KEY } from './hooks/useRecipes'
import { clearLocalData } from './utils'

function App() {
  const [authToken, setAuthToken] = useState(() => localStorage.getItem(AUTH_TOKEN_KEY) || '')
  const [authEmail, setAuthEmail] = useState(() => localStorage.getItem(AUTH_EMAIL_KEY) || '')
  const [loginNotice, setLoginNotice] = useState('')

  function handleAuthenticated(token: string, email: string) {
    localStorage.setItem(AUTH_TOKEN_KEY, token)
    localStorage.setItem(AUTH_EMAIL_KEY, email)
    setLoginNotice('')
    setAuthToken(token)
    setAuthEmail(email)
  }

  function clearSession(notice = '') {
    localStorage.removeItem(AUTH_TOKEN_KEY)
    localStorage.removeItem(AUTH_EMAIL_KEY)
    setAuthToken('')
    setAuthEmail('')
    setLoginNotice(notice)
  }

  function handleLogout() {
    void apiFetch('/api/auth/logout', { token: authToken, method: 'POST' }).catch(() => undefined)
    clearSession()
  }

  if (!authToken) return <LoginScreen apiBase={API_BASE} notice={loginNotice} onAuthenticated={handleAuthenticated} />
  // key={authToken}: switching accounts remounts Kitchen, so no state from the previous user survives.
  return <Kitchen key={authToken} token={authToken} email={authEmail} onLogout={handleLogout} onSessionExpired={() => clearSession('ログインの有効期限が切れました。もう一度ログインしてください。')}
    onAccountDeleted={() => { clearLocalData(authEmail, [PREFS_KEY]); clearSession('アカウントとすべてのデータを削除しました。ご利用ありがとうございました。') }} />
}

export default App
