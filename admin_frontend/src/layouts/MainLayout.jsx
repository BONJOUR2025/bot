import { useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Menu, LogOut } from 'lucide-react';

import Navigation from '../components/Navigation.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';
import { useAuth } from '../providers/AuthProvider.jsx';

const PAGE_META = {
  '/admin': {
    title: 'Дашборд',
    subtitle: 'Общее состояние HR-направления: команда, загрузка, финансы и события в одном окне.',
    wrap: false,
  },
  '/admin/employees': {
    title: 'Сотрудники',
    subtitle: 'Живой реестр команды с карточками, фильтрами и быстрыми действиями.',
  },
  '/admin/archive': {
    title: 'Архив сотрудников',
    subtitle: 'История и карточки бывших сотрудников в аккуратном архиве.',
  },
  '/admin/payouts': {
    title: 'Выплаты',
    subtitle: 'Статусы и суммы начислений с контролем сроков.',
  },
  '/admin/payouts-control': {
    title: 'Контроль выплат',
    subtitle: 'Мониторинг выплат, замечаний и подтверждений.',
  },
  '/admin/incentives': {
    title: 'Штрафы и премии',
    subtitle: 'Мотивационные начисления и удержания, сгруппированные по сотрудникам.',
  },
  '/admin/reports': {
    title: 'Отчёты',
    subtitle: 'Сводные отчёты по оплатам и графику выплат.',
  },
  '/admin/broadcast': {
    title: 'Рассылка',
    subtitle: 'Распространение сообщений и уведомлений по выбранным каналам.',
  },
  '/admin/messages': {
    title: 'История сообщений',
    subtitle: 'Хронология отправленных уведомлений и статусов доставки.',
  },
  '/admin/vacations': {
    title: 'Отпуска',
    subtitle: 'Планы отпусков и баланс дней отдыха в едином календаре.',
  },
  '/admin/birthdays': {
    title: 'Дни рождения',
    subtitle: 'Поздравления и напоминания о предстоящих праздниках.',
  },
  '/admin/assets': {
    title: 'Имущество',
    subtitle: 'Учёт и движение выданного имущества.',
  },
  '/admin/dictionary': {
    title: 'Словарь',
    subtitle: 'Справочники должностей, локаций и других сущностей.',
  },
  '/admin/settings': {
    title: 'Настройки',
    subtitle: 'Конфигурация платформы, интеграций и прав доступа.',
  },
  '/admin/access': {
    title: 'Доступ',
    subtitle: 'Роли, права и управление аккаунтами администраторов.',
  },
};

export default function MainLayout() {
  const location = useLocation();
  const { isMobile } = useViewport();
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(!isMobile);

  const meta = useMemo(() => {
    const matched = Object.entries(PAGE_META).find(
      ([path]) =>
        location.pathname === path || location.pathname.startsWith(`${path}/`),
    );

    if (matched) return matched[1];

    return {
      title: 'Админ-панель',
      subtitle: 'Управление HR-процессами, коммуникациями и доступами в одном окне.',
    };
  }, [location.pathname]);

  useEffect(() => {
    setSidebarOpen(!isMobile);
  }, [isMobile]);

  const toggleSidebar = () => setSidebarOpen((prev) => !prev);
  const closeSidebar = () => setSidebarOpen(false);

  const handleLogout = async () => {
    try {
      await logout();
    } catch (err) {
      console.error(err);
    }
  };

  const userLabel = user?.name || user?.login || 'Администратор';
  const heroBadge = meta.badge ?? 'HR UI 2.0';
  const wrapContent = meta.wrap !== false;

  return (
    <div className={`app-shell ${isMobile ? 'app-shell--mobile' : ''}`}>
      <aside className={`app-shell__sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <Navigation onNavigate={closeSidebar} />
      </aside>

      {isMobile && sidebarOpen && <div className="app-shell__backdrop" onClick={closeSidebar} />}

      <div className="app-shell__main">
        <header className="app-shell__header">
          {isMobile && (
            <button type="button" className="icon-button" onClick={toggleSidebar} aria-label="Открыть меню">
              <Menu size={20} />
            </button>
          )}
          <div className="app-shell__brand">
            <span className="app-shell__brand-accent" />
            HR Панель управления
          </div>
          <div className="app-shell__user">
            <span className="app-shell__user-name">{userLabel}</span>
            <button type="button" className="icon-button icon-button--ghost" onClick={handleLogout} aria-label="Выйти">
              <LogOut size={18} />
              <span>Выход</span>
            </button>
          </div>
        </header>
        <main className="app-shell__content">
          <div className="page-shell">
            <div className="page-hero">
              <div className="page-hero__meta">
                <span className="pill pill--ghost">{heroBadge}</span>
                <div className="page-hero__titles">
                  <h1>{meta.title}</h1>
                  {meta.subtitle && <p className="page-hero__subtitle">{meta.subtitle}</p>}
                </div>
              </div>
              <div className="page-hero__actions">
                <span className="tag tag--muted">Новый визуал</span>
              </div>
            </div>

            <div className="page-shell__content">
              {wrapContent ? (
                <div className="glass-panel glass-panel--padded page-wrapper">
                  <Outlet />
                </div>
              ) : (
                <Outlet />
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}




