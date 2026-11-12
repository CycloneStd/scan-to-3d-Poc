import './styles/components/input.css'
import './styles/login.css'
import { StrictMode, createElement, type ComponentType } from 'react'

type RouteModule = { default: ComponentType }

const authRoutes: Record<string, () => Promise<RouteModule>> = {
  '/signup': () => import('./pages/auth/SignupPage'),
  '/verify-email': () => import('./pages/auth/VerifyEmailPage'),
  '/forgot-password': () => import('./pages/auth/ForgotPasswordPage'),
  '/reset-password': () => import('./pages/auth/ResetPasswordPage'),
  '/login': () => import('./pages/auth/LoginPage'),
}

let appRoot: ReturnType<typeof import('react-dom/client')['createRoot']> | undefined
let activeUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`

function normalizedPath(url: URL) {
  return url.pathname.replace(/\/+$/, '') || '/'
}

async function loadRoute(url: URL): Promise<{ page: RouteModule; protected: boolean; notFound: boolean; destination: URL }> {
  const path = normalizedPath(url)
  const protectedRoute = path === '/library' || path === '/scan' || /^\/model\/[^/]+$/.test(path)

  if (protectedRoute) {
    const { ApiRequestError, authApi } = await import('./services/auth')
    try {
      await authApi.me()
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) {
        const next = `${url.pathname}${url.search}${url.hash}`
        const destination = new URL(`/login?next=${encodeURIComponent(next)}`, window.location.origin)
        return { page: await authRoutes['/login'](), protected: false, notFound: false, destination }
      }
      throw error
    }
  }

  if (authRoutes[path]) return { page: await authRoutes[path](), protected: protectedRoute, notFound: false, destination: url }
  if (protectedRoute) return { page: await import('./pages/LibraryPage'), protected: true, notFound: false, destination: url }
  return { page: await import('./pages/NotFoundPage'), protected: false, notFound: true, destination: url }
}

async function navigate(url: URL, mode: 'push' | 'pop' | 'initial' = 'push') {
  if (normalizedPath(url) === '/' && mode === 'initial') {
    activeUrl = `${url.pathname}${url.search}${url.hash}`
    return
  }
  if (normalizedPath(url) === '/' && mode !== 'initial') {
    window.location.assign(url.href)
    return
  }
  const [loaded, reactDom] = await Promise.all([
    loadRoute(url),
    import('react-dom/client'),
  ])
  const destination = loaded.destination

  if (loaded.page === undefined) throw new Error('The requested page has no route module.')
  if (!appRoot) {
    const root = document.createElement('div')
    root.id = 'app-root'
    document.body.replaceChildren(root)
    appRoot = reactDom.createRoot(root)
  }

  document.body.className = `${loaded.protected || loaded.notFound ? 'library-page' : 'login-page'} bg-surface-base text-surface`
  appRoot.render(createElement(StrictMode, null, createElement(loaded.page.default)))

  if (mode === 'push') window.history.pushState(null, '', destination)
  else if (destination.href !== url.href) window.history.replaceState(null, '', destination)
  activeUrl = `${destination.pathname}${destination.search}${destination.hash}`
}

function showInitialLoadError() {
  document.body.className = 'login-page bg-surface-base text-surface'
  const main = document.createElement('main')
  main.className = 'login-shell'
  const section = document.createElement('section')
  section.className = 'login-content'
  const heading = document.createElement('header')
  heading.className = 'login-heading'
  heading.innerHTML = '<h1>Page unavailable</h1><p>We couldn’t load this page. Check your connection and try again.</p>'
  const reload = document.createElement('button')
  reload.className = 'login-submit'
  reload.type = 'button'
  reload.textContent = 'Reload page'
  reload.addEventListener('click', () => window.location.reload())
  section.append(heading, reload)
  main.append(section)
  document.body.replaceChildren(main)
}

document.addEventListener('click', (event) => {
  if (!(event.target instanceof Element) || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  const anchor = event.target.closest('a[href]')
  if (!(anchor instanceof HTMLAnchorElement) || anchor.target || anchor.hasAttribute('download')) return
  const url = new URL(anchor.href)
  if (url.origin !== window.location.origin || url.pathname === '/') return
  event.preventDefault()
  void navigate(url).catch((error: unknown) => console.error('Navigation failed; keeping the current page.', error))
})

window.addEventListener('popstate', () => {
  void navigate(new URL(window.location.href), 'pop').catch((error: unknown) => {
    console.error('History navigation failed; restoring the current page.', error)
    window.history.replaceState(null, '', activeUrl)
  })
})

void navigate(new URL(window.location.href), 'initial').catch((error: unknown) => {
  console.error('Initial page failed to load.', error)
  showInitialLoadError()
})
