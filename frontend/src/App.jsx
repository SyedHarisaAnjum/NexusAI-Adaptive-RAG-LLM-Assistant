import { useCallback, useEffect, useState } from 'react'
import { setAuthToken, setUnauthorizedHandler } from './api.js'
import AuthScreen from './components/AuthScreen.jsx'
import ChatPage from './components/ChatPage.jsx'
import './App.css'

const AUTH_KEY = 'qa-auth'

// localStorage can throw (private mode, blocked storage) - never let that break the app.
function loadAuth() {
  try {
    const raw = localStorage.getItem(AUTH_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveAuth(auth) {
  try {
    if (auth) localStorage.setItem(AUTH_KEY, JSON.stringify(auth))
    else localStorage.removeItem(AUTH_KEY)
  } catch { /* ignore */ }
}

function App() {
  const [auth, setAuth] = useState(() => {
    const saved = loadAuth()
    setAuthToken(saved?.token ?? null)
    return saved
  })

  const handleLogout = useCallback(() => {
    setAuthToken(null)
    saveAuth(null)
    setAuth(null)
  }, [])

  // An expired/invalid token anywhere in the app sends the user back to login.
  useEffect(() => {
    setUnauthorizedHandler(handleLogout)
  }, [handleLogout])

  const handleAuthenticated = (data) => {
    const next = { token: data.access_token, user: data.user }
    setAuthToken(next.token)
    saveAuth(next)
    setAuth(next)
  }

  if (!auth) return <AuthScreen onAuthenticated={handleAuthenticated} />

  // key: remount (fresh state) whenever a different user logs in.
  return <ChatPage key={auth.user.user_id} user={auth.user} onLogout={handleLogout} />
}

export default App
