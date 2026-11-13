import './styles/components/input.css'
import './styles/login.css'
import { StrictMode, createElement, useLayoutEffect, type ComponentType, type ReactNode } from 'react'

type RouteModule = { default: ComponentType }

function RouteCommit({ children, onCommit }: { children: ReactNode; onCommit: () => void }) {
  useLayoutEffect(() => {
    onCommit()
  }, [onCommit])
  return children
}

const authRoutes: Record<string, () => Promise<RouteModule>> = {
  '/signup': () => import('./pages/auth/SignupPage'),
  '/verify-email': () => import('./pages/auth/VerifyEmailPage'),
  '/forgot-password': () => import('./pages/auth/ForgotPasswordPage'),
  '/reset-password': () => import('./pages/auth/ResetPasswordPage'),
  '/login': () => import('./pages/auth/LoginPage'),
}

let appRoot: ReturnType<typeof import('react-dom/client')['createRoot']> | undefined
let appContainer: HTMLDivElement | undefined
let activeUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`
let navigationSequence = 0
let committedNavigationSequence = 0
const landingRoot = document.getElementById('top')
const landingBodyClass = document.body.className
const prefetchedRoutes = new Set<string>()

function normalizedPath(url: URL) {
  return url.pathname.replace(/\/+$/, '') || '/'
}

async function loadAuthRoute(path: string) {
  const [page, imageCards] = await Promise.all([
    authRoutes[path](),
    import('./components/auth/LoginImageCards'),
  ])
  await imageCards.preloadLoginImages()
  return page
}

function prefetchRoute(url: URL) {
  const path = normalizedPath(url)
  if (path === '/' || prefetchedRoutes.has(path)) return
  prefetchedRoutes.add(path)
  const protectedRoute = path === '/library' || path === '/scan' || /^\/model\/[^/]+$/.test(path)
  const load = authRoutes[path]
    ? () => loadAuthRoute(path)
    : protectedRoute
      ? () => import('./pages/LibraryPage')
      : () => import('./pages/NotFoundPage')
  void load().catch(() => prefetchedRoutes.delete(path))
}

async function loadRoute(url: URL, hasFreshAuthentication = false): Promise<{ page: RouteModule; protected: boolean; notFound: boolean; destination: URL }> {
  const path = normalizedPath(url)
  const protectedRoute = path === '/library' || path === '/scan' || /^\/model\/[^/]+$/.test(path)

  if (protectedRoute && !hasFreshAuthentication) {
    const { ApiRequestError, authApi } = await import('./services/auth')
    try {
      await authApi.me()
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) {
        const next = `${url.pathname}${url.search}${url.hash}`
        const destination = new URL(`/login?next=${encodeURIComponent(next)}`, window.location.origin)
        return { page: await loadAuthRoute('/login'), protected: false, notFound: false, destination }
      }
      throw error
    }
  }

  if (authRoutes[path]) return { page: await loadAuthRoute(path), protected: protectedRoute, notFound: false, destination: url }
  if (protectedRoute) return { page: await import('./pages/LibraryPage'), protected: true, notFound: false, destination: url }
  return { page: await import('./pages/NotFoundPage'), protected: false, notFound: true, destination: url }
}

async function navigate(url: URL, mode: 'push' | 'pop' | 'initial' = 'push', hasFreshAuthentication = false) {
  const navigationId = ++navigationSequence
  if (normalizedPath(url) === '/' && mode === 'initial') {
    activeUrl = `${url.pathname}${url.search}${url.hash}`
    return
  }
  if (normalizedPath(url) === '/' && mode !== 'initial') {
    if (navigationId !== navigationSequence) return
    document.documentElement.classList.remove('route-app-initial')
    if (landingRoot) landingRoot.hidden = false
    if (appContainer) appContainer.hidden = true
    document.body.className = landingBodyClass
    if (mode === 'push') window.history.pushState(null, '', url)
    else if (url.href !== window.location.href) window.history.replaceState(null, '', url)
    activeUrl = `${url.pathname}${url.search}${url.hash}`
    return
  }
  const [loaded, reactDom] = await Promise.all([
    loadRoute(url, hasFreshAuthentication),
    import('react-dom/client'),
  ])
  if (navigationId !== navigationSequence) return
  const destination = loaded.destination

  if (loaded.page === undefined) throw new Error('The requested page has no route module.')
  if (!appRoot) {
    const root = document.createElement('div')
    root.id = 'app-root'
    root.hidden = true
    document.body.append(root)
    appContainer = root
    appRoot = reactDom.createRoot(root)
  }

  const commit = () => {
    if (navigationId !== navigationSequence || committedNavigationSequence === navigationId) return
    committedNavigationSequence = navigationId
    if (landingRoot) landingRoot.hidden = true
    document.documentElement.classList.remove('route-app-initial')
    if (appContainer) appContainer.hidden = false
    document.body.className = `${loaded.protected || loaded.notFound ? 'library-page' : 'login-page'} bg-surface-base text-surface`
    if (mode === 'push') window.history.pushState(null, '', destination)
    else if (destination.href !== url.href) window.history.replaceState(null, '', destination)
    activeUrl = `${destination.pathname}${destination.search}${destination.hash}`
  }
  appRoot.render(createElement(StrictMode, null, createElement(RouteCommit, { onCommit: commit }, createElement(loaded.page.default))))
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
  if (url.origin !== window.location.origin) return
  if (url.pathname === window.location.pathname && url.search === window.location.search) return
  event.preventDefault()
  void navigate(url).catch((error: unknown) => console.error('Navigation failed; keeping the current page.', error))
})

function prefetchLink(event: Event) {
  if (!(event.target instanceof Element)) return
  const anchor = event.target.closest('a[href]')
  if (!(anchor instanceof HTMLAnchorElement) || anchor.target || anchor.hasAttribute('download')) return
  const url = new URL(anchor.href)
  if (url.origin === window.location.origin) prefetchRoute(url)
}

document.addEventListener('pointerover', prefetchLink, { passive: true })
document.addEventListener('focusin', prefetchLink)

window.addEventListener('popstate', () => {
  void navigate(new URL(window.location.href), 'pop').catch((error: unknown) => {
    console.error('History navigation failed; restoring the current page.', error)
    window.history.replaceState(null, '', activeUrl)
  })
})

window.addEventListener('cyclone:navigate', (event) => {
  const detail = (event as CustomEvent<string | { destination: string; authenticated?: boolean; onError?: () => void }>).detail
  const destination = typeof detail === 'string' ? detail : detail?.destination
  if (typeof destination !== 'string') return
  const url = new URL(destination, window.location.origin)
  if (url.origin !== window.location.origin) return
  void navigate(url, 'push', typeof detail !== 'string' && detail.authenticated === true).catch((error: unknown) => {
    if (typeof detail !== 'string') detail?.onError?.()
    console.error('Navigation failed; keeping the current page.', error)
  })
})

void navigate(new URL(window.location.href), 'initial').catch((error: unknown) => {
  console.error('Initial page failed to load.', error)
  showInitialLoadError()
})
