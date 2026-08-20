import { useMemo } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  X, PanelLeftClose, PanelLeftOpen,
  LayoutDashboard, Users, UserPlus, Archive, CalendarRange,
  Umbrella, Cake, Package, Calculator, MapPin, Banknote,
  ShieldCheck, Award, ArrowLeftRight, CalendarDays, MessageSquare,
  BarChart2, Store, Megaphone, History, Settings as SettingsIcon,
  Hammer, TrendingUp, ListTodo, KeyRound, Send, LibraryBig, Truck,
  Clock, Replace, CalendarOff, MessageCircle, Users2, Sun, Moon, Monitor,
  Landmark, UserSearch, UserCog, SlidersHorizontal, Scan, Headphones,
} from 'lucide-react';

import { useAuth } from '../providers/AuthProvider.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';
import { useTheme } from '../providers/ThemeProvider.jsx';

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
      { to: '/admin/clients',          label: 'Клиенты',              permission: 'payroll',          icon: UserSearch },
      { to: '/admin/location-plans',   label: 'Планы продаж',         permission: 'payroll',          icon: MapPin },
      { to: '/admin/sale-transfers',   label: 'Перемещение продажи',  permission: 'payroll',          icon: Replace },
      { to: '/admin/scanner-3d',       label: '3D сканер',            permission: '3d-scanner',       icon: Scan },
      { to: '/admin/salon-audio',      label: 'Прослушивание',        permission: 'salon-audio',      icon: Headphones },
    ],
  },
  {
    name: 'Зарплата',
    items: [
      { to: '/admin/payroll-summary',  label: 'Сводный отчёт',        permission: 'payroll',         icon: BarChart2 },
      { to: '/admin/payroll',          label: 'Администраторы',        permission: 'payroll',         icon: Calculator },
      { to: '/admin/payroll-by-salon', label: 'ФОТ по салонам',       permission: 'payroll',         icon: Store },
      { to: '/admin/masters',          label: 'Мастера',              permission: 'payroll',         icon: Hammer },
      { to: '/admin/manager-salary',   label: 'Менеджеры',            permission: 'manager-salary',  icon: Users },
      { to: '/admin/courier-salary',   label: 'Курьер',               permission: 'payroll',         icon: Truck },
    ],
  },
  {
    name: 'Деньги',
    items: [
      { to: '/admin/payouts',          label: 'Выплаты',              permission: 'payouts',         icon: Banknote },
      { to: '/admin/payouts-control',  label: 'Контроль выплат',      permission: 'payouts-control', icon: ShieldCheck },
      { to: '/admin/incentives',       label: 'Штрафы и премии',      permission: 'incentives',      icon: Award },
      { to: '/admin/cash-moves',       label: 'Кассовые перемещения', permission: 'cash-moves',      icon: ArrowLeftRight },
      { to: '/admin/cash-summary',     label: 'Сводный отчёт (касса)', permission: 'cash-moves',     icon: BarChart2 },
      { to: '/admin/receivables',      label: 'Дебиторка',            permission: 'payroll',         icon: Landmark },
      { to: '/admin/payment-calendar', label: 'Платежный календарь',  permission: 'payment-calendar',icon: CalendarDays },
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
      { to: '/admin/agbis-users',    label: 'Пользователи АГБИС', permission: 'payroll', icon: UserCog },
      { to: '/admin/agbis-settings', label: 'Настройки АГБИС',   permission: 'payroll', icon: SlidersHorizontal },
      { to: '/admin/passwords',      label: 'Пароли',      permission: 'passwords', icon: KeyRound },
      { to: '/admin/settings',       label: 'Настройки',   permission: 'settings',  icon: SettingsIcon },
    ],
  },
];

const THEME_MODES = [
  { key: 'light', icon: Sun,     label: 'Светлая тема' },
  { key: 'dark',  icon: Moon,    label: 'Тёмная тема' },
  { key: 'auto',  icon: Monitor, label: 'Тема по системе' },
];

export default function Navigation({ onNavigate, collapsed, onToggleCollapse }) {
  const location = useLocation();
  const { user } = useAuth();
  const { isMobile } = useViewport();
  const { mode, setMode } = useTheme();
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
              // Prefix match lets a parent route (e.g. "/admin/settings")
              // stay highlighted on its sub-pages, but "/admin" itself is
              // the dashboard's own exact route, not a parent of every
              // other page — without this exclusion its prefix matched
              // literally everything (every route starts with "/admin/"),
              // so Дашборд stayed lit up alongside whatever page you were
              // actually on.
              active:
                location.pathname === item.to ||
                (item.to !== '/admin' && location.pathname.startsWith(`${item.to}/`)),
            })),
        }))
        .filter((category) => category.items.length > 0),
    [location.pathname, allowed],
  );

  const isCollapsed = !isMobile && collapsed;

  return (
    // Семантические классы вместо набора Tailwind-утилит. Правила для них
    // уже лежали в globals.css (включая ветку для брутализма), но были
    // мёртвыми: разметка их не использовала, и каждая тема не могла
    // повлиять на вид навигации иначе как переопределением токенов.
    // Панель, фон и скругление даёт .app-shell__sidebar > * — поэтому
    // здесь ни фона, ни рамки, ни ширины: ширину задаёт грид шелла.
    <nav className={`sidebar ${isCollapsed ? 'sidebar--collapsed' : ''}`}>
      {/* Шапка. На мобильном фон строки уходит под вырез экрана
          намеренно, но сам логотип и кнопка закрытия обязаны его
          миновать — та же логика, что и в .app-shell__header. */}
      <div
        className="sidebar__header"
        style={isMobile ? { paddingTop: 'calc(0.5rem + env(safe-area-inset-top, 0px))' } : undefined}
      >
        <div className="sidebar__badge">ЦУ</div>
        {!isCollapsed && (
          <div className="sidebar__title">
            <span className="sidebar__title-main">Центр управления</span>
            <span className="sidebar__title-sub">Панель администратора</span>
          </div>
        )}
        {isMobile && (
          <button
            type="button"
            className="sidebar__icon-btn ml-auto"
            onClick={() => typeof onNavigate === 'function' && onNavigate()}
            aria-label="Закрыть меню"
          >
            <X size={18} strokeWidth={1.4} />
          </button>
        )}
        {!isMobile && !isCollapsed && (
          <button
            type="button"
            onClick={onToggleCollapse}
            title="Свернуть меню"
            aria-label="Свернуть меню"
            className="sidebar__icon-btn ml-auto"
          >
            <PanelLeftClose size={16} strokeWidth={1.4} />
          </button>
        )}
      </div>

      <div className="sidebar__sections">
        {itemsByCategory.map((category) => (
          <div key={category.name} className="sidebar__section">
            {!isCollapsed && <div className="sidebar__section-label">{category.name}</div>}
            {isCollapsed && <div className="sidebar__divider" />}
            <div className="sidebar__links">
              {category.items.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    onClick={handleNavigate}
                    title={isCollapsed ? item.label : undefined}
                    aria-current={item.active ? 'page' : undefined}
                    className={`sidebar__link ${item.active ? 'is-active' : ''} ${
                      isCollapsed ? 'sidebar__link--icon' : ''
                    }`}
                  >
                    {Icon && <Icon size={16} strokeWidth={1.4} className="shrink-0" />}
                    {!isCollapsed && <span>{item.label}</span>}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Переключатель темы: показаны все три режима сразу, активный
          подсвечен — вместо одной кнопки, подписанной скрытым следующим
          состоянием. */}
      <div className="sidebar__footer">
        <div className={`sidebar__theme ${isCollapsed ? 'sidebar__theme--stacked' : ''}`}>
          {THEME_MODES.map(({ key, icon: Icon, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => setMode(key)}
              title={label}
              aria-label={label}
              aria-pressed={mode === key}
              className={`sidebar__theme-btn ${mode === key ? 'is-active' : ''}`}
            >
              <Icon size={15} strokeWidth={1.4} />
            </button>
          ))}
        </div>

        {isCollapsed && (
          <button
            type="button"
            onClick={onToggleCollapse}
            title="Развернуть меню"
            aria-label="Развернуть меню"
            className="sidebar__icon-btn mx-auto mt-2"
          >
            <PanelLeftOpen size={16} strokeWidth={1.4} />
          </button>
        )}
      </div>
    </nav>
  );
}
