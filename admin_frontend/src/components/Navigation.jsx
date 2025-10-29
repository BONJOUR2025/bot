import { useState } from 'react';
import { Link } from 'react-router-dom';
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
    ],
  },
  {
    name: 'Аналитика',
    items: [
      { to: '/admin/reports', label: 'Отчёты' },
      { to: '/admin/analytics', label: 'Аналитика' },
      { to: '/admin/analytics-details', label: 'Подробная аналитика' },
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
  const [open, setOpen] = useState(false);
  const toggle = () => setOpen((o) => !o);
  const close = () => setOpen(false);

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
        } sm:translate-x-0 transition-transform sm:flex flex-wrap gap-2 fixed sm:static top-0 left-0 h-full sm:h-auto w-64 sm:w-auto bg-white/80 backdrop-blur-lg p-4 rounded sm:rounded-none shadow-lg`}
      >
        {navStructure.map((cat) => (
          <div key={cat.name} className="relative group">
            <button
              type="button"
              className="px-3 py-2 rounded flex items-center text-gray-700 hover:bg-muted/20 transition-colors"
            >
              {cat.name}
            </button>
            <div className="absolute z-10 hidden group-hover:block bg-white/90 backdrop-blur border rounded shadow mt-1">
              {cat.items.map((item) => (
                <Link
                  key={item.to}
                  className="block px-3 py-2 whitespace-nowrap hover:bg-muted/20"
                  to={item.to}
                  onClick={close}
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </nav>
    </div>
  );
}




