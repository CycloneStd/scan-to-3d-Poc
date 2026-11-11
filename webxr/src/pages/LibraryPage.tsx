import { useState } from 'react'
import icebergPreview from '../assets/arctic-iceberg-scan.webp'
import '../styles/library.css'
import '../styles/components/input.css'

const libraryFilters = ['All', 'Objects', 'Rooms', 'Buildings', 'Environment'] as const
type LibraryCategory = (typeof libraryFilters)[number]
const libraryCardImages = [
  icebergPreview,
  ...[19845610, 3778080, 36297579, 29093113, 8516708].map(
    (photoId) => `https://images.pexels.com/photos/${photoId}/pexels-photo-${photoId}.jpeg?auto=compress&cs=tinysrgb&w=720&q=80`,
  ),
]

export default function LibraryPage() {
  const [activeFilter, setActiveFilter] = useState<LibraryCategory>('All')
  const [sortBy, setSortBy] = useState('recent')
  const [searchQuery, setSearchQuery] = useState('')

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
          <div className="library-header-actions">
            <a className="library-logout library-filter-pill" href="/login">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M10 4H5v16h5M14 8l4 4-4 4M18 12H9" />
              </svg>
              Logout
            </a>
          </div>
        </div>
      </header>

      <header className="library-page-heading">
        <div className="library-page-heading-inner">
          <h1>My library</h1>
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
        <div className="library-browse-controls">
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
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                />
              </span>
              <label className="m-input__label" htmlFor="library-search">
                Search your library
              </label>
            </span>
          </div>
          <div className="library-filter-list" role="group" aria-label="Filter library by category">
            {libraryFilters.map((filter) => (
              <button
                key={filter}
                className={`library-filter-pill${activeFilter === filter ? ' is-active' : ''}`}
                type="button"
                aria-pressed={activeFilter === filter}
                onClick={() => setActiveFilter(filter)}
              >
                {filter}
              </button>
            ))}
          </div>
        </div>
        <label className="library-sort-card" htmlFor="library-sort">
          <select
            id="library-sort"
            value={sortBy}
            onChange={(event) => setSortBy(event.target.value)}
          >
            <option value="recent">Most Recent</option>
            <option value="oldest">Oldest</option>
            <option value="name-asc">Name (A–Z)</option>
            <option value="name-desc">Name (Z–A)</option>
            <option value="images-desc">Most Images Used</option>
            <option value="images-asc">Fewest Images Used</option>
          </select>
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path d="m5 7.5 5 5 5-5" />
          </svg>
        </label>
      </section>

      <section className="library-results" aria-label="Library cards">
        <div className="library-card-grid" aria-hidden="true">
          {libraryCardImages.map((image, index) => (
            <article className="library-item-card rounded-surface-md bg-surface-low" key={index}>
              <div className="library-card-media">
                <img src={image} alt="" loading="lazy" />
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  )
}
