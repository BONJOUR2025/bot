import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// VitePWA removed: we use a hand-crafted sw.js in public/ for Web Push.
// VitePWA would generate a second service worker and conflict with it.

export default defineConfig({
  base: '/admin/',
  plugins: [react()],
  // Только для `npm run dev`: на сборку (`npm run build`) секция server не
  // влияет вообще. Без прокси фронт в деве стучится в /api на порт самого
  // Vite, где ничего нет, — залогиниться невозможно, и посмотреть работу
  // с настоящими данными не получается. Локальный FastAPI (pm2: bot-app)
  // слушает 8000.
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/static': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
