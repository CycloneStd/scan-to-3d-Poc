# Scan3D WebXR prototype

The browser client workspace for the Scan-to-3D demonstration. It is intentionally isolated from the Python pipeline and the existing static viewer in `web/`. This folder contains tooling only; interface and application code will be defined separately with the UI.

## Stack

- React + TypeScript + Vite as the planned app and build stack.
- Three.js for the planned browser 3D scene and WebXR session integration.
- Spark is included as the intended Gaussian-splat renderer for connecting real pipeline outputs.
- The existing Python pipeline remains the reconstruction runtime; this app will later talk to a small Python API for scan metadata, uploads, job state, and result URLs.

No UI, routes, authentication, API integration, or sample screens are included yet.

## Run locally

```bash
npm install
npm run dev
```

For headset testing, serve the app from HTTPS (localhost is treated as a secure context for local development) and use a browser/device with WebXR support. WebXR support varies by browser and hardware.

## Build

```bash
npm run build
```

When UI work begins, connect the chosen viewer to the exported Gaussian splat or mesh assets and keep API/job orchestration in Python so the existing pipeline remains the source of reconstruction truth.
