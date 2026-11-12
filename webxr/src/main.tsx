import './styles/components/input.css'
import './styles/login.css'
import { StrictMode, createElement, useEffect } from 'react'

function RouteReady({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    document.body.dataset.routeReady = 'true'
  }, [])
  return children
}

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
    const { ApiRequestError, authApi } = await import('./services/auth')
    try {
      await authApi.me()
    } catch (error) {
      if (!(error instanceof ApiRequestError) || error.status !== 401) throw error
      const next = pathname + window.location.search
      window.location.replace(`/login?next=${encodeURIComponent(next)}`)
      return
    }
  }

  document.body.className = `${isLibraryPage || isNotFound ? 'library-page' : 'login-page'} bg-surface-base text-surface`
  document.body.replaceChildren(Object.assign(document.createElement('div'), { id: 'app-root' }))

  const pageLoaders: Record<string, () => Promise<{ default: import('react').ComponentType }>> = {
    '/signup': () => import('./pages/auth/SignupPage'),
    '/verify-email': () => import('./pages/auth/VerifyEmailPage'),
    '/forgot-password': () => import('./pages/auth/ForgotPasswordPage'),
    '/reset-password': () => import('./pages/auth/ResetPasswordPage'),
    '/login': () => import('./pages/auth/LoginPage'),
  }
  const pagePromise = pageLoaders[pathname]
    ? pageLoaders[pathname]()
    : isLibraryPage
      ? import('./pages/LibraryPage')
      : import('./pages/NotFoundPage')

  const [{ createRoot }, pageModule] = await Promise.all([
    import('react-dom/client'),
    pagePromise,
  ])
  const rootElement = document.getElementById('app-root')
  if (!rootElement) throw new Error('Application root element was not found.')

  createRoot(rootElement).render(createElement(
    StrictMode,
    null,
    createElement(RouteReady, null, createElement(pageModule.default)),
  ))
}

void renderRoute()
  .catch((error: unknown) => {
    console.error('Page failed to load.', error)
    document.body.className = 'login-page bg-surface-base text-surface'
    const main = document.createElement('main')
    main.className = 'login-shell'
    const section = document.createElement('section')
    section.className = 'login-content'
    section.innerHTML = '<header class="login-heading"><h1>Page unavailable</h1><p>We couldn’t load this page. Check your connection and try again.</p></header>'
    const reload = document.createElement('button')
    reload.className = 'login-submit'
    reload.type = 'button'
    reload.textContent = 'Reload page'
    reload.addEventListener('click', () => window.location.reload())
    section.append(reload)
    main.append(section)
    document.body.replaceChildren(main)
  })
