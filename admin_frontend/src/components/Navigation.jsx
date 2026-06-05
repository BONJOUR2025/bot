import { useMemo } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { X, PanelLeftClose } from 'lucide-react';

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
      { to: '/admin/archive', label: 'Архив', permission: 'employees' },
      { to: '/admin/schedule', label: 'Расписание', permission: 'employees' },
      { to: '/admin/vacations', label: 'Отпуска', permission: 'vacations' },
      { to: '/admin/birthdays', label: 'Дни рождения', permission: 'birthdays' },
      { to: '/admin/assets', label: 'Имущество', permission: 'assets' },
      { to: '/admin/salons', label: 'Салоны', permission: 'salons' },
    ],
  },
  {
    name: 'Финансы',
    items: [
      { to: '/admin/payroll', label: 'Расчёт зарплаты', permission: 'payroll' },
      { to: '/admin/location-plans', label: 'Планы по точкам', permission: 'payroll' },
      { to: '/admin/masters', label: 'Работы мастеров', permission: 'payroll' },
      { to: '/admin/payouts', label: 'Выплаты', permission: 'payouts' },
      { to: '/admin/payouts-control', label: 'Контроль выплат', permission: 'payouts-control' },
      { to: '/admin/incentives', label: 'Штрафы и премии', permission: 'incentives' },
      { to: '/admin/cash-moves', label: 'Кассовые перемещения', permission: 'cash-moves' },
    ],
  },
  {
    name: 'Аналитика',
    items: [
      { to: '/admin/sales', label: 'Продажи', permission: 'payroll' },
      { to: '/admin/reports', label: 'Отчёты', permission: 'reports' },
    ],
  },
  {
    name: 'Операции',
    items: [
      { to: '/admin/tasks', label: 'Задачи', permission: 'tasks' },
      { to: '/admin/broadcast', label: 'Рассылка', permission: 'broadcast' },
      { to: '/admin/messages', label: 'История сообщений', permission: 'messages' },
    ],
  },
  {
    name: 'Система',
    items: [
      { to: '/admin/dictionary', label: 'Словарь', permission: 'dictionary' },
      { to: '/admin/passwords', label: 'Пароли', permission: 'passwords' },
      { to: '/admin/access', label: 'Доступ', permission: 'access' },
      { to: '/admin/settings', label: 'Настройки', permission: 'settings' },
    ],
  },
];

export default function Navigation({ onNavigate, onCollapse, sidebarOpen }) {
  const location = useLocation();
  const { user } = useAuth();
  const { isMobile } = useViewport();
  const allowed = useMemo(() => new Set(user?.permissions || []), [user?.permissions]);

  const handleNavigate = () => {
    if (isMobile && typeof onNavigate === 'function') {
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
      <div className="flex items-center gap-3 px-5 pb-4 pt-6">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[color:var(--color-sidebar-primary)] text-[color:var(--color-sidebar-primary-foreground)] text-xs font-bold shadow">
          ШТ
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold leading-tight truncate">Штаб</div>
          <div className="text-[11px] text-[color:var(--color-muted-foreground)] truncate">Панель управления</div>
        </div>
        {/* Collapse / close button */}
        {isMobile ? (
          <button
            type="button"
            className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[color:var(--color-sidebar-border)] text-[color:var(--color-sidebar-foreground)] hover:bg-[color:var(--color-sidebar-accent)] transition"
            onClick={onNavigate}
            aria-label="Закрыть меню"
          >
            <X size={16} />
          </button>
        ) : (
          <button
            type="button"
            className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[color:var(--color-sidebar-border)] text-[color:var(--color-sidebar-foreground)] hover:bg-[color:var(--color-sidebar-accent)] transition"
            onClick={onCollapse}
            aria-label="Свернуть меню"
            title="Свернуть"
          >
            <PanelLeftClose size={16} />
          </button>
        )}
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto px-4 pb-8">
        {itemsByCategory.map((category) => (
          <div key={category.name} className="space-y-1">
            <div className="px-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--color-muted-foreground)] mb-1">
              {category.name}
            </div>
            {category.items.map((item) => {
              const activeClasses = item.active
                ? 'bg-[color:var(--color-sidebar-primary)] text-[color:var(--color-sidebar-primary-foreground)] shadow-sm'
                : 'text-[color:var(--color-sidebar-foreground)] opacity-70 hover:bg-[color:var(--color-sidebar-accent)] hover:text-[color:var(--color-sidebar-accent-foreground)] hover:opacity-100';

              return (
                <Link
                  key={item.to}
                  to={item.to}
                  onClick={handleNavigate}
                  className={`flex items-center rounded-lg px-3 py-2 text-sm font-medium transition-all duration-150 ${activeClasses}`}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </div>

      <div className="border-t border-[color:var(--color-sidebar-border)] px-5 py-4 text-[11px] text-[color:var(--color-muted-foreground)] opacity-70">
        © {new Date().getFullYear()} Штаб
      </div>
    </nav>
  );
}
