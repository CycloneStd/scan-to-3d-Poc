import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import cycloneMark from '../assets/cyclone-mark.png'
import arcticIcebergImage from '../assets/arctic-iceberg-scan.webp'
import AppHeader from '../components/library/AppHeader'
import '../styles/library.css'
import '../styles/components/input.css'

const ModelPreview = lazy(() => import('../components/library/ModelPreview'))
const ResultsViewer = lazy(() => import('../components/library/ResultsViewer'))
const libraryFilters = ['All', 'Objects', 'Rooms', 'Buildings', 'Environment'] as const
type LibraryCategory = (typeof libraryFilters)[number]
type ScanStatus = 'Ready' | 'Processing'
type ModelPreviewFormat = 'ply' | 'glb' | 'obj'
type ScanCard = {
  id: number
  modelKey: string
  name: string
  type: 'Object' | 'Room' | 'Building'
  date: string
  status: ScanStatus
  previewUrl?: string
  previewFormat?: ModelPreviewFormat
  source: string
  sourceType: 'photos' | 'video'
  sourceImages?: string[]
  processingTime: string
  quality: 'Fast' | 'Balanced' | 'High detail'
}
const initialScans: ScanCard[] = [
  { id: 1, modelKey: 'mdl-7k4p2q9x', name: 'Arctic Iceberg', type: 'Building', date: 'Today', status: 'Ready', source: '64 photos', sourceType: 'photos', sourceImages: [arcticIcebergImage], processingTime: '4 min 12 s', quality: 'High detail' },
  { id: 2, modelKey: 'mdl-3f8n1v6c', name: 'Sneaker Pair', type: 'Object', date: 'Yesterday', status: 'Processing', source: 'Video, 2:48', sourceType: 'video', processingTime: '2 min 36 s', quality: 'Balanced' },
  { id: 4, modelKey: 'mdl-9d2h5w7k', name: 'Studio Building', type: 'Building', date: 'Nov 6', status: 'Ready', source: '128 photos', sourceType: 'photos', processingTime: '8 min 24 s', quality: 'High detail' },
  { id: 5, modelKey: 'mdl-4q6t8a3m', name: 'Atrium', type: 'Room', date: 'Nov 3', status: 'Ready', source: 'Video, 2:48', sourceType: 'video', processingTime: '5 min 40 s', quality: 'Balanced' },
  { id: 6, modelKey: 'mdl-8c1r5y2p', name: 'Ceramic Vase', type: 'Object', date: 'Oct 29', status: 'Ready', source: '36 photos', sourceType: 'photos', processingTime: '3 min 02 s', quality: 'Fast' },
]

function getScanTimestamp(dateLabel: string) {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  if (dateLabel === 'Today') return today.getTime()
  if (dateLabel === 'Yesterday') return today.getTime() - 24 * 60 * 60 * 1000
  const parsed = new Date(`${dateLabel}, ${today.getFullYear()}`)
  return Number.isNaN(parsed.getTime()) ? 0 : parsed.getTime()
}

function PreviewPlaceholder() {
  return (
    <div className="library-preview-placeholder" aria-hidden="true">
      <img src={cycloneMark} alt="" />
      <span>Preparing preview…</span>
    </div>
  )
}

export default function LibraryPage() {
  const [activeFilter, setActiveFilter] = useState<LibraryCategory>('All')
  const [sortBy, setSortBy] = useState('recent')
  const [searchQuery, setSearchQuery] = useState('')
  const [exportFormat, setExportFormat] = useState<'GLB' | 'OBJ' | 'PLY'>('GLB')
  const [scans, setScans] = useState(initialScans)
  const [sourceImageIndex, setSourceImageIndex] = useState(0)
  const [selectedScan, setSelectedScan] = useState<ScanCard | null>(() => {
    const modelKey = window.location.pathname.split('/').filter(Boolean).at(-1)
    return initialScans.find((scan) => scan.modelKey === modelKey) ?? null
  })
  const closeModalButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!selectedScan) return

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeModalButtonRef.current?.focus()
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeModelWindow()
    }
    const closeOnHistoryBack = () => setSelectedScan(null)
    window.addEventListener('keydown', closeOnEscape)
    window.addEventListener('popstate', closeOnHistoryBack)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
      window.removeEventListener('popstate', closeOnHistoryBack)
    }
  }, [selectedScan])

  useEffect(() => {
    setSourceImageIndex(0)
  }, [selectedScan?.id])

  const visibleScans = scans
    .filter((scan) => activeFilter === 'All' || scan.type === activeFilter.slice(0, -1))
    .filter((scan) => scan.name.toLowerCase().includes(searchQuery.trim().toLowerCase()))
    .sort((a, b) => {
      if (sortBy === 'oldest') return getScanTimestamp(a.date) - getScanTimestamp(b.date)
      if (sortBy === 'name-asc') return a.name.localeCompare(b.name)
      if (sortBy === 'name-desc') return b.name.localeCompare(a.name)
      return getScanTimestamp(b.date) - getScanTimestamp(a.date)
    })

  function renameScan(id: number, name: string) {
    setScans((items) => items.map((scan) => scan.id === id ? { ...scan, name } : scan))
  }

  function openModelWindow(scan: ScanCard) {
    window.history.pushState({ modelKey: scan.modelKey }, '', `/model/${scan.modelKey}`)
    setSelectedScan(scan)
  }

  function closeModelWindow() {
    if (window.location.pathname.startsWith('/model/')) {
      window.history.replaceState(null, '', '/library')
    }
    setSelectedScan(null)
  }

  return (
    <main className="library-shell">
      <AppHeader page="library" />

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
        <div className="library-card-grid">
          {visibleScans.map((scan) => (
            <article className="library-item-card rounded-surface-md bg-surface-low" key={scan.id}>
              <div className="library-card-preview">
                {scan.previewUrl ? (
                  <Suspense fallback={<div className="library-card-media"><PreviewPlaceholder /></div>}>
                    <ModelPreview src={scan.previewUrl} format={scan.previewFormat} name={scan.name} />
                  </Suspense>
                ) : (
                  <div className="library-card-media">
                    <PreviewPlaceholder />
                  </div>
                )}
              </div>
              <div className="library-card-details">
                <div className="library-card-title-row">
                  <input
                    aria-label={`Rename ${scan.name}`}
                    value={scan.name}
                    onChange={(event) => renameScan(scan.id, event.target.value)}
                  />
                  <span className="library-card-date">{scan.date}</span>
                  {scan.status === 'Processing' && (
                    <span className={`library-status library-status-${scan.status.toLowerCase()}`}>
                      {scan.status}
                    </span>
                  )}
                </div>
                <div className="library-card-meta">
                  <span>{scan.type}</span>
                </div>
                <div className="library-pipeline-row">
                  <span className="library-source-detail">
                    <svg viewBox="0 0 20 20" aria-hidden="true">
                      {scan.sourceType === 'video' ? (
                        <path d="M3 5.5h9.5v9H3zM12.5 8l4.5-2v8l-4.5-2" />
                      ) : (
                        <path d="M3.5 5.5h13v10h-13zM6 5.5l1-2h5l1 2M10 8a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5Z" />
                      )}
                    </svg>
                    {scan.source}
                  </span>
                  <span className="library-time-detail">
                    <svg viewBox="0 0 20 20" aria-hidden="true">
                      <circle cx="10" cy="10" r="7" />
                      <path d="M10 6v4l2.5 1.5" />
                    </svg>
                    {scan.processingTime}
                  </span>
                  <span className="library-quality-tag">{scan.quality}</span>
                </div>
              </div>
              <button
                className="library-card-link"
                type="button"
                aria-label={`Open 3D model for ${scan.name}`}
                aria-haspopup="dialog"
                onClick={() => openModelWindow(scan)}
              />
            </article>
          ))}
        </div>
      </section>

      {selectedScan && (
        <div className="model-modal-backdrop" onClick={(event) => event.target === event.currentTarget && closeModelWindow()}>
          <div className="model-modal-frame">
            <section className="model-modal" id="model-preview-dialog" role="dialog" aria-modal="true" aria-label={`${selectedScan.name} model window`}>
              <div className="model-modal-content">
                <div className="model-modal-viewer">
                  <Suspense fallback={<div className="model-modal-loading"><img src={cycloneMark} alt="" /></div>}>
                    <ResultsViewer />
                  </Suspense>
                </div>
                <aside className="model-modal-details-panel" aria-label="Model details">
                  <div className="model-modal-details-scroll">
                  <section className="model-detail-section">
                    <div className="model-detail-heading-row">
                      <h2>{selectedScan.name}</h2>
                      <span className="model-detail-ready">Ready</span>
                    </div>
                    <dl className="model-detail-list">
                      <div><dt>Type</dt><dd>Object</dd></div>
                      <div><dt>Source</dt><dd>64 photos</dd></div>
                      <div><dt>Captured</dt><dd>Today</dd></div>
                      <div><dt>Processing time</dt><dd>4 min 12 s</dd></div>
                    </dl>
                  </section>

                  {selectedScan.sourceType === 'photos' && (
                    <section className="model-detail-section model-original-images">
                      <h2>Resources</h2>
                      {selectedScan.sourceImages?.length ? (
                        <div className="model-original-image-viewer">
                          <img src={selectedScan.sourceImages[sourceImageIndex]} alt={`${selectedScan.name} original capture ${sourceImageIndex + 1}`} />
                          <button type="button" aria-label="Previous original image" disabled={selectedScan.sourceImages.length < 2} onClick={() => setSourceImageIndex((index) => (index - 1 + selectedScan.sourceImages!.length) % selectedScan.sourceImages!.length)}>
                            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m12.5 4.5-5.5 5.5 5.5 5.5" /></svg>
                          </button>
                          <span>{sourceImageIndex + 1} / {selectedScan.sourceImages.length}</span>
                          <button type="button" aria-label="Next original image" disabled={selectedScan.sourceImages.length < 2} onClick={() => setSourceImageIndex((index) => (index + 1) % selectedScan.sourceImages!.length)}>
                            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m7.5 4.5 5.5 5.5-5.5 5.5" /></svg>
                          </button>
                        </div>
                      ) : (
                        <div className="model-original-image-empty">Original images will appear here</div>
                      )}
                    </section>
                  )}

                  <section className="model-detail-section">
                    <h2>Model</h2>
                    <dl className="model-detail-stats">
                      <div><dt>Vertices</dt><dd>7,592</dd></div>
                      <div><dt>Faces</dt><dd>14,400</dd></div>
                      <div><dt>Texture</dt><dd>2048 px</dd></div>
                      <div><dt>File size</dt><dd>6.8 MB</dd></div>
                    </dl>
                  </section>

                  <section className="model-detail-section model-export-section">
                    <h2>Export</h2>
                    <div className="model-export-controls">
                      <div className="model-export-select-wrap">
                        <select aria-label="Export format" value={exportFormat} onChange={(event) => setExportFormat(event.target.value as 'GLB' | 'OBJ' | 'PLY')}>
                          <option value="GLB">GLB</option>
                          <option value="OBJ">OBJ</option>
                          <option value="PLY">PLY</option>
                        </select>
                        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg>
                      </div>
                      <button type="button" className="model-export-button">Export</button>
                    </div>
                  </section>
                  </div>
                </aside>
              </div>
            </section>
            <button ref={closeModalButtonRef} className="model-modal-close" type="button" aria-label="Close model preview" onClick={closeModelWindow}>
              <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 5 10 10M15 5 5 15" /></svg>
            </button>
          </div>
        </div>
      )}
    </main>
  )
}
