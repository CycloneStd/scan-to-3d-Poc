import type { FormEvent } from 'react'
import LoginImageCards from '../../components/auth/LoginImageCards'
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
  type: 'email' | 'password'
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
            minLength={type === 'password' ? 8 : undefined}
            required
          />
        </span>
        <label className="m-input__label" htmlFor={id}>{label}</label>
      </span>
    </div>
  )
}

export default function SignupPage() {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const password = form.elements.namedItem('password') as HTMLInputElement
    const confirmation = form.elements.namedItem('confirm-password') as HTMLInputElement
    confirmation.setCustomValidity(
      confirmation.value === password.value ? '' : 'Passwords must match.',
    )
    form.reportValidity()
  }

  return (
    <main className="login-shell signup-shell">
      <LoginImageCards />
      <section className="login-content" aria-labelledby="signup-title">
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
            Create account
          </button>
        </form>
        <p className="login-account-prompt">
          Already have an account? <a href="/login">Log in</a>
        </p>
      </section>
    </main>
  )
}
