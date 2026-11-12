import { lazy, Suspense, useEffect, useRef, useState, type MouseEvent } from 'react'
import cycloneMark from '../assets/cyclone-mark.webp'
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
  const [scanFiles, setScanFiles] = useState<File[]>([])
  const [uploadError, setUploadError] = useState('')
  const [scanProgress, setScanProgress] = useState<number | null>(null)
  const [pendingScanDetails, setPendingScanDetails] = useState<{ name: string; type: ScanCard['type'] } | null>(null)
  const [scanType, setScanType] = useState('')
  const [isScanDrawerOpen, setIsScanDrawerOpen] = useState(() => window.location.pathname === '/scan')
  const [sourceImageIndex, setSourceImageIndex] = useState(0)
  const [selectedScan, setSelectedScan] = useState<ScanCard | null>(() => {
    const modelKey = window.location.pathname.split('/').filter(Boolean).at(-1)
    return initialScans.find((scan) => scan.modelKey === modelKey) ?? null
  })
  const closeModalButtonRef = useRef<HTMLButtonElement>(null)
  const closeScanDrawerButtonRef = useRef<HTMLButtonElement>(null)
  const scanFileInputRef = useRef<HTMLInputElement>(null)
  const uploadKind = scanFiles[0]?.type.startsWith('video/') ? 'video' : scanFiles.length ? 'photos' : null
  useEffect(() => {
    if (window.location.pathname === '/scan') window.history.replaceState(null, '', '/library')
  }, [])

  useEffect(() => {
    if (scanProgress === null || scanProgress >= 100) return
    const timer = window.setInterval(() => setScanProgress((progress) => progress === null ? null : Math.min(100, progress + 1)), 300)
    return () => window.clearInterval(timer)
  }, [scanProgress === null || scanProgress >= 100])

  useEffect(() => {
    if (scanProgress !== 100) return
    const modelKey = `mdl-${Date.now().toString(36)}`
    const uploadedVideo = scanFiles.find((file) => file.type.startsWith('video/'))
    const result: ScanCard = {
      id: Date.now(),
      modelKey,
      name: pendingScanDetails?.name || 'New scan',
      type: pendingScanDetails?.type || 'Object',
      date: 'Today',
      status: 'Ready',
      source: uploadedVideo ? `Video · ${uploadedVideo.name}` : `${scanFiles.length} photos`,
      sourceType: uploadedVideo ? 'video' : 'photos',
      processingTime: 'Just now',
      quality: 'Balanced',
    }
    setScans((items) => [result, ...items])
    setIsScanDrawerOpen(false)
    window.history.replaceState({ modelKey }, '', `/model/${modelKey}`)
    setSelectedScan(result)
    setScanProgress(null)
  }, [scanProgress])

  useEffect(() => {
    if (!selectedScan && !isScanDrawerOpen) return

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    if (selectedScan) closeModalButtonRef.current?.focus()
    if (isScanDrawerOpen) closeScanDrawerButtonRef.current?.focus()
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (isScanDrawerOpen) closeScanDrawer()
        else closeModelWindow()
      }
    }
    const closeOnHistoryBack = () => {
      setSelectedScan(null)
      setIsScanDrawerOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    window.addEventListener('popstate', closeOnHistoryBack)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
      window.removeEventListener('popstate', closeOnHistoryBack)
    }
  }, [selectedScan, isScanDrawerOpen])

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

  function closeScanDrawer() {
    if (window.location.pathname === '/scan') {
      window.history.replaceState(null, '', '/library')
    }
    setIsScanDrawerOpen(false)
  }

  function openScanDrawer(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault()
    if (window.location.pathname !== '/library') window.history.replaceState(null, '', '/library')
    setIsScanDrawerOpen(true)
  }

  function addScanFiles(files: File[]) {
    const kind = files[0]?.type.startsWith('video/') ? 'video' : 'photos'
    const validFiles = files.filter((file) => kind === 'video' ? file.type.startsWith('video/') : ['image/jpeg', 'image/png'].includes(file.type))
    if (validFiles.length !== files.length) {
      setUploadError('Use JPEG or PNG photos, or choose a video. Other image formats are not supported by the pipeline.')
      return
    }
    if (scanFiles.length && uploadKind !== kind) {
      setUploadError('Photos and video must be uploaded in separate scans. Remove the current files to switch input type.')
      return
    }
    if (kind === 'video' && (scanFiles.length || validFiles.length > 1)) {
      setUploadError('Choose one video per scan. Remove the current files before choosing another video.')
      return
    }
    setUploadError('')
    setScanFiles((current) => [...current, ...validFiles])
  }

  return (
    <main className="library-shell">
      <AppHeader page="library" />

      <header className="library-page-heading">
        <div className="library-page-heading-inner">
          <h1>My library</h1>
          <a
            className="library-new-scan mirror-button m-button relative box-border inline-flex items-center justify-center border-2 outline-4 outline-offset-0 outline-transparent whitespace-nowrap no-underline transition-all duration-100 ease-linear focus-visible:focus-ring will-change-contents h-12 gap-1.5 type-component-lg rounded-component-lg border-transparent login-action"
            href="/library"
            onClick={openScanDrawer}
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
                      <div><dt>Type</dt><dd>{selectedScan.type}</dd></div>
                      <div><dt>Source</dt><dd>{selectedScan.source}</dd></div>
                      <div><dt>Captured</dt><dd>{selectedScan.date}</dd></div>
                      <div><dt>Processing time</dt><dd>{selectedScan.processingTime}</dd></div>
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

      {isScanDrawerOpen && (
        <div className="scan-drawer-backdrop" onClick={(event) => event.target === event.currentTarget && closeScanDrawer()}>
          <aside className="scan-drawer" role="dialog" aria-modal="true" aria-labelledby="scan-drawer-title">
            <div className="scan-drawer-glass" aria-hidden="true" />
            <div className="scan-drawer-content">
              <button ref={closeScanDrawerButtonRef} className="scan-drawer-close" type="button" aria-label="Close new scan panel" onClick={closeScanDrawer}>
                <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 5 10 10M15 5 5 15" /></svg>
              </button>
              <div className="scan-drawer-header">
                <h2 id="scan-drawer-title">New Scan</h2>
              </div>
              <form className="scan-drawer-form" aria-busy={scanProgress !== null} onSubmit={(event) => { event.preventDefault(); const formData = new FormData(event.currentTarget); setPendingScanDetails({ name: String(formData.get('name') || 'New scan'), type: String(formData.get('type') || 'Object') as ScanCard['type'] }); setScanProgress(0) }}>
                <fieldset className="scan-drawer-fields" disabled={scanProgress !== null}>
                <section className="scan-drawer-section">
                  <h3>Images</h3>
                  <button className="scan-upload-target" type="button" onClick={() => scanFileInputRef.current?.click()}>
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v5h14v-5" /></svg>
                    <strong>{uploadKind === 'video' ? 'Video selected' : uploadKind === 'photos' ? 'Add photos' : 'Add photos or video'}</strong>
                    <span>{uploadKind === 'video' ? 'Remove it to switch input type' : 'JPEG or PNG photos, or one video'}</span>
                  </button>
                  <input
                    ref={scanFileInputRef}
                    className="scan-upload-input"
                    type="file"
                    accept={uploadKind === 'video' ? 'video/*' : uploadKind === 'photos' ? 'image/jpeg,image/png' : 'image/jpeg,image/png,video/*'}
                    multiple={uploadKind !== 'video'}
                    onChange={(event) => { addScanFiles(Array.from(event.target.files ?? [])); event.currentTarget.value = '' }}
                  />
                  {uploadError && <p className="scan-upload-error" role="alert">{uploadError}</p>}
                  {scanFiles.length > 0 && (
                    <div className="scan-upload-count" aria-live="polite">
                      {scanFiles.length} {uploadKind === 'video' ? (scanFiles.length === 1 ? 'video selected' : 'videos selected') : (scanFiles.length === 1 ? 'photo selected' : 'photos selected')}
                    </div>
                  )}
                </section>

                <section className="scan-drawer-section">
                  <h3>Scan details</h3>
                  <div className="scan-login-input m-input relative box-border flex w-full cursor-text flex-row items-center justify-between select-none transition-all duration-100 ease-linear will-change-contents h-14 gap-1.5 rounded-component-xl" data-size="lg">
                    <span className="m-input__target" aria-hidden="true" onClick={() => document.getElementById('scan-name')?.focus()} />
                    <span className="m-input__field"><span className="m-input__control"><input className="mirror-input" id="scan-name" name="name" placeholder="Scan name" required /></span><label className="m-input__label" htmlFor="scan-name">Scan name</label></span>
                  </div>
                  <div className={`scan-login-input scan-type-input m-input relative box-border flex w-full cursor-text flex-row items-center justify-between select-none transition-all duration-100 ease-linear will-change-contents h-14 gap-1.5 rounded-component-xl${scanType ? ' has-value' : ''}`} data-size="lg" data-simple="true">
                    <span className="m-input__target" aria-hidden="true" onClick={() => document.getElementById('scan-type')?.focus()} />
                    <span className="m-input__field"><span className="m-input__control"><select className="scan-drawer-select" id="scan-type" name="type" value={scanType} onChange={(event) => setScanType(event.target.value)} aria-label="Type"><option value="" disabled>Type</option><option>Object</option><option>Room</option><option>Building</option></select></span></span>
                    <svg className="scan-type-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m5.5 7.5 4.5 4.5 4.5-4.5" /></svg>
                  </div>
                  <div className="scan-login-input m-input relative box-border flex w-full cursor-text flex-row items-center justify-between select-none transition-all duration-100 ease-linear will-change-contents h-14 gap-1.5 rounded-component-xl" data-size="lg">
                    <span className="m-input__target" aria-hidden="true" onClick={() => document.getElementById('scan-object')?.focus()} />
                    <span className="m-input__field"><span className="m-input__control"><input className="mirror-input" id="scan-object" name="object" placeholder="What are you scanning?" /></span><label className="m-input__label" htmlFor="scan-object">What are you scanning?</label></span>
                  </div>
                  <div className="scan-description-shell m-input relative box-border w-full rounded-component-xl" data-size="lg">
                    <textarea className="scan-description-input" id="scan-description" name="description" placeholder=" " aria-label="Description" rows={3} />
                    <label className="scan-description-label" htmlFor="scan-description">Description</label>
                  </div>
                </section>
                <button className="scan-drawer-submit" type="submit">Start Scan</button>
                </fieldset>
              </form>
            </div>
          </aside>
          {scanProgress !== null && scanProgress < 100 && (
            <div className="scan-progress-zone" role="status" aria-live="polite">
              <div className="scan-progress">
                <div className="scan-progress-label"><strong>{scanProgress}%</strong></div>
                <div className="scan-progress-track" role="progressbar" aria-label="Scan progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={scanProgress}><span style={{ width: `${scanProgress}%` }} /></div>
              </div>
            </div>
          )}
        </div>
      )}
    </main>
  )
}
