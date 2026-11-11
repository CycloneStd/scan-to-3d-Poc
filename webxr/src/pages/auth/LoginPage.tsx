import type { FormEvent } from 'react'
import LoginImageCards from '../../components/auth/LoginImageCards'
import '../../styles/components/input.css'
import '../../styles/login.css'

const submitButtonClasses = [
  'login-submit',
  'mirror-button',
  'm-button',
  'relative',
  'box-border',
  'inline-flex',
  'items-center',
  'justify-center',
  'border-2',
  'outline-4',
  'outline-offset-0',
  'outline-transparent',
  'whitespace-nowrap',
  'no-underline',
  'transition-all',
  'duration-100',
  'ease-linear',
  'focus-visible:focus-ring',
  'will-change-contents',
  'h-14',
  'gap-2',
  'type-component-lg',
  'rounded-component-xl',
  'border-transparent',
  'bg-primary-solid',
  'text-primary-on-solid',
  'hover:bg-primary-solid-hover',
  'data-[pressed=true]:bg-primary-solid-active',
].join(' ')

type LoginFieldProps = {
  id: string
  label: string
  type: 'email' | 'password'
  autoComplete: string
}

function LoginField({
  id,
  label,
  type,
  autoComplete,
}: LoginFieldProps) {
  const inputClasses = [
    'm-input',
    'relative',
    'box-border',
    'flex',
    'w-full',
    'cursor-text',
    'flex-row',
    'items-center',
    'justify-between',
    'select-none',
    'transition-all',
    'duration-100',
    'ease-linear',
    'will-change-contents',
    'h-14',
    'gap-1.5',
    'rounded-component-xl',
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
            required
          />
        </span>
        <label className="m-input__label" htmlFor={id}>
          {label}
        </label>
      </span>
    </div>
  )
}

export default function LoginPage() {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    window.location.assign('/library')
  }

  return (
    <main className="login-shell">
      <LoginImageCards />
      <section className="login-content" aria-labelledby="login-title">
        <header className="login-heading">
          <h1 id="login-title">Welcome back</h1>
          <p>Sign in to continue to your scans.</p>
        </header>
        <form className="login-form" onSubmit={handleSubmit}>
          <LoginField
            id="email"
            label="Email address"
            type="email"
            autoComplete="email"
          />
          <LoginField
            id="password"
            label="Password"
            type="password"
            autoComplete="current-password"
          />
          <a className="login-forgot-link" href="/forgot-password">
            Forgot password?
          </a>
          <button
            className={submitButtonClasses}
            type="submit"
            data-mode="solid"
            data-size="lg"
            data-variant="primary"
          >
            Continue
          </button>
        </form>
        <p className="login-account-prompt">
          Don’t have an account? <a href="/signup">Create account</a>
        </p>
      </section>
    </main>
  )
}
