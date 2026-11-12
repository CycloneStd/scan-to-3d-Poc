import type { FormEvent } from 'react'
import { useState } from 'react'
import { authApi } from '../../services/auth'
import LoginImageCards from '../../components/auth/LoginImageCards'
import cycloneWordmark from '../../assets/cyclone-wordmark.png'
import '../../styles/components/input.css'
import '../../styles/login.css'

const submitButtonClasses = [
  'login-submit', 'mirror-button', 'm-button', 'relative', 'box-border',
  'inline-flex', 'items-center', 'justify-center', 'border-2', 'outline-4',
  'outline-offset-0', 'outline-transparent', 'whitespace-nowrap', 'no-underline',
  'transition-all', 'duration-100', 'ease-linear', 'focus-visible:focus-ring',
  'will-change-contents', 'h-14', 'gap-2', 'type-component-lg',
  'rounded-component-xl', 'border-transparent', 'bg-primary-solid',
  'text-primary-on-solid', 'hover:bg-primary-solid-hover',
  'data-[pressed=true]:bg-primary-solid-active',
].join(' ')

type SignupFieldProps = {
  id: string
  label: string
  type: 'email' | 'password' | 'text'
  autoComplete: string
}

function SignupField({ id, label, type, autoComplete }: SignupFieldProps) {
  const inputClasses = [
    'm-input', 'relative', 'box-border', 'flex', 'w-full', 'cursor-text',
    'flex-row', 'items-center', 'justify-between', 'select-none',
    'transition-all', 'duration-100', 'ease-linear', 'will-change-contents',
    'h-14', 'gap-1.5', 'rounded-component-xl',
  ].join(' ')

  return (
    <div className={inputClasses} data-size="lg">
      <span
        className="m-input__target"
        aria-hidden="true"
        onClick={() => document.getElementById(id)?.focus()}
      />
      <span className="m-input__field">
        <span className="m-input__control">
          <input
            className="mirror-input"
            id={id}
            name={id}
            type={type}
            autoComplete={autoComplete}
            placeholder={label}
            minLength={type === 'password' ? 12 : undefined}
            required
          />
        </span>
        <label className="m-input__label" htmlFor={id}>{label}</label>
      </span>
    </div>
  )
}

export default function SignupPage() {
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const password = form.elements.namedItem('password') as HTMLInputElement
    const confirmation = form.elements.namedItem('confirm-password') as HTMLInputElement
    confirmation.setCustomValidity(
      confirmation.value === password.value ? '' : 'Passwords must match.',
    )
    if (!form.reportValidity()) return
    setBusy(true); setError('')
    try {
      await authApi.register({ email: (form.elements.namedItem('email') as HTMLInputElement).value, password: password.value, display_name: (form.elements.namedItem('display_name') as HTMLInputElement).value })
      setSubmitted(true)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Account creation failed.') }
    finally { setBusy(false) }
  }

  return (
    <main className="login-shell signup-shell">
      <LoginImageCards />
      <a className="login-brand" href="/" aria-label="Cyclone home">
        <img src={cycloneWordmark} alt="Cyclone" />
      </a>
      <section className="login-content" aria-labelledby="signup-title">
        {submitted ? <header className="login-heading">
          <h1 id="signup-title">Check your email</h1>
          <p>We’ve sent a verification link to your email address. Open it to verify your account, then you can continue to your library.</p>
        </header> : <>
        <header className="login-heading">
          <h1 id="signup-title">Create your account</h1>
          <p>Sign up to get started with your scans.</p>
        </header>
        <form
          className="login-form"
          onSubmit={handleSubmit}
          onInput={(event) => {
            const form = event.currentTarget
            const password = form.elements.namedItem('password') as HTMLInputElement
            const confirmation = form.elements.namedItem('confirm-password') as HTMLInputElement
            confirmation.setCustomValidity(
              confirmation.value && confirmation.value !== password.value
                ? 'Passwords must match.'
                : '',
            )
          }}
        >
          <SignupField id="display_name" label="Your name" type="text" autoComplete="name" />
          <SignupField id="email" label="Email address" type="email" autoComplete="email" />
          <SignupField id="password" label="Password" type="password" autoComplete="new-password" />
          <SignupField id="confirm-password" label="Confirm password" type="password" autoComplete="new-password" />
          <button
            className={submitButtonClasses}
            type="submit"
            data-mode="solid"
            data-size="lg"
            data-variant="primary"
          >
            {busy ? 'Creating account…' : 'Create account'}
          </button>
          {error && <p role="alert" className="login-account-prompt">{error}</p>}
        </form>
        </>}
        {!submitted && <p className="login-account-prompt">
          Already have an account? <a href="/login">Log in</a>
        </p>}
      </section>
    </main>
  )
}
