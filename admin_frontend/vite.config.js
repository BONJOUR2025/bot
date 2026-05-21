import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VitePWA removed: we use a hand-crafted sw.js in public/ for Web Push.
// VitePWA would generate a second service worker and conflict with it.

export default defineConfig({
  base: '/admin/',
  plugins: [react()],
})
