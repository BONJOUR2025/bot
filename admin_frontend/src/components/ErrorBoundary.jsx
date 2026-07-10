import { Component } from 'react';

// After every frontend deploy, `dist/` is rebuilt with new hashed chunk
// filenames and the old ones are gone. A tab that was already open before
// the deploy still holds references to the old chunk names, so the next
// lazy-loaded route (React.lazy in App.jsx) 404s instead of loading — with
// no boundary here, React just unmounts to a blank screen. Reloading once
// picks up the fresh index.html/chunk map and fixes it; the sessionStorage
// guard stops a reload loop if the failure isn't actually deploy-related.
const RELOAD_GUARD_KEY = 'app-error-reload-guard';
const RELOAD_GUARD_WINDOW_MS = 10_000;

function tryAutoReload() {
  const last = Number(sessionStorage.getItem(RELOAD_GUARD_KEY) || 0);
  const now = Date.now();
  if (now - last > RELOAD_GUARD_WINDOW_MS) {
    sessionStorage.setItem(RELOAD_GUARD_KEY, String(now));
    window.location.reload();
    return true;
  }
  return false;
}

if (typeof window !== 'undefined') {
  window.addEventListener('vite:preloadError', () => {
    tryAutoReload();
  });
}

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, reloaded: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch() {
    const reloaded = tryAutoReload();
    if (reloaded) this.setState({ reloaded: true });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center gap-3 py-24 px-6 text-center">
          <div className="text-lg font-semibold">
            {this.state.reloaded ? 'Обновляем страницу…' : 'Не удалось загрузить страницу'}
          </div>
          <div className="text-sm text-[color:var(--color-muted-foreground)] max-w-sm">
            Обычно это происходит сразу после обновления приложения на сервере.
          </div>
          {!this.state.reloaded && (
            <button className="btn btn--primary" onClick={() => window.location.reload()}>
              Обновить страницу
            </button>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}
