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

  useEffect(() => {
    setSidebarOpen(!isMobile);
  }, [isMobile]);

  const toggleSidebar = () => setSidebarOpen((prev) => !prev);
  const closeSidebar = () => setSidebarOpen(false);

  const handleLogout = async () => {
    try {
      await logout();
    } catch (err) {
      console.error(err);
    }
  };

  const userLabel = user?.name || user?.login || 'Администратор';

  return (
    <div className={`app-shell ${isMobile ? 'app-shell--mobile' : ''}`}>
      <aside className={`app-shell__sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <Navigation onNavigate={closeSidebar} />
      </aside>

      {isMobile && sidebarOpen && <div className="app-shell__backdrop" onClick={closeSidebar} />}

      <div className="app-shell__main">
        <header className="app-shell__header">
          {isMobile && (
            <button type="button" className="icon-button" onClick={toggleSidebar} aria-label="Открыть меню">
              <Menu size={20} />
            </button>
          )}
          <div className="app-shell__brand">
            <span className="app-shell__brand-accent" />
            HR Панель управления
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




