import '../styles/library.css'

export default function NotFoundPage() {
  return (
    <main className="min-h-svh flex flex-col items-center justify-center gap-2 px-6 text-center">
      <h1 className="type-surface-title-lg -strong text-surface">404</h1>
      <p className="type-surface-title-sm -strong text-surface-muted">Not Found</p>
      <a className="library-page-nav-link mt-8" href="/" style={{ backgroundColor: '#000', minWidth: '180px', minHeight: '56px', paddingInline: '24px', fontSize: '16px' }}>Back to Home</a>
    </main>
  )
}
