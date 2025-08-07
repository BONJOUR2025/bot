import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Menu, X } from 'lucide-react';

const navItems = [
  { to: '/admin', label: 'Дашборд' },
  { to: '/admin/employees', label: 'Сотрудники' },
  { to: '/admin/vacations', label: 'Отпуска' },
  { to: '/admin/assets', label: 'Имущество' },
  { to: '/admin/broadcast', label: 'Рассылка' },
  { to: '/admin/analytics', label: 'Аналитика' },
  { to: '/admin/incentives', label: 'Штрафы/Премии' },
  { to: '/admin/payouts', label: 'Выплаты' },
  { to: '/admin/payouts-control', label: 'Контроль' },
  { to: '/admin/birthdays', label: 'Дни рождения' },
  { to: '/admin/dictionary', label: 'Словарь' },
  { to: '/admin/settings', label: 'Настройки' },
];

export default function Navigation() {
  const [open, setOpen] = useState(false);
  const toggle = () => setOpen((o) => !o);
  const close = () => setOpen(false);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={toggle}
        className="sm:hidden p-2 mb-2 bg-brand text-white rounded shadow-lg"
      >
        {open ? <X size={20} /> : <Menu size={20} />}
      </button>
      {open && (
        <div className="fixed inset-0 bg-black/50 sm:hidden" onClick={close} />
      )}
      <nav
        className={`${
          open ? 'flex' : 'hidden'
        } sm:flex flex-wrap items-center gap-4 absolute sm:static top-full left-0 bg-white sm:bg-transparent shadow sm:shadow-none p-4 sm:p-0 w-full`}
      >
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            onClick={close}
            className={({ isActive }) =>
              `px-3 py-2 text-sm font-semibold uppercase border-b-2 ${
                isActive
                  ? 'border-brand text-brand'
                  : 'border-transparent hover:text-brand'
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
