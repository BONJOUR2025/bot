import { useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Menu, X } from 'lucide-react';

const navStructure = [
  {
    name: 'Обзор',
    items: [{ to: '/admin', label: 'Дашборд' }],
  },
  {
    name: 'Персонал',
    items: [
      { to: '/admin/employees', label: 'Сотрудники' },
      { to: '/admin/vacations', label: 'Отпуска' },
      { to: '/admin/birthdays', label: 'Дни рождения' },
      { to: '/admin/assets', label: 'Имущество' },
    ],
  },
  {
    name: 'Финансы',
    items: [
      { to: '/admin/payouts', label: 'Выплаты' },
      { to: '/admin/payouts-control', label: 'Контроль выплат' },
      { to: '/admin/incentives', label: 'Штрафы и премии' },
      { to: '/admin/reports', label: 'Отчёты' },
    ],
  },
  {
    name: 'Управление',
    items: [
      { to: '/admin/broadcast', label: 'Рассылка' },
      { to: '/admin/messages', label: 'История сообщений' },
      { to: '/admin/dictionary', label: 'Словарь' },
      { to: '/admin/settings', label: 'Настройки' },
    ],
  },
];

export default function Navigation() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const toggle = () => setOpen((o) => !o);
  const close = () => setOpen(false);

  const itemsByCategory = useMemo(
    () =>
      navStructure.map((category) => ({
        ...category,
        items: category.items.map((item) => ({
          ...item,
          active:
            location.pathname === item.to || location.pathname.startsWith(`${item.to}/`),
        })),
      })),
    [location.pathname],
  );

  return (
    <div className="relative mb-4">
      <button
        type="button"
        onClick={toggle}
        className="sm:hidden p-2 mb-2 bg-brand text-white rounded shadow-lg"
      >
        {open ? <X size={20} /> : <Menu size={20} />}
      </button>

      {open && (
        <div
          className="fixed inset-0 bg-black/50 sm:hidden"
          onClick={close}
        />
      )}

      <nav
        className={`${
          open ? 'translate-x-0' : '-translate-x-full'
        } sm:translate-x-0 transition-transform fixed sm:static top-0 left-0 h-full sm:h-auto w-64 bg-white/90 backdrop-blur-lg p-4 rounded sm:rounded-none shadow-lg sm:shadow-none overflow-y-auto`}
      >
        <div className="space-y-6">
          {itemsByCategory.map((category) => (
            <div key={category.name}>
              <div className="px-3 text-xs font-semibold uppercase tracking-wide text-gray-400">
                {category.name}
              </div>
              <div className="mt-2 space-y-1">
                {category.items.map((item) => (
                  <Link
                    key={item.to}
                    to={item.to}
                    onClick={close}
                    className={`block rounded px-3 py-2 text-sm transition-colors ${
                      item.active
                        ? 'bg-brand/10 text-brand font-semibold'
                        : 'text-gray-700 hover:bg-muted/20'
                    }`}
                  >
                    {item.label}
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      </nav>
    </div>
  );
}




