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

The FastAPI backend, authentication flows, scan/job APIs, worker, and storage adapters are in [`backend/`](backend/README.md). Authentication, scan/library data, uploads, jobs, and results use the API. Vite exposes `../web/assets` as its public directory for generated reconstruction assets.

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
## Run the web prototype locally

Run the frontend locally against Railway for the lightweight setup, or start the optional local Docker stack in [backend/README.md](backend/README.md). Both use the same application code; only environment configuration selects the service URLs and storage backend.

1. Deploy the Railway API and worker, and provision Railway PostgreSQL, Redis, and S3-compatible storage, using [backend/README.md](backend/README.md).
2. Add `http://localhost:5173` to the Railway API's `WEBXR_CORS_ORIGINS`. Keep the deployed website origin too. Use a separate Railway environment and data services for development so local testing doesn't alter production data.
3. Configure the frontend and install its dependencies:

   ```powershell
   cd webxr
   Copy-Item .env.example .env.local
   # Set VITE_API_BASE_URL to https://<api-domain>/api/v1 in .env.local
   npm ci
   ```

4. Start Vite:

   ```powershell
   npm run dev
   ```

Open `http://localhost:5173`. The frontend sends requests to the Railway API, and jobs run on the Railway worker. Requests from local development use whichever Railway environment is configured by that API URL.
