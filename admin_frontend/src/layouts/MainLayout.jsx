import { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Menu, LogOut } from 'lucide-react';

import Navigation from '../components/Navigation.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';
import { useAuth } from '../providers/AuthProvider.jsx';

export default function MainLayout() {
  const { isMobile } = useViewport();
  const { user, logout } = useAuth();

  // On desktop: collapsed = icons-only sidebar. On mobile: sidebar hidden/open.
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (isMobile) setMobileOpen(false);
  }, [isMobile]);

  const toggleCollapse = () => setCollapsed((v) => !v);
  const closeMobile = () => setMobileOpen(false);
  const openMobile = () => setMobileOpen(true);

  const handleLogout = async () => {
    try { await logout(); } catch (err) { console.error(err); }
  };

  const userLabel = user?.name || user?.login || 'Администратор';

  const shellClass = [
    'app-shell',
    isMobile ? 'app-shell--mobile' : '',
    !isMobile && collapsed ? 'app-shell--collapsed' : '',
  ].filter(Boolean).join(' ');

  return (
    <div className={shellClass}>
      <aside className={`app-shell__sidebar ${isMobile ? (mobileOpen ? 'is-open' : '') : 'is-open'}`}>
        <Navigation
          onNavigate={closeMobile}
          collapsed={collapsed}
          onToggleCollapse={toggleCollapse}
        />
      </aside>

      {isMobile && mobileOpen && <div className="app-shell__backdrop" onClick={closeMobile} />}

      <div className="app-shell__main">
        <header className="app-shell__header">
          {isMobile && (
            <button type="button" className="icon-button" onClick={openMobile} aria-label="Открыть меню">
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
