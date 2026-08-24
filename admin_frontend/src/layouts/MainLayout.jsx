import { useEffect, useRef, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Menu, LogOut } from 'lucide-react';

import Navigation from '../components/Navigation.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';
import { useAuth } from '../providers/AuthProvider.jsx';
import useReveal from '../hooks/useReveal.js';
import useDialogChrome from '../hooks/useDialogChrome.js';
import useSwipeGuard from '../hooks/useSwipeGuard.js';

export default function MainLayout() {
  const location = useLocation();
  const contentRef = useRef(null);
  const sidebarRef = useRef(null);
  useReveal(contentRef);
  // Поведение модальных окон для тех, что собраны вручную мимо Modal.jsx.
  useDialogChrome();
  const { isMobile } = useViewport();
  // touch-action: pan-y в CSS не добивает системный edge-свайп Safari —
  // тут нужен активный preventDefault, см. хук.
  useSwipeGuard(sidebarRef, isMobile);
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

  // UserOut отдаёт display_name; поля name у него нет, поэтому здесь
  // всегда показывался логин, даже когда имя было заполнено.
  const userLabel = user?.display_name || user?.login || 'Администратор';

  return (
    <div className={`app-shell ${isMobile ? 'app-shell--mobile' : ''} ${!isMobile && navCollapsed ? 'app-shell--nav-collapsed' : ''}`}>
      <aside ref={sidebarRef} className={`app-shell__sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <Navigation
          onNavigate={() => setSidebarOpen(false)}
          collapsed={navCollapsed}
          onToggleCollapse={toggleCollapse}
        />
      </aside>

      {isMobile && sidebarOpen && <div className="app-shell__backdrop" onClick={() => setSidebarOpen(false)} />}

      <div className="app-shell__main">
        {!isMobile && (
          <div className="fui-topline app-shell__topline">
            <span className="fui-topline__dot" />
            СИСТЕМА АКТИВНА <span className="fui-topline__sep">/</span> {userLabel} <span className="fui-topline__sep">/</span> {new Date().toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })}
          </div>
        )}
        <header className="app-shell__header">
          {isMobile && (
            <button type="button" className="icon-button" onClick={() => setSidebarOpen(o => !o)} aria-label="Открыть меню">
              <Menu size={20} />
            </button>
          )}
          <div className="app-shell__brand">
            Центр управления
          </div>
          <div className="app-shell__user">
            {/* title — для десктопа: имя сокращается многоточием только
                когда не помещается, и наведение показывает его целиком.
                Скринридеру многоточие не мешает в принципе: text-overflow
                прячет текст визуально, в DOM он остаётся полным. */}
            <span className="app-shell__user-name" title={userLabel}>{userLabel}</span>
            <button type="button" className="icon-button icon-button--ghost" onClick={handleLogout} aria-label="Выйти">
              <LogOut size={18} />
              <span>Выход</span>
            </button>
          </div>
        </header>
        {/* key от пути: без него React переиспользует этот узел между
            маршрутами, CSS-анимация появления не перезапускается, и
            переход между разделами выглядит мгновенной подменой.

            Тот же key пересоздаёт и наблюдатель проявления — он один на
            весь экран и следит за всем поддеревом, поэтому странице
            достаточно повесить класс .ui-reveal, ничего не подключая. */}
        <main className="app-shell__content" key={location.pathname} ref={contentRef}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
