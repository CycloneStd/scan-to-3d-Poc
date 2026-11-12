import type { FormEvent } from 'react'
import { useState } from 'react'
import { authApi } from '../../services/auth'
import LoginImageCards from '../../components/auth/LoginImageCards'
import cycloneWordmark from '../../assets/cyclone-wordmark.webp'
import '../../styles/components/input.css'
import '../../styles/login.css'

const submitButtonClasses = 'login-submit mirror-button m-button relative box-border inline-flex items-center justify-center border-2 outline-4 outline-offset-0 outline-transparent whitespace-nowrap no-underline transition-all duration-100 ease-linear focus-visible:focus-ring will-change-contents h-14 gap-2 type-component-lg rounded-component-xl border-transparent bg-primary-solid text-primary-on-solid hover:bg-primary-solid-hover'

function PasswordField({ id, label }: { id: string; label: string }) {
  return <div className="m-input relative box-border flex w-full cursor-text flex-row items-center justify-between select-none transition-all duration-100 ease-linear h-14 gap-1.5 rounded-component-xl" data-size="lg">
    <span className="m-input__target" aria-hidden="true" onClick={() => document.getElementById(id)?.focus()} />
    <span className="m-input__field"><span className="m-input__control"><input className="mirror-input" id={id} name={id} type="password" autoComplete="new-password" placeholder={label} minLength={12} required /></span><label className="m-input__label" htmlFor={id}>{label}</label></span>
  </div>
}

export default function ResetPasswordPage() {
  const [resetToken] = useState(() => {
    const token = new URLSearchParams(window.location.search).get('token') || ''
    if (token) window.history.replaceState(null, '', '/reset-password')
    return token
  })
  const [error, setError] = useState('')
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const password = form.elements.namedItem('password') as HTMLInputElement
    const confirmation = form.elements.namedItem('confirm-password') as HTMLInputElement
    confirmation.setCustomValidity(password.value === confirmation.value ? '' : 'Passwords must match.')
    if (!form.reportValidity()) return
    if (!resetToken) { setError('This reset link is invalid or expired. Request a new one.'); return }
    try { await authApi.reset(resetToken, password.value); window.location.assign('/login?reset=complete') }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Password reset failed.') }
  }
  return <main className="login-shell"><LoginImageCards /><a className="login-brand" href="/" aria-label="Cyclone home"><img src={cycloneWordmark} alt="Cyclone" /></a>
    <section className="login-content" aria-labelledby="reset-title">
      <header className="login-heading"><h1 id="reset-title">Reset password</h1><p>Choose a new password for your account.</p></header>
      <form className="login-form" onSubmit={handleSubmit} onInput={(event) => {
        const form = event.currentTarget
        const password = form.elements.namedItem('password') as HTMLInputElement
        const confirmation = form.elements.namedItem('confirm-password') as HTMLInputElement
        confirmation.setCustomValidity(confirmation.value && password.value !== confirmation.value ? 'Passwords must match.' : '')
      }}>
        <PasswordField id="password" label="New password" /><PasswordField id="confirm-password" label="Confirm password" />
        <button className={submitButtonClasses} type="submit" data-mode="solid" data-size="lg" data-variant="primary">Reset password</button>
        {error && <p role="alert" className="login-account-prompt">{error}</p>}
      </form>
    </section>
  </main>
}
