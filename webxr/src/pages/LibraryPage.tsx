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

      <section className="library-toolbar" aria-label="Search and filter your library">
        <label className="library-search-field m-input relative box-border flex w-full flex-row items-center justify-between rounded-component-xl transition-all duration-100 ease-linear h-14 gap-1.5" data-size="lg" data-simple="true">
          <span className="library-search-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <circle cx="10.8" cy="10.8" r="6.8" />
              <path d="m16 16 5 5" />
            </svg>
          </span>
          <span className="m-input__field">
            <span className="m-input__control">
              <input id="library-search" className="mirror-input" type="search" placeholder=" " />
            </span>
            <span className="m-input__label">Search your library</span>
          </span>
        </label>
        <div className="library-filters">
          <label className="library-filter-control">
            <span className="library-filter-label">Type</span>
            <select aria-label="Filter by type" defaultValue="all">
              <option value="all">All items</option>
              <option value="scans">Scans</option>
              <option value="models">3D models</option>
            </select>
          </label>
          <label className="library-filter-control">
            <span className="library-filter-label">Sort</span>
            <select aria-label="Sort library items" defaultValue="newest">
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="name">Name</option>
            </select>
          </label>
        </div>
      </section>
    </main>
  )
}
