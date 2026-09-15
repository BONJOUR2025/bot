import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { IN_MASTER_APP } from './utils/masterApp.js'

// Внутри приложения «BONJOUR Мастер» часть оформления выключается стилями
// (см. .in-master-app в globals.css). Класс ставится до первой отрисовки,
// чтобы фоновая анимация не успела запуститься.
if (IN_MASTER_APP) {
  document.documentElement.classList.add('in-master-app')
}

// Register service worker for push notifications.
// Path must match the app base (/admin/) so the browser doesn't request /sw.js
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/admin/sw.js').catch(() => {});
  });
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

