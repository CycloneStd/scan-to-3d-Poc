import cycloneWordmark from '../../assets/cyclone-wordmark.png'

type AppHeaderProps = { page: 'library' | 'model' }

const newScanButtonClass = 'library-new-scan mirror-button m-button relative box-border inline-flex items-center justify-center border-2 outline-4 outline-offset-0 outline-transparent whitespace-nowrap no-underline transition-all duration-100 ease-linear focus-visible:focus-ring will-change-contents h-12 gap-1.5 type-component-lg rounded-component-lg border-transparent login-action'

export default function AppHeader({ page }: AppHeaderProps) {
  return (
    <header className="library-header">
      <div className="library-header-inner">
        <a className="library-brand" href="/library" aria-label="Cyclone library">
          <img src={cycloneWordmark} alt="Cyclone" />
        </a>
        <nav className="library-page-nav" aria-label="Main navigation">
          <a className="library-page-nav-link" href="/library" aria-current={page === 'library' ? 'page' : undefined}>Library</a>
        </nav>
        <div className="library-header-actions">
          {page === 'library' ? (
          <a className="library-logout library-filter-pill" href="/login" onClick={(event) => { event.preventDefault(); void authApi.logout().finally(() => window.location.assign('/login')) }}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 4H5v16h5M14 8l4 4-4 4M18 12H9" /></svg>
              Logout
            </a>
          ) : (
            <button
              className={`${newScanButtonClass} results-export`}
              type="button"
              disabled
              title="Model downloads will be available when scan output is connected"
              data-mode="solid"
              data-size="md"
              data-variant="primary"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11m0 0 4-4m-4 4-4-4M5 18v2h14v-2" /></svg>
              Export model
            </button>
          )}
        </div>
      </div>
    </header>
  )
}
import { authApi } from '../../services/auth'

