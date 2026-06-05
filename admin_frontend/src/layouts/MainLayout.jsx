import { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Menu, LogOut } from 'lucide-react';

import Navigation from '../components/Navigation.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';
import { useAuth } from '../providers/AuthProvider.jsx';

export default function MainLayout() {
  const { isMobile } = useViewport();
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(!isMobile);
  const [navCollapsed, setNavCollapsed] = useState(() => {
    try { return localStorage.getItem('nav_collapsed') === 'true'; } catch { return false; }
  });

  useEffect(() => { setSidebarOpen(!isMobile); }, [isMobile]);

  function toggleCollapse() {
    setNavCollapsed(prev => {
      const next = !prev;
      try { localStorage.setItem('nav_collapsed', String(next)); } catch {}
      return next;
    });
  }

  const handleLogout = async () => {
    try { await logout(); } catch (err) { console.error(err); }
  };

  const userLabel = user?.name || user?.login || 'Администратор';

  return (
    <div className={`app-shell ${isMobile ? 'app-shell--mobile' : ''} ${!isMobile && navCollapsed ? 'app-shell--nav-collapsed' : ''}`}>
      <aside className={`app-shell__sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <Navigation
          onNavigate={() => setSidebarOpen(false)}
          collapsed={navCollapsed}
          onToggleCollapse={toggleCollapse}
        />
      </aside>

      {isMobile && sidebarOpen && <div className="app-shell__backdrop" onClick={() => setSidebarOpen(false)} />}

      <div className="app-shell__main">
        <header className="app-shell__header">
          {isMobile && (
            <button type="button" className="icon-button" onClick={() => setSidebarOpen(o => !o)} aria-label="Открыть меню">
              <Menu size={20} />
            </button>
          )}
          <div className="app-shell__brand">
            <span className="app-shell__brand-accent" />
            Центр управления
          </div>
          <div className="app-shell__user">
            <span className="app-shell__user-name">{userLabel}</span>
            <button type="button" className="icon-button icon-button--ghost" onClick={handleLogout} aria-label="Выйти">
              <LogOut size={18} />
              <span>Выход</span>
            </button>
          </div>
        </header>
        <main className="app-shell__content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
