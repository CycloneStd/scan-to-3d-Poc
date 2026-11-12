# Scan-to-3D WebXR

Vite serves the dark HTML landing page from `index.html`. Its styles and small menu script are separated from the document. The Mirage font and shared UI foundation remain local assets.

## Source layout

```text
webxr/
├── index.html
├── src/
│   ├── assets/
│   │   └── fonts/           # Local font files and font-face styles
│   ├── main.tsx              # Mounts React pages on application routes
│   ├── pages/
│   │   └── auth/
│   │       └── LoginPage.tsx # React login page at /login
│   ├── scripts/
│   │   └── mobile-auth-menu.js
│   └── styles/
│       ├── components.css   # Shared styles exported with the landing design
│       ├── components/
│       │   └── input.css    # Input component styles
│       ├── foundation.css    # Shared tokens and utility styles
│       ├── landing.css      # Landing page theme and overrides
│       └── login.css        # Login page layout
├── package.json
├── tsconfig.json
└── vite.config.ts
```

The landing page stays in HTML. Product pages are React components in `src/pages`, mounted by `src/main.tsx` when their route is requested. The Vite development server serves `index.html` as the app shell for `/login`; no separate login HTML file is needed. Route components use PascalCase names, and utilities use kebab-case.

## Planned product flow

1. Authentication: sign in, sign up, and password recovery.
2. Library: search, filters, scan status, and a new scan action.
3. New scan: image or video upload and scan settings.
4. Processing: reconstruction stages and progress.
5. Result viewer: 3D inspection and exports.

The independent FastAPI backend, authentication flows, scan/job APIs, worker, and storage adapters are scaffolded in [`backend/`](backend/README.md). The Vite/React frontend is not integrated with it yet. Vite exposes `../web/assets` as its public directory for generated reconstruction assets.

## Local development

```bash
npm install
npm run dev
```

## Production build

```bash
npm run build
npm run preview
```

`dist/` is generated output and is ignored by Git. Recreate it with `npm run build` when needed.
