import { useMemo } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { X } from 'lucide-react';

import { useAuth } from '../providers/AuthProvider.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';

const navStructure = [
  {
    name: 'Обзор',
    items: [{ to: '/admin', label: 'Дашборд', permission: 'dashboard' }],
  },
  {
    name: 'Персонал',
    items: [
      { to: '/admin/employees', label: 'Сотрудники', permission: 'employees' },
      { to: '/admin/vacations', label: 'Отпуска', permission: 'vacations' },
      { to: '/admin/birthdays', label: 'Дни рождения', permission: 'birthdays' },
      { to: '/admin/assets', label: 'Имущество', permission: 'assets' },
    ],
  },
  {
    name: 'Финансы',
    items: [
      { to: '/admin/payouts', label: 'Выплаты', permission: 'payouts' },
      { to: '/admin/payouts-control', label: 'Контроль выплат', permission: 'payouts-control' },
      { to: '/admin/incentives', label: 'Штрафы и премии', permission: 'incentives' },
      { to: '/admin/reports', label: 'Отчёты', permission: 'reports' },
    ],
  },
  {
    name: 'Управление',
    items: [
      { to: '/admin/broadcast', label: 'Рассылка', permission: 'broadcast' },
      { to: '/admin/messages', label: 'История сообщений', permission: 'messages' },
      { to: '/admin/dictionary', label: 'Словарь', permission: 'dictionary' },
      { to: '/admin/settings', label: 'Настройки', permission: 'settings' },
      { to: '/admin/access', label: 'Доступ', permission: 'access' },
    ],
  },
];

export default function Navigation({ onNavigate }) {
  const location = useLocation();
  const { user } = useAuth();
  const { isMobile } = useViewport();
  const allowed = useMemo(() => new Set(user?.permissions || []), [user?.permissions]);
  const handleNavigate = () => {
    if (isMobile && typeof onNavigate === 'function') {
      onNavigate();
    }
  };

  const handleClose = () => {
    if (typeof onNavigate === 'function') {
      onNavigate();
    }
  };

  const itemsByCategory = useMemo(
    () =>
      navStructure
        .map((category) => ({
          ...category,
          items: category.items
            .filter((item) => !item.permission || allowed.has(item.permission))
            .map((item) => ({
              ...item,
              active:
                location.pathname === item.to || location.pathname.startsWith(`${item.to}/`),
            })),
        }))
        .filter((category) => category.items.length > 0),
    [location.pathname, allowed],
  );

  return (
    <nav className="sidebar">
      <div className="sidebar__header">
        <div className="sidebar__badge">HR</div>
        <div className="sidebar__title">
          <div className="sidebar__title-main">Админ-панель</div>
          <div className="sidebar__title-sub">Управление персоналом</div>
        </div>
        {isMobile && (
          <button type="button" className="icon-button icon-button--ghost" onClick={handleClose} aria-label="Закрыть меню">
            <X size={18} />
          </button>
        )}
      </div>

      <div className="sidebar__sections">
        {itemsByCategory.map((category) => (
          <div key={category.name} className="sidebar__section">
            <div className="sidebar__section-label">{category.name}</div>
            <div className="sidebar__links">
              {category.items.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  onClick={handleNavigate}
                  className={`sidebar__link ${item.active ? 'is-active' : ''}`}
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>
    </nav>
  );
}
