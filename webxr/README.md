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

The FastAPI backend, authentication flows, scan/job APIs, worker, and storage adapters are in [`backend/`](backend/README.md). Authentication is connected to the API; the scan/library pages remain on their existing frontend implementation. Vite exposes `../web/assets` as its public directory for generated reconstruction assets.

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

Run the frontend and API natively on Windows; keep PostgreSQL, Redis, object storage, and the heavy scan worker on Railway. This avoids local Docker and the COLMAP/Blender worker image while still exercising the local API against the remote queue and storage.

1. Deploy the Railway API and worker, and provision Railway PostgreSQL, Redis, and S3-compatible storage, using [backend/README.md](backend/README.md).
2. Add `http://localhost:5173` to the Railway API's `WEBXR_CORS_ORIGINS`. Keep the deployed website origin too. Use a separate Railway environment and data services for development so local testing doesn't alter production data.
3. Install the small API dependency set and Railway CLI once from the repository root:

   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\python -m pip install -r webxr\backend\requirements.txt
   npm install --global @railway/cli
   railway login
   railway link
   ```

4. In one terminal, run the API locally with the Railway API service variables:

   ```powershell
   cd webxr\backend
   railway run --service api ..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

5. In a second terminal, set up and run Vite:

   ```powershell
   cd webxr
   Copy-Item .env.example .env.local
   npm run dev
   ```

Open `http://localhost:5173`. The local API reads Railway's database, Redis, and S3 settings; jobs enter the Railway queue and run on the Railway worker. If you prefer, point `VITE_API_BASE_URL` in `.env.local` at the Railway API domain and skip running the local API. Install Node dependencies with `npm ci` only if `node_modules` is missing or `package-lock.json` changed.
