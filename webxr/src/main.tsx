async function renderRoute() {
  const pathname = window.location.pathname.replace(/\/+$/, '') || '/'
  const isModelPage = /^\/model\/[^/]+$/.test(pathname)
  if (pathname !== '/login' && pathname !== '/signup' && pathname !== '/library' && !isModelPage) return

  const isLibraryPage = pathname === '/library' || isModelPage
  document.body.className = `${isLibraryPage ? 'library-page' : 'login-page'} bg-surface-base text-surface`
  document.body.innerHTML = '<div id="app-root"></div>'

  const [{ StrictMode, createElement }, { createRoot }, pageModule] =
    await Promise.all([
      import('react'),
      import('react-dom/client'),
      pathname === '/signup'
        ? import('./pages/auth/SignupPage')
        : isLibraryPage
          ? import('./pages/LibraryPage')
          : import('./pages/auth/LoginPage'),
    ])

  const rootElement = document.getElementById('app-root')
  if (!rootElement) throw new Error('Application root element was not found.')

  createRoot(rootElement).render(
    createElement(StrictMode, null, createElement(pageModule.default)),
  )
}

void renderRoute()
