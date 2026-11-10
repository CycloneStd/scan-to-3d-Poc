# Scan-to-3D WebXR

Vite serves the dark HTML landing page from `index.html`. Its styles and small menu script are separated from the document. The Mirage font and shared UI foundation remain local assets.

## Source layout

```text
webxr/
├── index.html
├── src/
│   ├── assets/
│   │   └── fonts/           # Local font files and font-face styles
│   ├── scripts/
│   │   └── mobile-auth-menu.js
│   └── styles/
│       ├── components.css   # Shared styles exported with the landing design
│       ├── foundation.css    # Shared tokens and utility styles
│       └── landing.css      # Landing page theme and overrides
├── package.json
├── tsconfig.json
└── vite.config.ts
```

The landing page stays in HTML. Add the product workflow in React under `src/app`, `src/pages`, `src/features`, and `src/components`; keep route components named in PascalCase (for example, `ScanLibraryPage.tsx`) and utility files in kebab-case. Those React folders will be introduced with the first workflow page rather than left as empty scaffolding.

## Planned product flow

1. Authentication: sign in, sign up, and password recovery.
2. Library: search, filters, scan status, and a new scan action.
3. New scan: image or video upload and scan settings.
4. Processing: reconstruction stages and progress.
5. Result viewer: 3D inspection and exports.

Authentication, uploads, processing jobs, and managed scan storage are not connected to the Python pipeline yet. Vite exposes `../web/assets` as its public directory for generated reconstruction assets.

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
