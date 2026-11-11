import { useState } from 'react'
import icebergPreview from '../assets/arctic-iceberg-scan.webp'
import '../styles/library.css'
import '../styles/components/input.css'

const libraryFilters = ['All', 'Objects', 'Rooms', 'Buildings', 'Environment'] as const
type LibraryCategory = (typeof libraryFilters)[number]
type LibraryItem = {
  id: string
  name: string
  category: Exclude<LibraryCategory, 'All'>
  images: number
  createdAt: string
  cover: 'object' | 'room' | 'building' | 'environment'
  image?: string
}

const previewItems: LibraryItem[] = [
  { id: 'vase', name: 'Stoneware Vase', category: 'Objects', images: 48, createdAt: '2026-11-11', cover: 'object' },
  { id: 'lamp', name: 'Studio Lamp', category: 'Objects', images: 36, createdAt: '2026-11-10', cover: 'object' },
  { id: 'reading-room', name: 'Reading Room', category: 'Rooms', images: 112, createdAt: '2026-11-08', cover: 'room' },
  { id: 'living-space', name: 'Living Space', category: 'Rooms', images: 84, createdAt: '2026-11-06', cover: 'room' },
  { id: 'workshop', name: 'Workshop Building', category: 'Buildings', images: 176, createdAt: '2026-11-03', cover: 'building' },
  { id: 'iceberg', name: 'Arctic Iceberg', category: 'Environment', images: 94, createdAt: '2026-10-29', cover: 'environment', image: icebergPreview },
]

export default function LibraryPage() {
  const [activeFilter, setActiveFilter] = useState<LibraryCategory>('All')
  const [sortBy, setSortBy] = useState('recent')
  const [searchQuery, setSearchQuery] = useState('')

  const visibleItems = previewItems
    .filter((item) => activeFilter === 'All' || item.category === activeFilter)
    .filter((item) => item.name.toLowerCase().includes(searchQuery.trim().toLowerCase()))
    .sort((a, b) => {
      if (sortBy === 'oldest') return a.createdAt.localeCompare(b.createdAt)
      if (sortBy === 'name-asc') return a.name.localeCompare(b.name)
      if (sortBy === 'name-desc') return b.name.localeCompare(a.name)
      if (sortBy === 'images-desc') return b.images - a.images
      if (sortBy === 'images-asc') return a.images - b.images
      return b.createdAt.localeCompare(a.createdAt)
    })

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

      <section className="library-results" aria-labelledby="library-results-title">
        <header className="library-results-header">
          <div>
            <h1 id="library-results-title">Your library</h1>
            <p>Sample scans to preview your library layout</p>
          </div>
          <span className="library-result-count">{visibleItems.length} items</span>
        </header>
        {visibleItems.length > 0 ? (
          <div className="library-card-grid">
            {visibleItems.map((item) => (
              <article className="library-item-card rounded-surface-md bg-surface-low" key={item.id}>
                <div className={`library-card-cover library-card-cover--${item.cover}`}>
                  {item.image ? (
                    <img src={item.image} alt="" />
                  ) : (
                    <svg className="library-card-artwork" viewBox="0 0 120 120" aria-hidden="true">
                      <path d="m60 15 39 22v46l-39 22-39-22V37z" />
                      <path d="m21 37 39 23 39-23M60 60v45M41 26l39 22v24L41 50z" />
                    </svg>
                  )}
                  <span className="library-preview-badge">Preview</span>
                  <span className="library-card-category">{item.category}</span>
                </div>
                <div className="library-card-details">
                  <h2>{item.name}</h2>
                  <div className="library-card-meta">
                    <span>{item.images} images</span>
                    <span>{new Date(`${item.createdAt}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="library-empty-state">No scans match this search and category.</p>
        )}
      </section>
    </main>
  )
}
