import { useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { LogOut, Menu, X, DollarSign, CreditCard, Calendar, User } from 'lucide-react';
import { useAuth } from '../providers/AuthProvider.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';

const NAV_ITEMS = [
  { to: '/employee/salary', label: 'Зарплата', icon: DollarSign },
  { to: '/employee/payouts', label: 'Авансы', icon: CreditCard },
  { to: '/employee/schedule', label: 'График', icon: Calendar },
  { to: '/employee/profile', label: 'Профиль', icon: User },
];

export default function EmployeeLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { isMobile } = useViewport();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate('/employee/login', { replace: true });
  };

  const displayName = user?.display_name || user?.login || 'Сотрудник';

  return (
    <div className="emp-shell">
      <header className="emp-header">
        <div className="emp-header__brand">
          <span className="emp-header__logo">HR</span>
          <span className="emp-header__title">Личный кабинет</span>
        </div>
        <div className="emp-header__right">
          <span className="emp-header__name">{displayName}</span>
          {isMobile ? (
            <button
              type="button"
              className="icon-button"
              onClick={() => setMenuOpen((v) => !v)}
              aria-label="Меню"
            >
              {menuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          ) : (
            <button
              type="button"
              className="icon-button icon-button--ghost"
              onClick={handleLogout}
              aria-label="Выйти"
            >
              <LogOut size={18} />
              <span>Выход</span>
            </button>
          )}
        </div>
      </header>

      {isMobile && menuOpen && (
        <nav className="emp-nav emp-nav--mobile">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `emp-nav__item ${isActive ? 'emp-nav__item--active' : ''}`
              }
              onClick={() => setMenuOpen(false)}
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
          <button type="button" className="emp-nav__item emp-nav__logout" onClick={handleLogout}>
            <LogOut size={18} />
            Выход
          </button>
        </nav>
      )}

      <div className="emp-body">
        {!isMobile && (
          <aside className="emp-sidebar">
            <nav className="emp-nav">
              {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    `emp-nav__item ${isActive ? 'emp-nav__item--active' : ''}`
                  }
                >
                  <Icon size={18} />
                  {label}
                </NavLink>
              ))}
            </nav>
          </aside>
        )}
        <main className="emp-content">
          <Outlet />
        </main>
      </div>

      {isMobile && (
        <nav className="emp-bottomnav">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `emp-bottomnav__item ${isActive ? 'emp-bottomnav__item--active' : ''}`
              }
            >
              <Icon size={20} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  );
}
