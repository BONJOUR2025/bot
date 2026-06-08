import { NavLink, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import {
  SlidersHorizontal, Send, Sparkles, FileText, BookOpen,
} from 'lucide-react';

import SettingsGeneral from './settings/General.jsx';
import SettingsTelegram from './settings/Telegram.jsx';
import SettingsAutomation from './settings/Automation.jsx';
import SettingsTemplates from './settings/Templates.jsx';
import SettingsDictionary from './settings/DictionarySettings.jsx';

const TABS = [
  { to: 'general',    label: 'Общие',         icon: SlidersHorizontal },
  { to: 'telegram',   label: 'Telegram',      icon: Send },
  { to: 'automation', label: 'Автоматизация', icon: Sparkles },
  { to: 'templates',  label: 'Шаблоны',       icon: FileText },
  { to: 'dictionary', label: 'Словарь',       icon: BookOpen },
];

function SettingsLayout() {
  return (
    <div className="space-y-5">
      <h2 className="text-2xl font-semibold tracking-tight">Настройки</h2>

      <nav className="flex flex-wrap gap-1.5 border-b border-[color:var(--color-border)] pb-3">
        {TABS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[color:var(--color-primary)] text-white'
                  : 'text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-bg-secondary)]'
              }`
            }
          >
            <Icon size={15} />
            {label}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </div>
  );
}

export default function Settings() {
  return (
    <Routes>
      <Route element={<SettingsLayout />}>
        <Route index element={<Navigate to="general" replace />} />
        <Route path="general" element={<SettingsGeneral />} />
        <Route path="telegram" element={<SettingsTelegram />} />
        <Route path="automation" element={<SettingsAutomation />} />
        <Route path="templates" element={<SettingsTemplates />} />
        <Route path="dictionary" element={<SettingsDictionary />} />
        <Route path="*" element={<Navigate to="general" replace />} />
      </Route>
    </Routes>
  );
}
