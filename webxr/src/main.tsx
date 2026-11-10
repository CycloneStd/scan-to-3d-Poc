async function renderRoute() {
  const pathname = window.location.pathname.replace(/\/+$/, '') || '/'
  if (pathname !== '/login' && pathname !== '/signup') return

  document.body.className = 'login-page bg-surface-base text-surface'
  document.body.innerHTML = '<div id="login-root"></div>'

  const [{ StrictMode, createElement }, { createRoot }, pageModule] =
    await Promise.all([
      import('react'),
      import('react-dom/client'),
      pathname === '/signup'
        ? import('./pages/auth/SignupPage')
        : import('./pages/auth/LoginPage'),
    ])

  const rootElement = document.getElementById('login-root')
  if (!rootElement) throw new Error('Login page root element was not found.')

  createRoot(rootElement).render(
    createElement(StrictMode, null, createElement(pageModule.default)),
  )
}

void renderRoute()
