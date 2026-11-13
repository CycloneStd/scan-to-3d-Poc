import { lazy, Suspense, useCallback, useEffect, useRef, useState, type FormEvent, type MouseEvent } from 'react'
import cycloneMark from '../assets/cyclone-mark.webp'
import rocketIcon from '../assets/rocket-lucide.svg'
import AppHeader from '../components/library/AppHeader'
import { scansApi, type ScanArtifact, type ScanAsset, type ScanJob, type ScanRecord } from '../services/scans'
import '../styles/library.css'
import '../styles/components/input.css'

const ResultsViewer = lazy(() => import('../components/library/ResultsViewer'))
const libraryFilters = ['All', 'Objects', 'Rooms', 'Buildings', 'Environment'] as const
type LibraryCategory = (typeof libraryFilters)[number]
type ScanCard = ScanRecord & { type: string; date: string; source: string; sourceType: 'photos' | 'video'; processingTime: string; quality: string }

function toScanCard(scan: ScanRecord): ScanCard {
  const images = scan.assets.filter((asset) => asset.status === 'uploaded' && asset.content_type.startsWith('image/'))
  const video = scan.assets.find((asset) => asset.status === 'uploaded' && asset.content_type.startsWith('video/'))
  const latestJob = scan.jobs[0]
  const seconds = latestJob?.started_at && latestJob.finished_at
    ? Math.max(0, Math.floor((Date.parse(latestJob.finished_at) - Date.parse(latestJob.started_at)) / 1000))
    : null
  return {
    ...scan,
    type: scan.subject_type,
    date: new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(new Date(scan.created_at)),
    source: video ? `Video · ${video.filename}` : `${images.length} ${images.length === 1 ? 'photo' : 'photos'}`,
    sourceType: video ? 'video' : 'photos',
    processingTime: seconds === null ? '—' : `${Math.floor(seconds / 60)} min ${String(seconds % 60).padStart(2, '0')} s`,
    quality: '—',
  }
}

function formatMetric(metrics: Record<string, unknown> | undefined, names: string[]) {
  if (!metrics) return '—'
  const wanted = new Set(names.map((name) => name.toLowerCase()))
  const visit = (value: unknown): string | undefined => {
    if (!value || typeof value !== 'object') return undefined
    for (const [key, item] of Object.entries(value)) {
      if (wanted.has(key.toLowerCase()) && (typeof item === 'number' || typeof item === 'string')) {
        return Number.isFinite(Number(item)) ? Number(item).toLocaleString() : String(item)
      }
    }
    for (const item of Object.values(value)) {
      const found = visit(item)
      if (found) return found
    }
    return undefined
  }
  return visit(metrics) ?? '—'
}

function formatBytes(bytes: number | undefined) {
  if (!bytes || bytes < 0) return '—'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function fileExtension(filename: string) {
  return filename.split('.').pop()?.toLowerCase() ?? ''
}

function resultArtifact(scan: ScanRecord): ScanArtifact | null {
  const artifacts = scan.artifacts.filter((artifact) => ['glb', 'gltf', 'obj', 'ply', 'spz'].includes(fileExtension(artifact.filename)))
  const priority = ['glb', 'obj', 'ply', 'spz', 'gltf']
  return artifacts.sort((a, b) => priority.indexOf(fileExtension(a.filename)) - priority.indexOf(fileExtension(b.filename)))[0] ?? null
}

function fileKind(file: File): 'photos' | 'video' | null {
  const extension = file.name.split('.').pop()?.toLowerCase()
  const imageExtensions = ['jpg', 'jpeg', 'png']
  const videoExtensions = ['mp4', 'mov', 'm4v', 'avi', 'mkv', 'webm']
  if (imageExtensions.includes(extension ?? '') && (!file.type || file.type === 'image/jpeg' || file.type === 'image/png')) return 'photos'
  if (videoExtensions.includes(extension ?? '') && (!file.type || file.type.startsWith('video/'))) return 'video'
  return null
}

function formatStatus(status: string) {
  return status.charAt(0).toUpperCase() + status.slice(1)
}

const sourceImageBlobs = new Map<string, Promise<Blob>>()

function getSourceImageBlob(assetId: string) {
  const cached = sourceImageBlobs.get(assetId)
  if (cached) {
    sourceImageBlobs.delete(assetId)
    sourceImageBlobs.set(assetId, cached)
    return cached
  }
  const request = scansApi.sourceAsset(assetId)
  sourceImageBlobs.set(assetId, request)
  while (sourceImageBlobs.size > 3) sourceImageBlobs.delete(sourceImageBlobs.keys().next().value!)
  void request.catch(() => {
    if (sourceImageBlobs.get(assetId) === request) sourceImageBlobs.delete(assetId)
  })
  return request
}

async function preloadSourceImage(assetId: string) {
  const blob = await getSourceImageBlob(assetId)
  const url = URL.createObjectURL(blob)
  const image = new Image()
  try {
    if (typeof image.decode === 'function') {
      image.src = url
      await image.decode()
    } else {
      await new Promise<void>((resolve, reject) => {
        image.onload = () => resolve()
        image.onerror = () => reject(new Error('The original image could not be decoded.'))
        image.src = url
      })
    }
  } finally {
    URL.revokeObjectURL(url)
  }
}

function PreviewPlaceholder() {
  return (
    <div className="library-preview-placeholder" aria-hidden="true">
      <img src={cycloneMark} alt="" />
      <span>Preparing preview…</span>
    </div>
  )
}

function SourceAssetImage({ asset, name, index }: { asset: ScanAsset; name: string; index: number }) {
  const [src, setSrc] = useState<string>()
  const [loaded, setLoaded] = useState(false)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let active = true
    let objectUrl: string | undefined
    setSrc(undefined)
    setLoaded(false)
    setFailed(false)
    void getSourceImageBlob(asset.id).then((blob) => {
      objectUrl = URL.createObjectURL(blob)
      if (active) setSrc(objectUrl)
      else URL.revokeObjectURL(objectUrl)
    }).catch((error: unknown) => {
      if (active) setFailed(true)
      console.error('Source image could not be loaded.', error)
    })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [asset.id])
  return (
    <div className={`model-original-image-frame${loaded ? ' is-loaded' : ''}`} aria-busy={!loaded && !failed}>
      {!loaded && (
        <div className="model-original-image-loading" role={failed ? 'status' : undefined}>
          <img src={cycloneMark} alt="" />
          {failed && <span>Image could not be loaded</span>}
        </div>
      )}
      {src && <img src={src} alt={`${name} original capture ${index + 1}`} onLoad={() => setLoaded(true)} onError={() => setFailed(true)} />}
    </div>
  )
}

export default function LibraryPage() {
  const [activeFilter, setActiveFilter] = useState<LibraryCategory>('All')
  const [sortBy, setSortBy] = useState('recent')
  const [searchQuery, setSearchQuery] = useState('')
  const [exportFormat, setExportFormat] = useState<'GLB' | 'OBJ' | 'PLY'>('GLB')
  const [scans, setScans] = useState<ScanCard[]>([])
  const [hasLoadedScans, setHasLoadedScans] = useState(false)
  const [scanFiles, setScanFiles] = useState<File[]>([])
  const [uploadError, setUploadError] = useState('')
  const [scanProgress, setScanProgress] = useState<number | null>(null)
  const [scanType, setScanType] = useState('')
  const [isScanDrawerOpen, setIsScanDrawerOpen] = useState(() => window.location.pathname === '/scan')
  const [sourceImageIndex, setSourceImageIndex] = useState(0)
  const [sourceImageNavigating, setSourceImageNavigating] = useState(false)
  const [selectedScan, setSelectedScan] = useState<ScanCard | null>(null)
  const [scanActionError, setScanActionError] = useState('')
  const [retryingScanId, setRetryingScanId] = useState<string | null>(null)
  const [deletingScanId, setDeletingScanId] = useState<string | null>(null)
  const closeModalButtonRef = useRef<HTMLButtonElement>(null)
  const closeScanDrawerButtonRef = useRef<HTMLButtonElement>(null)
  const scanFileInputRef = useRef<HTMLInputElement>(null)
  const uploadKind = scanFiles.length ? fileKind(scanFiles[0]) : null
  const refreshScans = useCallback(async () => {
    const records = (await scansApi.list()).map(toScanCard)
    setScans(records)
    setHasLoadedScans(true)
    setSelectedScan((current) => current ? records.find((scan) => scan.id === current.id) ?? current : current)
    return records
  }, [])

  useEffect(() => {
    void refreshScans().catch((error: unknown) => console.error('The scan library could not be loaded.', error))
  }, [refreshScans])

  const hasActiveScans = scans.some((scan) => scan.status === 'queued' || scan.status === 'processing')
  useEffect(() => {
    if (!hasActiveScans) return
    const timer = window.setInterval(() => { void refreshScans().catch((error: unknown) => console.error('Scan statuses could not be refreshed.', error)) }, 5000)
    return () => window.clearInterval(timer)
  }, [hasActiveScans, refreshScans])

  useEffect(() => {
    if (!window.location.pathname.startsWith('/model/')) return
    const scanId = window.location.pathname.split('/').filter(Boolean).at(-1)
    const scan = scans.find((item) => item.id === scanId)
    if (scan) setSelectedScan(scan)
  }, [scans])

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

  useEffect(() => setSourceImageIndex(0), [selectedScan?.id])

  const visibleScans = scans
    .filter((scan) => activeFilter === 'All' || scan.type === ({ Objects: 'Object', Rooms: 'Room', Buildings: 'Building', Environment: 'Environment' } as const)[activeFilter])
    .filter((scan) => scan.name.toLowerCase().includes(searchQuery.trim().toLowerCase()))
    .sort((a, b) => {
      if (sortBy === 'oldest') return Date.parse(a.created_at) - Date.parse(b.created_at)
      if (sortBy === 'name-asc') return a.name.localeCompare(b.name)
      if (sortBy === 'name-desc') return b.name.localeCompare(a.name)
      if (sortBy === 'images-desc') return b.assets.filter((asset) => asset.content_type.startsWith('image/')).length - a.assets.filter((asset) => asset.content_type.startsWith('image/')).length
      if (sortBy === 'images-asc') return a.assets.filter((asset) => asset.content_type.startsWith('image/')).length - b.assets.filter((asset) => asset.content_type.startsWith('image/')).length
      return Date.parse(b.created_at) - Date.parse(a.created_at)
    })

  const selectedJob: ScanJob | undefined = selectedScan?.jobs[0]
  const selectedArtifact = selectedScan ? resultArtifact(selectedScan) : null
  const selectedImages = selectedScan?.assets.filter((asset) => asset.status === 'uploaded' && asset.content_type.startsWith('image/')) ?? []
  const selectedImageIds = selectedImages.map((asset) => asset.id).join(',')
  const selectedExports = selectedScan?.artifacts.filter((artifact) => ['glb', 'obj', 'ply'].includes(fileExtension(artifact.filename))) ?? []
  const selectedExport = selectedExports.find((artifact) => fileExtension(artifact.filename).toUpperCase() === exportFormat)

  useEffect(() => {
    if (selectedImages.length < 2) return
    const adjacent = [
      selectedImages[(sourceImageIndex + 1) % selectedImages.length],
      selectedImages[(sourceImageIndex - 1 + selectedImages.length) % selectedImages.length],
    ]
    adjacent.forEach((asset) => { void getSourceImageBlob(asset.id).catch(() => undefined) })
  }, [selectedScan?.id, selectedImageIds, sourceImageIndex])

  useEffect(() => {
    const preferred = selectedExports.find((artifact) => fileExtension(artifact.filename).toUpperCase() === exportFormat)
    if (!preferred && selectedExports[0]) setExportFormat(fileExtension(selectedExports[0].filename).toUpperCase() as 'GLB' | 'OBJ' | 'PLY')
  }, [selectedScan?.id, selectedExports.map((artifact) => artifact.id).join(',')])

  function renameScan(id: string, name: string) {
    setScans((items) => items.map((scan) => scan.id === id ? { ...scan, name } : scan))
  }

  async function saveScanName(scan: ScanCard) {
    const name = scan.name.trim()
    if (!name || scan.status === 'queued' || scan.status === 'processing') return
    try {
      await scansApi.update(scan.id, { name, subject_type: scan.subject_type, subject: scan.subject, description: scan.description })
      await refreshScans()
    } catch (error) {
      console.error('The scan name could not be saved.', error)
      await refreshScans().catch(() => undefined)
    }
  }

  function openModelWindow(scan: ScanCard) {
    setScanActionError('')
    window.history.pushState({ scanId: scan.id }, '', `/model/${scan.id}`)
    setSelectedScan(scan)
  }

  async function changeSourceImage(direction: -1 | 1) {
    if (sourceImageNavigating || selectedImages.length < 2) return
    const nextIndex = (sourceImageIndex + direction + selectedImages.length) % selectedImages.length
    setSourceImageNavigating(true)
    try {
      await preloadSourceImage(selectedImages[nextIndex].id)
      setSourceImageIndex(nextIndex)
    } catch (error) {
      console.error('The next original image could not be prepared.', error)
      setScanActionError('That original image could not be loaded. Try again.')
    } finally {
      setSourceImageNavigating(false)
    }
  }

  async function retryScan(scanId: string) {
    setScanActionError('')
    setRetryingScanId(scanId)
    try {
      await scansApi.start(scanId)
      await refreshScans()
    } catch (error) {
      setScanActionError(error instanceof Error ? error.message : 'The scan could not be retried.')
    } finally {
      setRetryingScanId(null)
    }
  }

  async function deleteScan(scan: ScanCard) {
    const active = scan.status === 'queued' || scan.status === 'processing'
    const message = active
      ? `Delete “${scan.name}” and stop its queued or running scan? This cannot be undone.`
      : `Delete “${scan.name}” and its uploaded files? This cannot be undone.`
    if (!window.confirm(message)) return
    setScanActionError('')
    setDeletingScanId(scan.id)
    try {
      await scansApi.remove(scan.id)
      setScans((items) => items.filter((item) => item.id !== scan.id))
      closeModelWindow()
    } catch (error) {
      setScanActionError(error instanceof Error ? error.message : 'The scan could not be deleted.')
    } finally {
      setDeletingScanId(null)
    }
  }

  function closeModelWindow() {
    if (window.location.pathname.startsWith('/model/')) window.history.replaceState(null, '', '/library')
    setSelectedScan(null)
  }

  function closeScanDrawer() {
    if (window.location.pathname === '/scan') window.history.replaceState(null, '', '/library')
    setIsScanDrawerOpen(false)
  }

  function openScanDrawer(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault()
    if (window.location.pathname !== '/library') window.history.replaceState(null, '', '/library')
    setIsScanDrawerOpen(true)
  }

  function addScanFiles(files: File[]) {
    const kinds = files.map(fileKind)
    if (!files.length || kinds.some((kind) => kind === null)) {
      setUploadError('Use JPEG or PNG photos, or choose a supported video.')
      return
    }
    const kind = kinds[0]!
    if (kinds.some((item) => item !== kind)) {
      setUploadError('Photos and video must be uploaded in separate scans. Remove the current files to switch input type.')
      return
    }
    if (scanFiles.length && uploadKind !== kind) {
      setUploadError('Photos and video must be uploaded in separate scans. Remove the current files to switch input type.')
      return
    }
    if (kind === 'video' && (scanFiles.length || files.length > 1)) {
      setUploadError('Choose one video per scan. Remove the current files before choosing another video.')
      return
    }
    setUploadError('')
    setScanFiles((current) => [...current, ...files])
  }

  async function submitScan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!scanFiles.length) {
      setUploadError('Choose at least one photo or one video before starting the scan.')
      return
    }
    setScanProgress(0)
    setUploadError('')
    let scanId: string | undefined
    let jobAccepted = false
    try {
      const form = new FormData(event.currentTarget)
      const scan = await scansApi.create({
        name: String(form.get('name') ?? ''),
        subject_type: String(form.get('type') || 'Object'),
        subject: String(form.get('object') ?? '').trim() || null,
        description: String(form.get('description') ?? '').trim() || null,
      })
      scanId = scan.id
      for (const file of scanFiles) await scansApi.upload(scan.id, file)
      let job = await scansApi.start(scan.id)
      jobAccepted = true
      while (job.status === 'queued' || job.status === 'running') {
        setScanProgress(job.progress)
        await new Promise((resolve) => window.setTimeout(resolve, 3000))
        job = await scansApi.job(job.id)
      }
      if (job.status !== 'succeeded') throw new Error(job.error_message || 'The scan job failed.')
      setScanProgress(100)
      const [details] = await Promise.all([scansApi.get(scan.id), refreshScans()])
      const result = toScanCard(details)
      setIsScanDrawerOpen(false)
      setScanFiles([])
      setScanType('')
      window.history.replaceState({ scanId: scan.id }, '', `/model/${scan.id}`)
      setSelectedScan(result)
    } catch (error) {
      if (scanId && !jobAccepted) await scansApi.remove(scanId).catch(() => undefined)
      if (jobAccepted) await refreshScans().catch(() => undefined)
      setUploadError(error instanceof Error ? error.message : 'The scan could not be completed.')
    } finally {
      setScanProgress(null)
    }
  }

  async function exportArtifact(artifact: ScanArtifact | undefined) {
    if (!artifact) return
    try {
      const url = URL.createObjectURL(await scansApi.artifact(artifact.id))
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = artifact.filename
      anchor.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (error) {
      console.error('The scan result could not be downloaded.', error)
    }
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
              <button
                className="library-card-delete"
                type="button"
                aria-label={`${deletingScanId === scan.id ? 'Deleting' : 'Delete'} ${scan.name}`}
                disabled={deletingScanId === scan.id}
                onClick={() => { void deleteScan(scan) }}
              >
                {deletingScanId === scan.id ? 'Deleting…' : (
                  <>
                    <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3.5 5.5h13M8 5.5v-2h4v2m-6 0 .7 11h6.6l.7-11M8.5 8.5v5m3-5v5" /></svg>
                    Delete
                  </>
                )}
              </button>
              <div className="library-card-preview">
                <div className="library-card-media">
                  <PreviewPlaceholder />
                </div>
              </div>
              <div className="library-card-details">
                <div className="library-card-title-row">
                  <input
                    aria-label={`Rename ${scan.name}`}
                    value={scan.name}
                    onChange={(event) => renameScan(scan.id, event.target.value)}
                    onBlur={() => { void saveScanName(scan) }}
                  />
                  <span className="library-card-date">{scan.date}</span>
                  {scan.status !== 'ready' && scan.status !== 'draft' && (
                    <span className={`library-status library-status-${scan.status.toLowerCase()}`}>
                      {formatStatus(scan.status)}
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
        {hasLoadedScans && scans.length === 0 && (
          <div className="library-empty-state" role="status">
            <img src={rocketIcon} alt="" />
            <p>No objects yet</p>
          </div>
        )}
      </section>

      {selectedScan && (
        <div className="model-modal-backdrop" onClick={(event) => event.target === event.currentTarget && closeModelWindow()}>
          <div className="model-modal-frame">
            <section className="model-modal" id="model-preview-dialog" role="dialog" aria-modal="true" aria-label={`${selectedScan.name} model window`}>
              <div className="model-modal-content">
                <div className="model-modal-viewer">
                  <Suspense fallback={<div className="model-modal-loading"><img src={cycloneMark} alt="" /></div>}>
                    <ResultsViewer artifact={selectedArtifact} />
                  </Suspense>
                </div>
                <aside className="model-modal-details-panel" aria-label="Model details">
                  <div className="model-modal-details-scroll">
                  <section className="model-detail-section">
                    <div className="model-detail-heading-row">
                      <h2>{selectedScan.name}</h2>
                      <span className="model-detail-ready">{formatStatus(selectedScan.status)}</span>
                    </div>
                    {selectedScan.status === 'failed' && (
                      <div className="model-failed-actions">
                        <button type="button" className="model-retry-button" disabled={retryingScanId === selectedScan.id || deletingScanId === selectedScan.id} onClick={() => { void retryScan(selectedScan.id) }}>
                          {retryingScanId === selectedScan.id ? 'Retrying…' : 'Retry'}
                        </button>
                        <button type="button" className="model-delete-button" disabled={retryingScanId === selectedScan.id || deletingScanId === selectedScan.id} onClick={() => { void deleteScan(selectedScan) }}>
                          {deletingScanId === selectedScan.id ? 'Deleting…' : 'Delete'}
                        </button>
                      </div>
                    )}
                    {scanActionError && <p className="model-action-error" role="alert">{scanActionError}</p>}
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
                      {selectedImages.length ? (
                        <div className="model-original-image-viewer" aria-busy={sourceImageNavigating}>
                          <SourceAssetImage asset={selectedImages[sourceImageIndex]} name={selectedScan.name} index={sourceImageIndex} />
                          {sourceImageNavigating && <div className="model-original-image-navigation-loading" aria-hidden="true"><img src={cycloneMark} alt="" /></div>}
                          <button type="button" aria-label="Previous original image" disabled={selectedImages.length < 2 || sourceImageNavigating} onClick={() => { void changeSourceImage(-1) }}>
                            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m12.5 4.5-5.5 5.5 5.5 5.5" /></svg>
                          </button>
                          <span>{sourceImageIndex + 1} / {selectedImages.length}</span>
                          <button type="button" aria-label="Next original image" disabled={selectedImages.length < 2 || sourceImageNavigating} onClick={() => { void changeSourceImage(1) }}>
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
                      <div><dt>Vertices</dt><dd>{formatMetric(selectedJob?.metrics, ['vertices', 'vertex_count', 'num_vertices'])}</dd></div>
                      <div><dt>Faces</dt><dd>{formatMetric(selectedJob?.metrics, ['faces', 'face_count', 'triangles', 'triangle_count'])}</dd></div>
                      <div><dt>Texture</dt><dd>{formatMetric(selectedJob?.metrics, ['texture_resolution', 'texture_size', 'texture_pixels'])}</dd></div>
                      <div><dt>File size</dt><dd>{formatBytes(selectedArtifact?.size_bytes)}</dd></div>
                    </dl>
                  </section>

                  <section className="model-detail-section model-export-section">
                    <h2>Export</h2>
                    <div className="model-export-controls">
                      <div className="model-export-select-wrap">
                        <select aria-label="Export format" value={exportFormat} onChange={(event) => setExportFormat(event.target.value as 'GLB' | 'OBJ' | 'PLY')}>
                          <option value="GLB" disabled={!selectedExports.some((artifact) => fileExtension(artifact.filename) === 'glb')}>GLB</option>
                          <option value="OBJ" disabled={!selectedExports.some((artifact) => fileExtension(artifact.filename) === 'obj')}>OBJ</option>
                          <option value="PLY" disabled={!selectedExports.some((artifact) => fileExtension(artifact.filename) === 'ply')}>PLY</option>
                        </select>
                        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 7.5 5 5 5-5" /></svg>
                      </div>
                      <button type="button" className="model-export-button" disabled={!selectedExport} onClick={() => { void exportArtifact(selectedExport) }}>Export</button>
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
              <form className="scan-drawer-form" aria-busy={scanProgress !== null} onSubmit={(event) => { void submitScan(event) }}>
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
