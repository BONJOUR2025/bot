import { useMemo } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  X, PanelLeftClose, PanelLeftOpen,
  LayoutDashboard, Users, UserPlus, Archive, CalendarRange,
  Umbrella, Cake, Package, Calculator, MapPin, Banknote,
  ShieldCheck, Award, ArrowLeftRight, CalendarDays, MessageSquare,
  BarChart2, Store, Megaphone, History, Settings as SettingsIcon,
  Hammer, TrendingUp, ListTodo, KeyRound, FileText, Send, LibraryBig,
  Clock, Replace, CalendarOff, MessageCircle, Users2,
} from 'lucide-react';

import { useAuth } from '../providers/AuthProvider.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';

const navStructure = [
  {
    name: 'Обзор',
    items: [{ to: '/admin', label: 'Дашборд', permission: 'dashboard', icon: LayoutDashboard }],
  },
  {
    name: 'Сотрудники',
    items: [
      { to: '/admin/employees',   label: 'Сотрудники',        permission: 'employees', icon: Users },
      { to: '/admin/recruitment', label: 'Подбор персонала',  permission: 'employees', icon: UserPlus },
      { to: '/admin/archive',     label: 'Архив',             permission: 'employees', icon: Archive },
      { to: '/admin/birthdays',   label: 'Дни рождения',      permission: 'birthdays', icon: Cake },
      { to: '/admin/assets',      label: 'Имущество',         permission: 'assets',    icon: Package },
    ],
  },
  {
    name: 'Учёт времени и отсутствий',
    items: [
      { to: '/admin/schedule',       label: 'Расписание',       permission: 'employees',      icon: CalendarRange },
      { to: '/admin/vacations',      label: 'Отпуска',          permission: 'vacations',      icon: Umbrella },
      { to: '/admin/leave-requests', label: 'Заявки на отгул',  permission: 'leave-requests', icon: CalendarOff },
      { to: '/admin/shift-checkins', label: 'Рабочее время',    permission: 'shift-checkins', icon: Clock },
    ],
  },
  {
    name: 'Точки и продажи',
    items: [
      { to: '/admin/salons',           label: 'Салоны',               permission: 'salons',           icon: Store },
      { to: '/admin/visitor-counters', label: 'Счётчик посетителей',  permission: 'visitor-counters', icon: Users2 },
      { to: '/admin/sales',            label: 'Продажи',              permission: 'payroll',          icon: TrendingUp },
      { to: '/admin/masters',          label: 'Работы мастеров',      permission: 'payroll',          icon: Hammer },
      { to: '/admin/location-plans',   label: 'Планы по точкам',      permission: 'payroll',          icon: MapPin },
      { to: '/admin/sale-transfers',   label: 'Перемещение продажи',  permission: 'payroll',          icon: Replace },
    ],
  },
  {
    name: 'Деньги',
    items: [
      { to: '/admin/payroll',          label: 'Расчёт зарплаты',      permission: 'payroll',         icon: Calculator },
      { to: '/admin/payouts',          label: 'Выплаты',              permission: 'payouts',         icon: Banknote },
      { to: '/admin/payouts-control',  label: 'Контроль выплат',      permission: 'payouts-control', icon: ShieldCheck },
      { to: '/admin/incentives',       label: 'Штрафы и премии',      permission: 'incentives',      icon: Award },
      { to: '/admin/cash-moves',       label: 'Кассовые перемещения', permission: 'cash-moves',      icon: ArrowLeftRight },
      { to: '/admin/payment-calendar', label: 'Платежный календарь',  permission: 'payment-calendar',icon: CalendarDays },
      { to: '/admin/reports',          label: 'Отчёты',               permission: 'reports',         icon: BarChart2 },
    ],
  },
  {
    name: 'Коммуникации',
    items: [
      { to: '/admin/tasks',     label: 'Задачи',            permission: 'tasks',     icon: ListTodo },
      { to: '/admin/broadcast', label: 'Рассылка',          permission: 'broadcast', icon: Megaphone },
      { to: '/admin/messages',  label: 'История сообщений', permission: 'messages',  icon: History },
      { to: '/admin/employee-messages', label: 'Сообщения от сотрудников', permission: 'employee-messages', icon: MessageCircle },
      { to: '/admin/smses',     label: 'СМС Агбис',         permission: 'smses',     icon: MessageSquare },
    ],
  },
  {
    name: 'Справочники и система',
    items: [
      { to: '/admin/knowledge-base', label: 'База знаний', permission: 'employees', icon: LibraryBig },
      { to: '/admin/passwords',      label: 'Пароли',      permission: 'passwords', icon: KeyRound },
      { to: '/admin/settings',       label: 'Настройки',   permission: 'settings',  icon: SettingsIcon },
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
    <nav className={`flex h-full min-h-screen flex-col bg-[color:var(--color-sidebar)] text-[color:var(--color-sidebar-foreground)] shadow-xl transition-all duration-200 ${isMobile ? 'w-full' : isCollapsed ? 'w-[64px]' : 'w-[280px]'}`}>

      {/* Logo */}
      <div className={`flex pb-5 pt-7 ${isCollapsed ? 'flex-col items-center gap-2 px-0' : 'items-center gap-4 px-6'}`}>
        <div className="grid h-11 w-11 flex-shrink-0 place-items-center rounded-xl bg-[color:var(--color-sidebar-primary)] text-[color:var(--color-sidebar-primary-foreground)] shadow-[0_10px_30px_rgba(0,0,0,0.12)] text-sm font-bold">
          ЦУ
        </div>
        {!isCollapsed && (
          <div className="flex flex-col text-sm min-w-0">
            <span className="text-base font-semibold leading-tight">Центр управления</span>
            <span className="text-[13px] text-[color:var(--color-muted-foreground)]">Панель администратора</span>
          </div>
        )}
        {isMobile && (
          <button
            type="button"
            className="ml-auto inline-flex h-9 w-9 items-center justify-center rounded-full border border-[color:var(--color-sidebar-border)] bg-transparent transition hover:bg-[color:var(--color-sidebar-accent)]"
            onClick={() => typeof onNavigate === 'function' && onNavigate()}
          >
            <X size={18} />
          </button>
        )}
        {!isMobile && (
          <button
            type="button"
            onClick={onToggleCollapse}
            title={isCollapsed ? 'Развернуть меню' : 'Свернуть меню'}
            className={`flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-lg text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-sidebar-accent)] hover:text-[color:var(--color-sidebar-accent-foreground)] transition-colors ${isCollapsed ? '' : 'ml-auto'}`}
          >
            {isCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        )}
      </div>

      {/* Nav items */}
      <div className={`flex-1 space-y-6 overflow-y-auto pb-4 ${isCollapsed ? 'px-2' : 'px-6'}`}>
        {itemsByCategory.map((category) => (
          <div key={category.name} className="space-y-1">
            {!isCollapsed && (
              <div className="text-xs font-medium uppercase tracking-[0.12em] text-[color:var(--color-muted-foreground)] mb-2">
                {category.name}
              </div>
            )}
            {isCollapsed && <div className="h-px bg-[color:var(--color-sidebar-border)] mb-2" />}
            <div className="space-y-0.5">
              {category.items.map((item) => {
                const Icon = item.icon;
                const activeClasses = item.active
                  ? 'bg-[color:var(--color-sidebar-primary)] text-[color:var(--color-sidebar-primary-foreground)] shadow-[0_4px_12px_rgba(0,0,0,0.15)]'
                  : 'text-[color:var(--color-sidebar-foreground)] opacity-70 hover:bg-[color:var(--color-sidebar-accent)] hover:opacity-100';

                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    onClick={handleNavigate}
                    title={isCollapsed ? item.label : undefined}
                    className={`flex items-center rounded-xl border border-transparent transition-all duration-150 ${
                      isCollapsed ? 'justify-center h-10 w-10 mx-auto' : 'gap-3 px-4 py-2'
                    } ${activeClasses}`}
                  >
                    {Icon && <Icon size={isCollapsed ? 18 : 16} className="flex-shrink-0" />}
                    {!isCollapsed && <span className="text-sm font-medium">{item.label}</span>}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Collapse toggle (desktop only) */}
      {!isMobile && (
        <div className={`border-t border-[color:var(--color-sidebar-border)] py-3 ${isCollapsed ? 'flex justify-center' : 'px-6 flex justify-between items-center'}`}>
          {!isCollapsed && (
            <span className="text-xs text-[color:var(--color-muted-foreground)] opacity-70">
              © {new Date().getFullYear()} Центр управления
            </span>
          )}
          <button
            type="button"
            onClick={onToggleCollapse}
            title={isCollapsed ? 'Развернуть меню' : 'Свернуть меню'}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-sidebar-accent)] hover:text-[color:var(--color-sidebar-accent-foreground)] transition-colors"
          >
            {isCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        </div>
      )}

      {/* Mobile footer */}
      {isMobile && (
        <div className="border-t border-[color:var(--color-sidebar-border)] px-6 py-5 text-xs text-[color:var(--color-muted-foreground)] opacity-90">
          © {new Date().getFullYear()} Центр управления
        </div>
      )}
    </nav>
  );
}
