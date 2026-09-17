import { useEffect, useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import {
  LogOut, Menu, X, DollarSign, CreditCard, Calendar, User, History, Wallet, Wrench, ScanLine,
  Package,
} from 'lucide-react';
import { useAuth } from '../providers/AuthProvider.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';
import MasterAppUpdate from '../components/MasterAppUpdate.jsx';
import api from '../api.js';

// «Отгулов» и «Связи» в меню нет ни у кого — так решил руководитель. Страницы
// (/employee/leave-requests, /employee/feedback) остались и открываются по
// прямой ссылке, из меню их убрали.
const NAV_ITEMS = [
  { to: '/employee/salary', label: 'Зарплата', icon: DollarSign },
  { to: '/employee/payouts', label: 'Авансы', icon: CreditCard },
  { to: '/employee/history', label: 'История', icon: History },
  { to: '/employee/schedule', label: 'График', icon: Calendar },
  { to: '/employee/profile', label: 'Профиль', icon: User },
];

// У мастера нет «Зарплаты» и «Графика»: оба раздела читают «ФОТ админы *.xlsx»,
// где мастеров нет, и всегда показывали бы «данных нет». Заработок мастера
// считается по сканам — тот же набор, что меню мастера в Telegram-боте.
// «Скан» — вход и выход по бирке (запись в Агбис — флаг AGBIS_SCAN_WRITE).
const MASTER_NAV_ITEMS = [
  { to: '/employee/earnings', label: 'Заработок', icon: Wallet },
  { to: '/employee/wip', label: 'В работе', icon: Wrench },
  { to: '/employee/scan', label: 'Скан', icon: ScanLine },
  { to: '/employee/payouts', label: 'Авансы', icon: CreditCard },
  { to: '/employee/history', label: 'История', icon: History },
  { to: '/employee/profile', label: 'Профиль', icon: User },
];

// Меню администратора точки (приложение «BONJOUR Салон»). Это личный кабинет
// с тем же набором, что кнопки бота у администратора, плюс «Имущество»:
// рабочих инструментов точки (выручка, заказы клиентов) здесь намеренно нет.
// Показывается тем, за кем закреплён салон: это решает сервер
// (GET /salon/me/point), а не роль — точка живёт в карточке салона, не в правах.
const SALON_NAV_ITEMS = [
  { to: '/employee/salary', label: 'Зарплата', icon: DollarSign },
  { to: '/employee/schedule', label: 'График', icon: Calendar },
  { to: '/employee/payouts', label: 'Авансы', icon: CreditCard },
  { to: '/employee/history', label: 'История', icon: History },
  { to: '/employee/assets', label: 'Имущество', icon: Package },
  { to: '/employee/profile', label: 'Профиль', icon: User },
];

export default function EmployeeLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { isMobile } = useViewport();
  const [menuOpen, setMenuOpen] = useState(false);
  const [onPoint, setOnPoint] = useState(false);

  useEffect(() => {
    if (user?.is_master || !user?.employee_id) return undefined;
    let alive = true;
    api
      .get('/salon/me/point')
      .then(() => alive && setOnPoint(true))
      .catch(() => alive && setOnPoint(false));
    return () => {
      alive = false;
    };
  }, [user?.is_master, user?.employee_id]);

  const handleLogout = async () => {
    await logout();
    navigate('/employee/login', { replace: true });
  };

  const displayName = user?.display_name || user?.login || 'Сотрудник';
  const navItems = user?.is_master ? MASTER_NAV_ITEMS : onPoint ? SALON_NAV_ITEMS : NAV_ITEMS;

  return (
    <div className="emp-shell">
      <header className="emp-header">
        <div className="emp-header__brand">
          <span className="emp-header__logo">B</span>
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
          {navItems.map(({ to, label, icon: Icon }) => (
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
              {navItems.map(({ to, label, icon: Icon }) => (
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
          <MasterAppUpdate />
          <Outlet />
        </main>
      </div>

      {isMobile && (
        <nav className="emp-bottomnav">
          {navItems.map(({ to, label, icon: Icon }) => (
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
