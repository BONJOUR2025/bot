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
    <nav className="flex h-full min-h-screen w-full flex-col bg-[color:var(--color-sidebar)] text-[color:var(--color-sidebar-foreground)] shadow-xl sm:w-[280px]">
      <div className="flex items-center gap-4 px-6 pb-5 pt-7">
        <div className="grid h-11 w-11 place-items-center rounded-xl bg-[color:var(--color-sidebar-primary)] text-[color:var(--color-sidebar-primary-foreground)] shadow-[0_10px_30px_rgba(0,0,0,0.12)]">
          HR
        </div>
        <div className="flex flex-col text-sm">
          <span className="text-base font-semibold leading-tight">Админ-панель</span>
          <span className="text-[13px] text-[color:var(--color-muted-foreground)]">
            Управление персоналом
          </span>
        </div>
        {isMobile && (
          <button
            type="button"
            className="ml-auto inline-flex h-9 w-9 items-center justify-center rounded-full border border-[color:var(--color-sidebar-border)] bg-transparent text-[color:var(--color-sidebar-foreground)] transition hover:bg-[color:var(--color-sidebar-accent)] hover:text-[color:var(--color-sidebar-accent-foreground)]"
            onClick={handleClose}
            aria-label="Закрыть меню"
          >
            <X size={18} />
          </button>
        )}
      </div>

      <div className="flex-1 space-y-7 overflow-y-auto px-6 pb-8">
        {itemsByCategory.map((category) => (
          <div key={category.name} className="space-y-3">
            <div className="text-xs font-medium uppercase tracking-[0.12em] text-[color:var(--color-muted-foreground)]">
              {category.name}
            </div>
            <div className="space-y-1">
              {category.items.map((item) => {
                const activeClasses = item.active
                  ? 'bg-[color:var(--color-sidebar-primary)] text-[color:var(--color-sidebar-primary-foreground)] shadow-[0_18px_38px_rgba(3,2,19,0.22)]'
                  : 'text-[color:var(--color-sidebar-foreground)] opacity-75 hover:bg-[color:var(--color-sidebar-accent)] hover:text-[color:var(--color-sidebar-accent-foreground)] hover:opacity-100';

                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    onClick={handleNavigate}
                    className={`flex items-center justify-between rounded-xl border border-transparent px-4 py-2 text-sm font-medium transition-all duration-150 ${activeClasses}`}
                  >
                    <span>{item.label}</span>
                    <span className="h-1.5 w-1.5 rounded-full bg-current opacity-40" />
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-[color:var(--color-sidebar-border)] px-6 py-5 text-xs text-[color:var(--color-muted-foreground)] opacity-90">
        © {new Date().getFullYear()} HR Platform
      </div>
    </nav>
  );
}
