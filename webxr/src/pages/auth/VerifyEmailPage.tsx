import { useEffect, useRef, useState } from 'react'
import LoginImageCards from '../../components/auth/LoginImageCards'
import cycloneWordmark from '../../assets/cyclone-wordmark.webp'
import { authApi } from '../../services/auth'
import '../../styles/components/input.css'
import '../../styles/login.css'

export default function VerifyEmailPage() {
  const [message, setMessage] = useState('Verifying your email…')
  const [token] = useState(() => new URLSearchParams(window.location.search).get('token'))
  const verification = useRef<Promise<void> | null>(null)
  useEffect(() => {
    if (!token) { setMessage('This verification link is invalid or expired.'); return }
    window.history.replaceState(null, '', '/verify-email')
    let active = true
    verification.current ??= authApi.verify(token)
    verification.current.then(() => {
      if (!active) return
      setMessage('Email verified. Taking you to your library…')
      window.location.replace('/library')
    }).catch((error: unknown) => {
      if (active) setMessage(error instanceof Error ? error.message : 'Email verification failed.')
    })
    return () => { active = false }
  }, [token])
  return <main className="login-shell"><LoginImageCards /><a className="login-brand" href="/" aria-label="Cyclone home"><img src={cycloneWordmark} alt="Cyclone" /></a><section className="login-content"><header className="login-heading"><h1>Verify your email</h1><p role="status">{message}</p></header></section></main>
}
