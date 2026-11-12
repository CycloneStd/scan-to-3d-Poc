import type { FormEvent } from 'react'
import { useState } from 'react'
import { authApi } from '../../services/auth'
import LoginImageCards from '../../components/auth/LoginImageCards'
import cycloneWordmark from '../../assets/cyclone-wordmark.webp'
import '../../styles/components/input.css'
import '../../styles/login.css'

const submitButtonClasses = 'login-submit mirror-button m-button relative box-border inline-flex items-center justify-center border-2 outline-4 outline-offset-0 outline-transparent whitespace-nowrap no-underline transition-all duration-100 ease-linear focus-visible:focus-ring will-change-contents h-14 gap-2 type-component-lg rounded-component-xl border-transparent bg-primary-solid text-primary-on-solid hover:bg-primary-solid-hover'

function EmailField() {
  return <div className="m-input relative box-border flex w-full cursor-text flex-row items-center justify-between select-none transition-all duration-100 ease-linear h-14 gap-1.5 rounded-component-xl" data-size="lg">
    <span className="m-input__target" aria-hidden="true" onClick={() => document.getElementById('email')?.focus()} />
    <span className="m-input__field"><span className="m-input__control"><input className="mirror-input" id="email" name="email" type="email" autoComplete="email" placeholder="Email address" required /></span><label className="m-input__label" htmlFor="email">Email address</label></span>
  </div>
}

export default function ForgotPasswordPage() {
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true); setError('')
    try { await authApi.forgot((event.currentTarget.elements.namedItem('email') as HTMLInputElement).value); setSubmitted(true) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not submit request.') }
    finally { setBusy(false) }
  }
  return <main className="login-shell"><LoginImageCards /><a className="login-brand" href="/" aria-label="Cyclone home"><img src={cycloneWordmark} alt="Cyclone" /></a>
    <section className="login-content" aria-labelledby="forgot-title">
      {submitted ? <header className="login-heading"><h1 id="forgot-title">Check your email</h1><p>If an account exists for that address, you’ll receive a password reset link shortly.</p></header> : <>
        <header className="login-heading"><h1 id="forgot-title">Forgot password?</h1><p>Enter your email address to request a reset link.</p></header>
        <form className="login-form" onSubmit={handleSubmit}><EmailField /><button className={submitButtonClasses} disabled={busy} type="submit" data-mode="solid" data-size="lg" data-variant="primary">{busy ? 'Please wait…' : 'Continue'}</button>{error && <p role="alert" className="login-account-prompt">{error}</p>}</form>
      </>}
    </section>
  </main>
}
