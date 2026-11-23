import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Serve pipeline-generated models and textures at the site root.
  publicDir: '../web/assets',
  server: {
    host: '0.0.0.0',
  },
})
