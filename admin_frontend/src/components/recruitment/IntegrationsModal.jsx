import { useState, useEffect, useCallback } from 'react';
import {
  X, CheckCircle, AlertCircle, RefreshCw, Link2, Unlink,
  ExternalLink, Settings, Clock, Zap,
} from 'lucide-react';
import api from '../../api';

const HH_CALLBACK_URL = `${window.location.origin}/api/recruitment/integrations/hh/callback`;

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
  const [connecting, setConnecting]     = useState(false);
  const [disconnecting, setDisconn]     = useState(false);
  const [loadingVacs, setLoadingVacs]   = useState(false);
  const [externalVacs, setExternalVacs] = useState([]);
  const [syncing, setSyncing]           = useState(false);
  const [error, setError]               = useState('');

  const isConnected    = source?.is_active;
  const envConfigured  = source?.env_configured ?? false;

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
    setConnecting(true); setError('');
    try {
      const res = await api.get('/recruitment/integrations/hh/auth-url', {
        params: { redirect_uri: HH_CALLBACK_URL },
      });
      window.location.href = res.data.auth_url;
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
      setConnecting(false);
    }
  }

  async function disconnect() {
    setDisconn(true);
    try { await api.delete('/recruitment/integrations/hh/disconnect'); await onRefresh(); }
    finally { setDisconn(false); }
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
          {!envConfigured ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 space-y-1">
              <p className="font-medium">Ожидаем одобрения заявки hh.ru</p>
              <p className="text-xs text-amber-700">
                После получения Client ID и Secret их нужно добавить в <code className="bg-amber-100 px-1 rounded">.env</code> на сервере:
              </p>
              <pre className="text-xs bg-amber-100 rounded px-2 py-1.5 mt-1 select-all">HH_CLIENT_ID=...<br/>HH_CLIENT_SECRET=...</pre>
              <p className="text-xs text-amber-700 mt-1">
                Redirect URI для регистрации в dev.hh.ru:
              </p>
              <p className="text-xs font-mono bg-amber-100 rounded px-2 py-1 break-all select-all">{HH_CALLBACK_URL}</p>
            </div>
          ) : (
            <>
              {error && <p className="text-xs text-red-600">{error}</p>}
              <button
                onClick={startOAuth}
                disabled={connecting}
                className="btn btn-primary w-full flex items-center justify-center gap-2"
              >
                {connecting
                  ? <><RefreshCw size={14} className="animate-spin" /> Перенаправляем на hh.ru...</>
                  : <><ExternalLink size={14} /> Войти через hh.ru</>}
              </button>
            </>
          )}
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
                  await api.patch(`/recruitment/integrations/hh/interval`, null, { params: { interval_minutes: +e.target.value } });
                  onRefresh();
                }}
              >
                {[1, 5, 10, 15, 30, 60].map(m => <option key={m} value={m}>{m} мин.</option>)}
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
              Для каждой внутренней вакансии выберите соответствующее объявление на hh.ru — отклики будут автоматически попадать в CRM.
            </p>
            {loadingVacs ? (
              <p className="text-sm text-[color:var(--color-muted-foreground)] text-center py-4">Загружаем объявления hh.ru...</p>
            ) : externalVacs.length === 0 ? (
              <p className="text-sm text-[color:var(--color-muted-foreground)] text-center py-4">Нет активных объявлений на hh.ru</p>
            ) : vacancies.length === 0 ? (
              <p className="text-sm text-[color:var(--color-muted-foreground)] text-center py-4">
                Сначала создайте вакансию в CRM — кнопка «+ Вакансия» на главной странице подбора.
              </p>
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

// ── Avito manual vacancy link row ─────────────────────────────────
function AvitoVacancyLinkRow({ internalVacancy, existingLink, onLink, onUnlink }) {
  const [vacancyId, setVacancyId] = useState('');
  const [saving, setSaving]       = useState(false);
  const [lookupTitle, setLookupTitle] = useState('');

  async function handleLink() {
    const id = vacancyId.trim();
    if (!id) return;
    setSaving(true);
    try {
      // Try to get title for display
      let title = lookupTitle || `Авито #${id}`;
      try {
        const res = await api.get(`/recruitment/integrations/avito/vacancy/${id}`);
        if (res.data?.title) title = res.data.title;
      } catch { /* ignore, use fallback title */ }
      await onLink(internalVacancy.id, 'avito', id, title);
      setVacancyId('');
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
              → {existingLink.external_vacancy_title || `Авито #${existingLink.external_vacancy_id}`}
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
            <input
              className="input text-xs py-1 w-32"
              value={vacancyId}
              onChange={e => setVacancyId(e.target.value.replace(/\D/g, ''))}
              placeholder="ID вакансии"
            />
            <button
              onClick={handleLink}
              disabled={saving || !vacancyId.trim()}
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

// ── Avito Tab ──────────────────────────────────────────────────────
function AvitoTab({ source, onRefresh, vacancies, links, onLink, onUnlink }) {
  const [clientId, setClientId]     = useState('');
  const [clientSecret, setSecret]   = useState('');
  const [interval, setInterval_]    = useState(source?.sync_interval_minutes || 15);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconn] = useState(false);
  const [syncing, setSyncing]       = useState(false);
  const [error, setError]           = useState('');

  const isConnected = source?.is_active;

  async function connect() {
    if (!clientId.trim() || !clientSecret.trim()) return;
    setConnecting(true); setError('');
    try {
      await api.post('/recruitment/integrations/avito/connect', {
        client_id: clientId.trim(),
        client_secret: clientSecret.trim(),
        sync_interval_minutes: interval,
      });
      setClientId(''); setSecret('');
      await onRefresh();
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally { setConnecting(false); }
  }

  async function disconnect() {
    setDisconn(true);
    try { await api.delete('/recruitment/integrations/avito/disconnect'); await onRefresh(); }
    finally { setDisconn(false); }
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
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Client ID</label>
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
          <button onClick={connect} disabled={connecting || !clientId.trim() || !clientSecret.trim()} className="btn btn-primary w-full">
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
                {[1, 5, 10, 15, 30, 60].map(m => <option key={m} value={m}>{m} мин.</option>)}
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
            <div className="rounded-lg bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-700 mb-3">
              API Авито не предоставляет список вакансий. Введите ID объявления вручную — его можно найти в конце URL вакансии на avito.ru, например:<br />
              <span className="font-mono">avito.ru/…/vakansii/nazvanie-<strong>123456789</strong></span>
            </div>
            {vacancies.length === 0 ? (
              <p className="text-sm text-center py-4 text-[color:var(--color-muted-foreground)]">
                Сначала создайте вакансию в CRM — кнопка «+ Вакансия» на главной странице подбора.
              </p>
            ) : (
              <div className="space-y-2">
                {vacancies.map(v => (
                  <AvitoVacancyLinkRow
                    key={v.id}
                    internalVacancy={v}
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
