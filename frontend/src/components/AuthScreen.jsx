import { useState } from 'react'
import { login, register } from '../api.js'

// Optional public demo account so visitors can try the app without signing up.
const DEMO_EMAIL = import.meta.env.VITE_DEMO_EMAIL
const DEMO_PASSWORD = import.meta.env.VITE_DEMO_PASSWORD

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState('login') // 'login' | 'register'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [isBusy, setIsBusy] = useState(false)

  const run = async (action) => {
    setIsBusy(true)
    setError(null)
    try {
      onAuthenticated(await action())
    } catch (err) {
      setError(err.message)
    } finally {
      setIsBusy(false)
    }
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    run(() => (mode === 'login' ? login(email, password) : register(email, password)))
  }

  const switchMode = (next) => {
    setMode(next)
    setError(null)
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>AI Q&amp;A Assistant</h1>
        <p className="auth-subtitle">
          Ask questions about your PDFs and get answers with page-level sources.
        </p>

        <div className="auth-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'login'}
            className={mode === 'login' ? 'active' : ''}
            onClick={() => switchMode('login')}
          >
            Log in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'register'}
            className={mode === 'register' ? 'active' : ''}
            onClick={() => switchMode('register')}
          >
            Create account
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            Email
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              minLength={mode === 'register' ? 8 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {mode === 'register' && <p className="auth-hint">At least 8 characters.</p>}

          {error && <p className="auth-error" role="alert">{error}</p>}

          <button type="submit" className="auth-submit" disabled={isBusy}>
            {isBusy ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}
          </button>
        </form>

        {DEMO_EMAIL && DEMO_PASSWORD && (
          <button
            type="button"
            className="auth-demo"
            disabled={isBusy}
            onClick={() => run(() => login(DEMO_EMAIL, DEMO_PASSWORD))}
          >
            Try the demo account
          </button>
        )}

        <p className="auth-note">Your documents and conversations are private to your account.</p>
      </div>
    </div>
  )
}

export default AuthScreen
