import { useEffect, useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import {
  LogOut, Menu, X, DollarSign, CreditCard, Calendar, User, History, Wallet, Wrench, ScanLine,
  Package, Factory,
  Target,
} from 'lucide-react';
import { useAuth } from '../providers/AuthProvider.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';
import { useTheme } from '../providers/ThemeProvider.jsx';
import MasterAppUpdate from '../components/MasterAppUpdate.jsx';
import api from '../api.js';
import useBackClose from '../hooks/useBackClose.js';

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
// Менеджеру по работе с клиентами — «Мой KPI» первым пунктом: зарплата у
// него считается от плана и amoCRM, а не из Excel админов.
const MANAGER_KPI_ITEM = { to: '/employee/kpi', label: 'Мой KPI', icon: Target };
const WORKSHOP_NAV_ITEM = { to: '/employee/workshop', label: 'Цех', icon: Factory };

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
  const { setForced } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  useBackClose(menuOpen, () => setMenuOpen(false));
  const [onPoint, setOnPoint] = useState(false);

  // Кабинет сотрудника всегда светлый, какая бы тема ни стояла в телефоне.
  useEffect(() => {
    setForced('light');
    return () => setForced(null);
  }, [setForced]);

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
  const baseItems = user?.is_master ? MASTER_NAV_ITEMS
    : user?.is_manager ? [MANAGER_KPI_ITEM, ...NAV_ITEMS.filter((i) => i.to !== '/employee/salary')]
    : onPoint ? SALON_NAV_ITEMS : NAV_ITEMS;
  // «Цех» — по праву, а не по должности: старшим мастером может быть и мастер,
  // и руководитель отдела пошива. Встаёт первым пунктом.
  const hasWorkshop = (user?.permissions || []).includes('workshop');
  const navItems = hasWorkshop ? [WORKSHOP_NAV_ITEM, ...baseItems] : baseItems;
  // В нижней панели больше шести пунктов не помещаются (подписи обрезаются):
  // «История» остаётся в меню, из панели уходит.
  const bottomItems = navItems.length > 6
    ? navItems.filter((i) => i.to !== '/employee/history')
    : navItems;

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
          {bottomItems.map(({ to, label, icon: Icon }) => (
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
