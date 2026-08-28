import { NavLink, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import {
  SlidersHorizontal, Send, Sparkles, FileText, BookOpen, Lock, Stethoscope, Plug, Coins, Shield, Scissors,
} from 'lucide-react';

import SettingsGeneral from './settings/General.jsx';
import SettingsTelegram from './settings/Telegram.jsx';
import SettingsAutomation from './settings/Automation.jsx';
import SettingsAiUsage from './settings/AiUsage.jsx';
import SettingsTemplates from './settings/Templates.jsx';
import SettingsDictionary from './settings/DictionarySettings.jsx';
import SettingsAccessControl from './settings/AccessControl.jsx';
import SettingsDiagnostics from './settings/Diagnostics.jsx';
import SettingsIntegrations from './settings/Integrations.jsx';
import SettingsVpn from './settings/Vpn.jsx';
import SettingsPoshivBot from './settings/PoshivBot.jsx';

const TABS = [
  { to: '/admin/settings/general',     label: 'Общие',         icon: SlidersHorizontal },
  { to: '/admin/settings/telegram',    label: 'Telegram',      icon: Send },
  { to: '/admin/settings/automation',  label: 'Автоматизация', icon: Sparkles },
  { to: '/admin/settings/ai-usage',    label: 'Расход AI',     icon: Coins },
  { to: '/admin/settings/integrations', label: 'Интеграции',   icon: Plug },
  { to: '/admin/settings/vpn',         label: 'VPN',           icon: Shield },
  { to: '/admin/settings/poshiv-bot',  label: 'Бот пошива',    icon: Scissors },
  { to: '/admin/settings/templates',   label: 'Шаблоны',       icon: FileText },
  { to: '/admin/settings/dictionary',  label: 'Словарь',       icon: BookOpen },
  { to: '/admin/settings/access',      label: 'Доступ',        icon: Lock },
  { to: '/admin/settings/diagnostics', label: 'Диагностика',   icon: Stethoscope },
];

function SettingsLayout() {
  return (
    <div className="space-y-5">
      <div>
        <span className="ui-eyebrow mb-3">Изменения применяются сразу</span>
        <h2 className="text-2xl font-semibold tracking-tight">Настройки</h2>
      </div>

      <nav className="flex flex-wrap gap-1.5 border-b border-[color:var(--color-border)] pb-3">
        {TABS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end
            className={({ isActive }) =>
              `ui-tabnav__btn flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
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
        <Route index element={<Navigate to="/admin/settings/general" replace />} />
        <Route path="general" element={<SettingsGeneral />} />
        <Route path="telegram" element={<SettingsTelegram />} />
        <Route path="automation" element={<SettingsAutomation />} />
        <Route path="ai-usage" element={<SettingsAiUsage />} />
        <Route path="integrations" element={<SettingsIntegrations />} />
        <Route path="vpn" element={<SettingsVpn />} />
        <Route path="poshiv-bot" element={<SettingsPoshivBot />} />
        <Route path="templates" element={<SettingsTemplates />} />
        <Route path="dictionary" element={<SettingsDictionary />} />
        <Route path="access" element={<SettingsAccessControl />} />
        <Route path="diagnostics" element={<SettingsDiagnostics />} />
        <Route path="*" element={<Navigate to="/admin/settings/general" replace />} />
      </Route>
    </Routes>
  );
}
