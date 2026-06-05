import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  base: '/admin/',
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      base: '/admin/',
      manifest: {
        name: 'Штаб',
        short_name: 'Штаб',
        start_url: '/admin/',
        display: 'standalone',
        background_color: '#ffffff',
        theme_color: '#1e40af',
        icons: [
          {
            src: '/admin/vite.svg',
            sizes: 'any',
            type: 'image/svg+xml',
          },
        ],
      },
    }),
  ],
})
