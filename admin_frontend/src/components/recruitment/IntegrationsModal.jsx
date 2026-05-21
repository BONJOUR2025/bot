import { useState, useEffect, useCallback } from 'react';
import {
  X, CheckCircle, AlertCircle, RefreshCw, Link2, Unlink,
  ChevronDown, ExternalLink, Settings, Clock, Zap,
} from 'lucide-react';
import api from '../../api';

// Callback URL shown in instructions so users know what to register in hh.ru
const HH_CALLBACK_URL = `${window.location.origin}/api/recruitment/integrations/hh/callback`;

// ── Instructions copy ──────────────────────────────────────────────
const HH_INSTRUCTIONS = [
  { step: '1', text: 'Зайдите на dev.hh.ru → «Создать приложение»' },
  { step: '2', text: `В поле redirect_uri укажите: ${HH_CALLBACK_URL}` },
  { step: '3', text: 'Получите Client ID и Client Secret вашего приложения' },
  { step: '4', text: 'Введите их ниже и нажмите «Войти через hh.ru»' },
];
const AVITO_INSTRUCTIONS = [
  { step: '1', text: 'Зайдите в кабинет разработчика Авито → «Мои приложения»' },
  { step: '2', text: 'Создайте приложение, получите Client ID и Client Secret' },
  { step: '3', text: 'Вставьте их ниже — токен получим автоматически' },
];

// ── Small helper components ────────────────────────────────────────
function StatusBadge({ isActive, error }) {
  if (error) return (
    <span className="flex items-center gap-1 text-xs text-red-600 font-medium">
      <AlertCircle size={13} /> Ошибка
    </span>
  );
  if (isActive) return (
    <span className="flex items-center gap-1 text-xs text-emerald-600 font-medium">
      <CheckCircle size={13} /> Подключено
    </span>
  );
  return <span className="text-xs text-[color:var(--color-muted-foreground)]">Не подключено</span>;
}

function Instructions({ steps }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50 overflow-hidden text-sm">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-blue-700 font-medium text-left"
      >
        <span className="flex-1">Как получить доступ?</span>
        <ChevronDown size={15} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <ol className="px-4 pb-3 space-y-1.5 border-t border-blue-200 pt-2.5">
          {steps.map(s => (
            <li key={s.step} className="flex gap-2 text-blue-800">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-200 text-blue-700 text-[11px] font-bold flex items-center justify-center">{s.step}</span>
              <span>{s.text}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ── Vacancy linker row ─────────────────────────────────────────────
function VacancyLinkRow({ internalVacancy, source, externalVacancies, existingLink, onLink, onUnlink }) {
  const [selected, setSelected] = useState(existingLink?.external_vacancy_id || '');
  const [saving, setSaving] = useState(false);

  async function handleLink() {
    if (!selected) return;
    setSaving(true);
    try {
      const ext = externalVacancies.find(v => v.id === selected);
      await onLink(internalVacancy.id, source, selected, ext?.title || '');
    } finally { setSaving(false); }
  }

  async function handleUnlink() {
    if (!existingLink) return;
    setSaving(true);
    try { await onUnlink(existingLink.id); }
    finally { setSaving(false); }
  }

  const hasLink = !!existingLink;

  return (
    <div className={`rounded-xl border p-3 space-y-2 ${hasLink ? 'border-emerald-200 bg-emerald-50/50' : 'border-[color:var(--color-border)] bg-white'}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">{internalVacancy.title}</p>
          {hasLink && (
            <p className="text-xs text-emerald-700 mt-0.5 truncate">
              → {existingLink.external_vacancy_title || existingLink.external_vacancy_id}
            </p>
          )}
        </div>
        {hasLink ? (
          <button
            onClick={handleUnlink}
            disabled={saving}
            className="flex-shrink-0 flex items-center gap-1 text-xs text-red-500 hover:text-red-700 font-medium"
          >
            <Unlink size={12} /> Отвязать
          </button>
        ) : (
          <div className="flex items-center gap-2 flex-shrink-0">
            <select
              className="input text-xs py-1 max-w-[160px]"
              value={selected}
              onChange={e => setSelected(e.target.value)}
            >
              <option value="">— выбрать объявление —</option>
              {externalVacancies.map(v => (
                <option key={v.id} value={v.id}>{v.title}{v.area ? ` (${v.area})` : ''}</option>
              ))}
            </select>
            <button
              onClick={handleLink}
              disabled={saving || !selected}
              className="btn btn-primary text-xs px-3 py-1.5 flex items-center gap-1"
            >
              <Link2 size={12} /> Привязать
            </button>
          </div>
        )}
      </div>
      {hasLink && (
        <div className="flex items-center gap-3 text-xs text-[color:var(--color-muted-foreground)]">
          <span className={`flex items-center gap-1 ${existingLink.sync_enabled ? 'text-emerald-600' : 'text-gray-400'}`}>
            <Zap size={11} /> {existingLink.sync_enabled ? 'Авто-синхронизация вкл.' : 'Синхронизация откл.'}
          </span>
          {existingLink.last_synced_at && (
            <span className="flex items-center gap-1">
              <Clock size={11} /> {new Date(existingLink.last_synced_at).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          {existingLink.last_sync_count > 0 && (
            <span>+{existingLink.last_sync_count} в последний раз</span>
          )}
        </div>
      )}
    </div>
  );
}

// ── HH Tab ────────────────────────────────────────────────────────
function HHTab({ source, onRefresh, vacancies, links, onLink, onUnlink }) {
  const [clientId, setClientId]   = useState('');
  const [clientSecret, setSecret] = useState('');
  const [interval, setInterval_]  = useState(source?.sync_interval_minutes || 15);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [loadingVacs, setLoadingVacs] = useState(false);
  const [externalVacs, setExternalVacs] = useState([]);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState('');

  const isConnected = source?.is_active;

  const loadExternalVacs = useCallback(async () => {
    if (!isConnected) return;
    setLoadingVacs(true);
    try {
      const res = await api.get('/recruitment/integrations/hh/vacancies');
      setExternalVacs(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally { setLoadingVacs(false); }
  }, [isConnected]);

  useEffect(() => { loadExternalVacs(); }, [loadExternalVacs]);

  async function startOAuth() {
    if (!clientId.trim() || !clientSecret.trim()) return;
    setConnecting(true); setError('');
    try {
      const res = await api.post('/recruitment/integrations/hh/setup', {
        client_id: clientId.trim(),
        client_secret: clientSecret.trim(),
        redirect_uri: HH_CALLBACK_URL,
        sync_interval_minutes: interval,
      });
      // Full-page redirect to hh.ru authorization
      window.location.href = res.data.auth_url;
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
      setConnecting(false);
    }
  }

  async function disconnect() {
    setDisconnecting(true);
    try {
      await api.delete('/recruitment/integrations/hh/disconnect');
      await onRefresh();
    } finally { setDisconnecting(false); }
  }

  async function syncNow() {
    setSyncing(true);
    try {
      await api.post('/recruitment/sync');
      setTimeout(() => { onRefresh(); setSyncing(false); }, 3000);
    } catch { setSyncing(false); }
  }

  return (
    <div className="space-y-4">
      {/* Status */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">hh.ru</p>
          {isConnected && source.employer_name && (
            <p className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">{source.employer_name}</p>
          )}
        </div>
        <StatusBadge isActive={isConnected} error={source?.last_error} />
      </div>

      {source?.last_error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-600">
          {source.last_error}
        </div>
      )}

      {!isConnected ? (
        <>
          <Instructions steps={HH_INSTRUCTIONS} />

          {/* Redirect URI copy box */}
          <div className="rounded-lg bg-gray-50 border border-gray-200 px-3 py-2">
            <p className="text-xs text-[color:var(--color-muted-foreground)] mb-1">Redirect URI для регистрации в dev.hh.ru:</p>
            <p className="text-xs font-mono text-gray-700 break-all select-all">{HH_CALLBACK_URL}</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">
                Client ID <a href="https://dev.hh.ru" target="_blank" rel="noopener noreferrer" className="text-[color:var(--color-primary)] hover:underline inline-flex items-center gap-0.5">dev.hh.ru <ExternalLink size={10} /></a>
              </label>
              <input
                className="input w-full text-sm"
                value={clientId}
                onChange={e => setClientId(e.target.value)}
                placeholder="xxxxxxxx"
                autoComplete="off"
              />
            </div>
            <div>
              <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Client Secret</label>
              <input
                type="password"
                className="input w-full text-sm font-mono"
                value={clientSecret}
                onChange={e => setSecret(e.target.value)}
                placeholder="••••••••"
                autoComplete="off"
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <label className="text-xs text-[color:var(--color-muted-foreground)] flex-shrink-0">Интервал синхронизации:</label>
            <select className="input text-sm py-1" value={interval} onChange={e => setInterval_(+e.target.value)}>
              {[5, 10, 15, 30, 60].map(m => <option key={m} value={m}>{m} мин.</option>)}
            </select>
          </div>

          {error && <p className="text-xs text-red-600">{error}</p>}

          <button
            onClick={startOAuth}
            disabled={connecting || !clientId.trim() || !clientSecret.trim()}
            className="btn btn-primary w-full flex items-center justify-center gap-2"
          >
            {connecting ? (
              <>
                <RefreshCw size={14} className="animate-spin" />
                Перенаправляем на hh.ru...
              </>
            ) : (
              <>
                <ExternalLink size={14} />
                Войти через hh.ru
              </>
            )}
          </button>
        </>
      ) : (
        <>
          {/* Interval + sync controls */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <Clock size={14} className="text-[color:var(--color-muted-foreground)]" />
              <label className="text-xs text-[color:var(--color-muted-foreground)]">Интервал:</label>
              <select
                className="input text-sm py-1"
                value={source.sync_interval_minutes}
                onChange={async e => {
                  await api.patch(`/recruitment/integrations/hh/interval`, null, { params: { interval_minutes: +e.target.value } });
                  onRefresh();
                }}
              >
                {[5, 10, 15, 30, 60].map(m => <option key={m} value={m}>{m} мин.</option>)}
              </select>
            </div>
            <button onClick={syncNow} disabled={syncing} className="btn btn-secondary text-xs flex items-center gap-1.5 py-1.5">
              <RefreshCw size={13} className={syncing ? 'animate-spin' : ''} />
              {syncing ? 'Синхронизируем...' : 'Синхронизировать сейчас'}
            </button>
            <button onClick={disconnect} disabled={disconnecting} className="ml-auto text-xs text-red-500 hover:text-red-700 font-medium">
              Отключить
            </button>
          </div>

          {/* Vacancy linking */}
          <div>
            <p className="text-sm font-semibold mb-2">Привязка вакансий</p>
            <p className="text-xs text-[color:var(--color-muted-foreground)] mb-3">
              Для каждой внутренней вакансии выберите соответствующее объявление на hh.ru — отклики будут автоматически попадать в CRM.
            </p>
            {loadingVacs ? (
              <p className="text-sm text-[color:var(--color-muted-foreground)] text-center py-4">Загружаем объявления hh.ru...</p>
            ) : externalVacs.length === 0 ? (
              <p className="text-sm text-[color:var(--color-muted-foreground)] text-center py-4">Нет активных объявлений на hh.ru</p>
            ) : (
              <div className="space-y-2">
                {vacancies.map(v => (
                  <VacancyLinkRow
                    key={v.id}
                    internalVacancy={v}
                    source="hh"
                    externalVacancies={externalVacs}
                    existingLink={links.find(l => l.vacancy_id === v.id && l.source === 'hh')}
                    onLink={onLink}
                    onUnlink={onUnlink}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ── Avito Tab ──────────────────────────────────────────────────────
function AvitoTab({ source, onRefresh, vacancies, links, onLink, onUnlink }) {
  const [clientId, setClientId]     = useState('');
  const [clientSecret, setSecret]   = useState('');
  const [interval, setInterval_]    = useState(source?.sync_interval_minutes || 15);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisc]    = useState(false);
  const [loadingVacs, setLoadVacs]  = useState(false);
  const [externalVacs, setExtVacs]  = useState([]);
  const [syncing, setSyncing]       = useState(false);
  const [error, setError]           = useState('');

  const isConnected = source?.is_active;

  const loadExternalVacs = useCallback(async () => {
    if (!isConnected) return;
    setLoadVacs(true);
    try {
      const res = await api.get('/recruitment/integrations/avito/vacancies');
      setExtVacs(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally { setLoadVacs(false); }
  }, [isConnected]);

  useEffect(() => { loadExternalVacs(); }, [loadExternalVacs]);

  async function connect() {
    if (!clientId.trim() || !clientSecret.trim()) return;
    setConnecting(true); setError('');
    try {
      await api.post('/recruitment/integrations/avito/connect', {
        client_id: clientId,
        client_secret: clientSecret,
        sync_interval_minutes: interval,
      });
      setClientId(''); setSecret('');
      await onRefresh();
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally { setConnecting(false); }
  }

  async function disconnect() {
    setDisc(true);
    try {
      await api.delete('/recruitment/integrations/avito/disconnect');
      await onRefresh();
    } finally { setDisc(false); }
  }

  async function syncNow() {
    setSyncing(true);
    try {
      await api.post('/recruitment/sync');
      setTimeout(() => { onRefresh(); setSyncing(false); }, 3000);
    } catch { setSyncing(false); }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Авито Работа</p>
          {isConnected && source.employer_name && (
            <p className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">{source.employer_name}</p>
          )}
        </div>
        <StatusBadge isActive={isConnected} error={source?.last_error} />
      </div>

      {source?.last_error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-600">
          {source.last_error}
        </div>
      )}

      {!isConnected ? (
        <>
          <Instructions steps={AVITO_INSTRUCTIONS} />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">
                Client ID <a href="https://developers.avito.ru" target="_blank" rel="noopener noreferrer" className="text-[color:var(--color-primary)] hover:underline inline-flex items-center gap-0.5">developers.avito.ru <ExternalLink size={10} /></a>
              </label>
              <input className="input w-full text-sm" value={clientId} onChange={e => setClientId(e.target.value)} placeholder="xxxxxxxx" autoComplete="off" />
            </div>
            <div>
              <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Client Secret</label>
              <input type="password" className="input w-full text-sm font-mono" value={clientSecret} onChange={e => setSecret(e.target.value)} placeholder="••••••••" autoComplete="off" />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-[color:var(--color-muted-foreground)] flex-shrink-0">Интервал:</label>
            <select className="input text-sm py-1" value={interval} onChange={e => setInterval_(+e.target.value)}>
              {[5, 10, 15, 30, 60].map(m => <option key={m} value={m}>{m} мин.</option>)}
            </select>
          </div>
          {error && <p className="text-xs text-red-600">{error}</p>}
          <button onClick={connect} disabled={connecting || !clientId || !clientSecret} className="btn btn-primary w-full">
            {connecting ? 'Подключаем...' : 'Подключить Авито'}
          </button>
        </>
      ) : (
        <>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <Clock size={14} className="text-[color:var(--color-muted-foreground)]" />
              <label className="text-xs text-[color:var(--color-muted-foreground)]">Интервал:</label>
              <select
                className="input text-sm py-1"
                value={source.sync_interval_minutes}
                onChange={async e => {
                  await api.patch(`/recruitment/integrations/avito/interval`, null, { params: { interval_minutes: +e.target.value } });
                  onRefresh();
                }}
              >
                {[5, 10, 15, 30, 60].map(m => <option key={m} value={m}>{m} мин.</option>)}
              </select>
            </div>
            <button onClick={syncNow} disabled={syncing} className="btn btn-secondary text-xs flex items-center gap-1.5 py-1.5">
              <RefreshCw size={13} className={syncing ? 'animate-spin' : ''} />
              {syncing ? 'Синхронизируем...' : 'Синхронизировать сейчас'}
            </button>
            <button onClick={disconnect} disabled={disconnecting} className="ml-auto text-xs text-red-500 hover:text-red-700 font-medium">
              Отключить
            </button>
          </div>

          <div>
            <p className="text-sm font-semibold mb-2">Привязка вакансий</p>
            <p className="text-xs text-[color:var(--color-muted-foreground)] mb-3">
              Привяжите объявления с Авито к внутренним вакансиям. Отклики из чатов будут импортироваться автоматически.
            </p>
            {loadingVacs ? (
              <p className="text-sm text-center py-4 text-[color:var(--color-muted-foreground)]">Загружаем объявления Авито...</p>
            ) : externalVacs.length === 0 ? (
              <p className="text-sm text-center py-4 text-[color:var(--color-muted-foreground)]">Нет активных объявлений на Авито</p>
            ) : (
              <div className="space-y-2">
                {vacancies.map(v => (
                  <VacancyLinkRow
                    key={v.id}
                    internalVacancy={v}
                    source="avito"
                    externalVacancies={externalVacs}
                    existingLink={links.find(l => l.vacancy_id === v.id && l.source === 'avito')}
                    onLink={onLink}
                    onUnlink={onUnlink}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ── Main modal ─────────────────────────────────────────────────────
export default function IntegrationsModal({ onClose, vacancies }) {
  const [tab, setTab]       = useState('hh');
  const [sources, setSources] = useState({});
  const [links, setLinks]   = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [srcRes, linksRes] = await Promise.all([
        api.get('/recruitment/integrations'),
        api.get('/recruitment/links'),
      ]);
      const srcMap = {};
      for (const s of srcRes.data) srcMap[s.source] = s;
      setSources(srcMap);
      setLinks(linksRes.data);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleLink(vacancyId, source, externalId, externalTitle) {
    await api.post('/recruitment/links', {
      vacancy_id: vacancyId,
      source,
      external_vacancy_id: externalId,
      external_vacancy_title: externalTitle,
    });
    await load();
  }

  async function handleUnlink(linkId) {
    await api.delete(`/recruitment/links/${linkId}`);
    await load();
  }

  const TABS = [
    { key: 'hh', label: 'hh.ru', active: sources.hh?.is_active },
    { key: 'avito', label: 'Авито', active: sources.avito?.is_active },
  ];

  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-2xl w-full flex flex-col overflow-hidden" style={{ maxHeight: '90vh' }}>
        {/* Header */}
        <div className="flex items-center justify-between mb-0 pb-4 border-b border-[color:var(--color-border)]">
          <div className="flex items-center gap-2">
            <Settings size={18} className="text-[color:var(--color-muted-foreground)]" />
            <h3 className="text-base font-semibold">Автоимпорт откликов</h3>
          </div>
          <button onClick={onClose} className="text-xl text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] leading-none">&times;</button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 pt-4 pb-3 border-b border-[color:var(--color-border)] -mx-6 px-6">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                tab === t.key
                  ? 'bg-[color:var(--color-primary)] text-white'
                  : 'text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-muted)]'
              }`}
            >
              {t.label}
              {t.active && (
                <span className={`w-1.5 h-1.5 rounded-full ${tab === t.key ? 'bg-white/70' : 'bg-emerald-500'}`} />
              )}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto pt-4">
          {loading ? (
            <div className="text-center py-12 text-sm text-[color:var(--color-muted-foreground)]">Загрузка...</div>
          ) : tab === 'hh' ? (
            <HHTab
              source={sources.hh}
              onRefresh={load}
              vacancies={vacancies}
              links={links}
              onLink={handleLink}
              onUnlink={handleUnlink}
            />
          ) : (
            <AvitoTab
              source={sources.avito}
              onRefresh={load}
              vacancies={vacancies}
              links={links}
              onLink={handleLink}
              onUnlink={handleUnlink}
            />
          )}
        </div>
      </div>
    </div>
  );
}
