import './styles/components/input.css'
import './styles/login.css'

async function renderRoute() {
  const pathname = window.location.pathname.replace(/\/+$/, '') || '/'
  if (pathname === '/') {
    document.body.dataset.routeReady = 'true'
    return
  }
  const isModelPage = /^\/model\/[^/]+$/.test(pathname)
  const isScanPage = pathname === '/scan'
  const isKnownRoute = pathname === '/login' || pathname === '/signup' || pathname === '/forgot-password' || pathname === '/reset-password' || pathname === '/verify-email' || pathname === '/library' || isModelPage || isScanPage
  const isNotFound = !isKnownRoute

  const isLibraryPage = pathname === '/library' || isModelPage || isScanPage
  if (isLibraryPage) {
    const { authApi } = await import('./services/auth')
    try { await authApi.me() } catch { window.location.replace(`/login?next=${encodeURIComponent(pathname + window.location.search)}`); return }
  }
  document.body.className = `${isLibraryPage || isNotFound ? 'library-page' : 'login-page'} bg-surface-base text-surface`
  document.body.innerHTML = '<div id="app-root"></div>'

  let pagePromise: Promise<{ default: import('react').ComponentType }>
  switch (pathname) {
    case '/signup':
      pagePromise = import('./pages/auth/SignupPage')
      break
    case '/verify-email':
      pagePromise = import('./pages/auth/VerifyEmailPage')
      break
    case '/forgot-password':
      pagePromise = import('./pages/auth/ForgotPasswordPage')
      break
    case '/reset-password':
      pagePromise = import('./pages/auth/ResetPasswordPage')
      break
    case '/login':
      pagePromise = import('./pages/auth/LoginPage')
      break
    default:
      pagePromise = isLibraryPage
        ? import('./pages/LibraryPage')
        : import('./pages/NotFoundPage')
  }

  const [{ StrictMode, createElement }, { createRoot }, pageModule] =
    await Promise.all([
      import('react'),
      import('react-dom/client'),
      pagePromise,
    ])

  const rootElement = document.getElementById('app-root')
  if (!rootElement) throw new Error('Application root element was not found.')

  createRoot(rootElement).render(
    createElement(StrictMode, null, createElement(pageModule.default)),
  )
  requestAnimationFrame(() => { document.body.dataset.routeReady = 'true' })
}

void renderRoute()
