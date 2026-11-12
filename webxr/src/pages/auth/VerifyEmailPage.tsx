import { useEffect, useState } from 'react'
import LoginImageCards from '../../components/auth/LoginImageCards'
import cycloneWordmark from '../../assets/cyclone-wordmark.png'
import { authApi } from '../../services/auth'
import '../../styles/components/input.css'
import '../../styles/login.css'

export default function VerifyEmailPage() {
  const [message, setMessage] = useState('Verifying your email…')
  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token')
    if (!token) { setMessage('This verification link is invalid or expired.'); return }
    window.history.replaceState(null, '', '/verify-email')
    authApi.verify(token).then(() => {
      setMessage('Email verified. Taking you to your library…')
      window.location.replace('/library')
    }).catch((error: unknown) => setMessage(error instanceof Error ? error.message : 'Email verification failed.'))
  }, [])
  return <main className="login-shell"><LoginImageCards /><a className="login-brand" href="/" aria-label="Cyclone home"><img src={cycloneWordmark} alt="Cyclone" /></a><section className="login-content"><header className="login-heading"><h1>Verify your email</h1><p role="status">{message}</p></header></section></main>
}
