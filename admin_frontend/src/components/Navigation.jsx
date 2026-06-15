import { useMemo } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  X, PanelLeftClose, PanelLeftOpen,
  LayoutDashboard, Users, Archive, CalendarRange,
  Umbrella, Cake, Package, Store,
  Calculator, MapPin, Hammer, Banknote,
  ShieldCheck, Award, ArrowLeftRight, CalendarDays,
  TrendingUp, BarChart2,
  ListTodo, Megaphone, History,
  BookOpen, KeyRound, Lock, Settings as SettingsIcon,
  Clock,
} from 'lucide-react';

import { useAuth } from '../providers/AuthProvider.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';

const navStructure = [
  {
    name: 'Обзор',
    items: [
      { to: '/admin', label: 'Дашборд', permission: 'dashboard', icon: LayoutDashboard },
    ],
  },
  {
    name: 'Персонал',
    items: [
      { to: '/admin/employees',  label: 'Сотрудники',   permission: 'employees', icon: Users },
      { to: '/admin/archive',    label: 'Архив',         permission: 'employees', icon: Archive },
      { to: '/admin/schedule',   label: 'Расписание',    permission: 'employees', icon: CalendarRange },
      { to: '/admin/vacations',  label: 'Отпуска',       permission: 'vacations', icon: Umbrella },
      { to: '/admin/birthdays',  label: 'Дни рождения',  permission: 'birthdays', icon: Cake },
      { to: '/admin/assets',     label: 'Имущество',     permission: 'assets',    icon: Package },
      { to: '/admin/salons',     label: 'Салоны',        permission: 'salons',    icon: Store },
      { to: '/admin/shift-checkins', label: 'Рабочее время', permission: 'shift-checkins', icon: Clock },
    ],
  },
  {
    name: 'Финансы',
    items: [
      { to: '/admin/payroll',           label: 'Расчёт зарплаты',      permission: 'payroll',          icon: Calculator },
      { to: '/admin/location-plans',    label: 'Планы по точкам',      permission: 'payroll',          icon: MapPin },
      { to: '/admin/masters',           label: 'Работы мастеров',      permission: 'payroll',          icon: Hammer },
      { to: '/admin/payouts',           label: 'Выплаты',              permission: 'payouts',          icon: Banknote },
      { to: '/admin/payouts-control',   label: 'Контроль выплат',      permission: 'payouts-control',  icon: ShieldCheck },
      { to: '/admin/incentives',        label: 'Штрафы и премии',      permission: 'incentives',       icon: Award },
      { to: '/admin/cash-moves',        label: 'Кассовые перемещения', permission: 'cash-moves',       icon: ArrowLeftRight },
      { to: '/admin/payment-calendar',  label: 'Платежный календарь',  permission: 'payment-calendar', icon: CalendarDays },
    ],
  },
  {
    name: 'Аналитика',
    items: [
      { to: '/admin/sales',   label: 'Продажи',  permission: 'payroll',  icon: TrendingUp },
      { to: '/admin/reports', label: 'Отчёты',   permission: 'reports',  icon: BarChart2 },
    ],
  },
  {
    name: 'Операции',
    items: [
      { to: '/admin/tasks',     label: 'Задачи',             permission: 'tasks',     icon: ListTodo },
      { to: '/admin/broadcast', label: 'Рассылка',           permission: 'broadcast', icon: Megaphone },
      { to: '/admin/messages',  label: 'История сообщений',  permission: 'messages',  icon: History },
    ],
  },
  {
    name: 'Система',
    items: [
      { to: '/admin/dictionary', label: 'Словарь',   permission: 'dictionary', icon: BookOpen },
      { to: '/admin/passwords',  label: 'Пароли',    permission: 'passwords',  icon: KeyRound },
      { to: '/admin/access',     label: 'Доступ',    permission: 'access',     icon: Lock },
      { to: '/admin/settings',   label: 'Настройки', permission: 'settings',   icon: SettingsIcon },
    ],
  },
];

export default function Navigation({ onNavigate, collapsed, onToggleCollapse }) {
  const location = useLocation();
  const { user } = useAuth();
  const { isMobile } = useViewport();
  const allowed = useMemo(() => new Set(user?.permissions || []), [user?.permissions]);

  const handleNavigate = () => {
    if (isMobile && typeof onNavigate === 'function') onNavigate();
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
                location.pathname === item.to ||
                location.pathname.startsWith(`${item.to}/`),
            })),
        }))
        .filter((category) => category.items.length > 0),
    [location.pathname, allowed],
  );

  const isCollapsed = !isMobile && collapsed;

  return (
    <nav className={`flex h-full min-h-screen flex-col bg-[color:var(--color-sidebar)] text-[color:var(--color-sidebar-foreground)] shadow-xl transition-[width] duration-200 overflow-hidden ${
      isMobile ? 'w-full' : isCollapsed ? 'w-[64px]' : 'w-[280px]'
    }`}>

      {/* Header */}
      <div className={`flex items-center gap-3 pb-4 pt-6 shrink-0 ${isCollapsed ? 'justify-center px-0' : 'px-5'}`}>
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[color:var(--color-sidebar-primary)] text-[color:var(--color-sidebar-primary-foreground)] text-xs font-bold shadow">
          ЦУ
        </div>
        {!isCollapsed && (
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold leading-tight truncate">Центр управления</div>
            <div className="text-[11px] text-[color:var(--color-muted-foreground)] truncate">Панель администратора</div>
          </div>
        )}
        {isMobile && (
          <button
            type="button"
            className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[color:var(--color-sidebar-border)] text-[color:var(--color-sidebar-foreground)] hover:bg-[color:var(--color-sidebar-accent)] transition"
            onClick={onNavigate}
            aria-label="Закрыть меню"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Nav items */}
      <div className={`flex-1 space-y-5 overflow-y-auto pb-4 ${isCollapsed ? 'px-2' : 'px-4'}`}>
        {itemsByCategory.map((category) => (
          <div key={category.name} className="space-y-0.5">
            {!isCollapsed ? (
              <div className="px-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--color-muted-foreground)] mb-1">
                {category.name}
              </div>
            ) : (
              <div className="h-px bg-[color:var(--color-sidebar-border)] mb-2" />
            )}
            {category.items.map((item) => {
              const Icon = item.icon;
              const activeClasses = item.active
                ? 'bg-[color:var(--color-sidebar-primary)] text-[color:var(--color-sidebar-primary-foreground)] shadow-sm'
                : 'text-[color:var(--color-sidebar-foreground)] opacity-70 hover:bg-[color:var(--color-sidebar-accent)] hover:text-[color:var(--color-sidebar-accent-foreground)] hover:opacity-100';

              return (
                <Link
                  key={item.to}
                  to={item.to}
                  onClick={handleNavigate}
                  title={isCollapsed ? item.label : undefined}
                  className={`flex items-center rounded-lg transition-all duration-150 ${
                    isCollapsed
                      ? 'justify-center h-9 w-9 mx-auto'
                      : 'gap-3 px-3 py-2'
                  } ${activeClasses}`}
                >
                  {Icon && <Icon size={isCollapsed ? 18 : 16} className="shrink-0" />}
                  {!isCollapsed && <span className="text-sm font-medium">{item.label}</span>}
                </Link>
              );
            })}
          </div>
        ))}
      </div>

      {/* Footer: collapse toggle (desktop) / copyright (mobile) */}
      {!isMobile ? (
        <div className={`border-t border-[color:var(--color-sidebar-border)] py-3 shrink-0 ${
          isCollapsed ? 'flex justify-center' : 'px-5 flex justify-between items-center'
        }`}>
          {!isCollapsed && (
            <span className="text-xs text-[color:var(--color-muted-foreground)] opacity-70">
              © {new Date().getFullYear()} Центр управления
            </span>
          )}
          <button
            type="button"
            onClick={onToggleCollapse}
            title={isCollapsed ? 'Развернуть меню' : 'Свернуть меню'}
            className="h-8 w-8 flex items-center justify-center rounded-lg text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-sidebar-accent)] hover:text-[color:var(--color-sidebar-accent-foreground)] transition-colors"
          >
            {isCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        </div>
      ) : (
        <div className="border-t border-[color:var(--color-sidebar-border)] px-5 py-4 text-[11px] text-[color:var(--color-muted-foreground)] opacity-70 shrink-0">
          © {new Date().getFullYear()} Центр управления
        </div>
      )}
    </nav>
  );
}
