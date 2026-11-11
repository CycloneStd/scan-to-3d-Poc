import '../styles/library.css'
import '../styles/components/input.css'

export default function LibraryPage() {
  return (
    <main className="library-shell">
      <header className="library-header">
        <div className="library-header-inner">
          <div aria-hidden="true" />
          <div className="ui-header-nav border-surface backdrop-blur-surface relative flex h-17 items-center gap-1 overflow-hidden rounded-3xl border-2 p-1 lg:h-15 lg:rounded-[1.375rem] pointer-events-auto">
            <div className="translucent-glass" />
            <a
              href="/library"
              aria-current="page"
              className="m-button relative box-border inline-flex items-center justify-center border-2 outline-4 outline-offset-0 outline-transparent whitespace-nowrap no-underline transition-all duration-100 ease-linear focus-visible:focus-ring will-change-contents h-12 gap-1.5 type-component-lg rounded-component-lg border-transparent bg-primary-subtle text-primary-on-subtle hover:bg-primary-subtle data-[pressed=true]:bg-primary-subtle-hover mirror-button pointer-events-auto min-w-24"
              data-blur="true"
              data-icon="true"
              data-mode="subtle"
              data-size="md"
              data-variant="primary"
            >
              <span className="home-label">Library</span>
            </a>
          </div>
          <a
            className="library-new-scan mirror-button m-button relative box-border inline-flex items-center justify-center border-2 outline-4 outline-offset-0 outline-transparent whitespace-nowrap no-underline transition-all duration-100 ease-linear focus-visible:focus-ring will-change-contents h-12 gap-1.5 type-component-lg rounded-component-lg border-transparent login-action"
            href="/scan"
            data-mode="solid"
            data-size="md"
            data-variant="primary"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New Scan
          </a>
        </div>
      </header>

      <section className="library-toolbar" aria-label="Search your library">
        <div className="library-search-field m-input relative box-border flex w-full cursor-text flex-row items-center justify-between select-none transition-all duration-100 ease-linear will-change-contents h-14 gap-1.5 rounded-component-xl" data-size="lg">
          <span
            className="m-input__target"
            aria-hidden="true"
            onClick={() => document.getElementById('library-search')?.focus()}
          />
          <span className="m-input__field">
            <span className="m-input__control">
              <input
                id="library-search"
                name="search"
                className="mirror-input"
                type="search"
                placeholder="Search your library"
                autoComplete="off"
              />
            </span>
            <label className="m-input__label" htmlFor="library-search">
              Search your library
            </label>
          </span>
        </div>
      </section>
    </main>
  )
}
