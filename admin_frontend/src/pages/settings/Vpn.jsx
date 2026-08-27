import { useEffect, useState } from 'react';
import { RefreshCw, Check, Power, ExternalLink, Plus, X, AlertTriangle, Square } from 'lucide-react';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';
import { Section, Field } from './shared.jsx';

export default function SettingsVpn() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [doc, setDoc] = useState(null);        // GET /vpn/settings response
  const [urlInput, setUrlInput] = useState('');
  const [profiles, setProfiles] = useState(null); // [{remarks}]
  const [profilesLoading, setProfilesLoading] = useState(false);
  const [selectedRemarks, setSelectedRemarks] = useState('');
  const [restarting, setRestarting] = useState([]); // process keys currently restarting

  const [osProcesses, setOsProcesses] = useState(null); // [{path, label}]
  const [osProcessesLoading, setOsProcessesLoading] = useState(false);
  const [osFilter, setOsFilter] = useState('');
  const [tunStatus, setTunStatus] = useState(null); // {installed, running, log_tail}
  const [tunBusy, setTunBusy] = useState(false);
  const [tunLogOpen, setTunLogOpen] = useState(false);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); loadTunStatus(); }, []);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get('vpn/settings');
      setDoc(res.data);
      setUrlInput(res.data.subscription_url || '');
      if (res.data.active_profile?.remarks) setSelectedRemarks(res.data.active_profile.remarks);
      if (res.data.subscription_url) await loadProfiles(false);
    } catch (err) {
      toast(err?.response?.data?.detail || 'Не удалось загрузить настройки VPN', 'error');
    } finally {
      setLoading(false);
    }
  }

  async function loadTunStatus() {
    try {
      const res = await api.get('vpn/tun/status');
      setTunStatus(res.data);
    } catch {
      // Диагностика — тихо промолчим, страница не должна падать из-за неё
    }
  }

  async function loadOsProcesses() {
    setOsProcessesLoading(true);
    try {
      const res = await api.get('vpn/os-processes');
      setOsProcesses(res.data.processes);
    } catch (err) {
      toast(err?.response?.data?.detail || 'Не удалось получить список процессов', 'error');
    } finally {
      setOsProcessesLoading(false);
    }
  }

  async function saveTunProcesses(next) {
    setSaving(true);
    try {
      const res = await api.put('vpn/tun-processes', { processes: next });
      setDoc((d) => ({ ...d, tun_processes: res.data.tun_processes }));
    } catch (err) {
      toast(err?.response?.data?.detail || 'Не удалось сохранить', 'error');
    } finally {
      setSaving(false);
    }
  }

  function addTunProcess(proc) {
    const current = doc?.tun_processes || [];
    if (current.some((p) => p.path === proc.path)) return;
    saveTunProcesses([...current, proc]);
  }

  function removeTunProcess(path) {
    const current = doc?.tun_processes || [];
    saveTunProcesses(current.filter((p) => p.path !== path));
  }

  async function startTun() {
    setTunBusy(true);
    try {
      await api.post('vpn/tun/start');
      toast('Перехват на уровне ОС включён', 'success');
      await loadTunStatus();
    } catch (err) {
      toast(err?.response?.data?.detail || 'Не удалось включить', 'error');
    } finally {
      setTunBusy(false);
    }
  }

  async function stopTun() {
    setTunBusy(true);
    try {
      await api.post('vpn/tun/stop');
      toast('Перехват выключен', 'success');
      await loadTunStatus();
    } catch (err) {
      toast(err?.response?.data?.detail || 'Не удалось выключить', 'error');
    } finally {
      setTunBusy(false);
    }
  }

  async function loadProfiles(showToast = true) {
    setProfilesLoading(true);
    try {
      const res = await api.get('vpn/profiles');
      setProfiles(res.data.profiles);
      if (showToast) toast(`Серверов в подписке: ${res.data.profiles.length}`, 'success');
    } catch (err) {
      toast(err?.response?.data?.detail || 'Не удалось получить список серверов', 'error');
    } finally {
      setProfilesLoading(false);
    }
  }

  async function saveSubscription() {
    if (!urlInput.trim()) return;
    setSaving(true);
    try {
      const res = await api.post('vpn/subscription', { url: urlInput.trim() });
      setProfiles(res.data.profiles);
      toast(`Подписка сохранена, серверов: ${res.data.profiles.length}`, 'success');
    } catch (err) {
      toast(err?.response?.data?.detail || 'Не удалось прочитать подписку', 'error');
    } finally {
      setSaving(false);
    }
  }

  // Перезапуск после применения сервера/переключения маршрута теперь
  // происходит сам (detached-процесс на бэкенде) — здесь просто держим
  // ключи, которые сейчас в процессе рестарта, и снимаем через паузу:
  // отдельного «нажмите перезапустить» больше нет.
  function markRestarting(keys) {
    if (!keys?.length) return;
    setRestarting((prev) => [...new Set([...prev, ...keys])]);
    setTimeout(() => {
      setRestarting((prev) => prev.filter((k) => !keys.includes(k)));
    }, 8000);
  }

  async function applyProfile() {
    if (!selectedRemarks) return;
    setSaving(true);
    try {
      const res = await api.post('vpn/profile', { remarks: selectedRemarks });
      setDoc((d) => ({ ...d, active_profile: res.data.active_profile }));
      markRestarting(res.data.restarting);
      toast('Сервер применён', 'success');
    } catch (err) {
      toast(err?.response?.data?.detail || 'Не удалось применить сервер', 'error');
    } finally {
      setSaving(false);
    }
  }

  async function toggleRoute(key, value) {
    setSaving(true);
    try {
      const res = await api.put('vpn/route', { route: { [key]: value } });
      setDoc((d) => ({ ...d, route: res.data.route }));
      markRestarting(res.data.restarting);
    } catch (err) {
      toast(err?.response?.data?.detail || 'Не удалось сохранить', 'error');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="text-sm text-[color:var(--color-muted-foreground)] flex items-center gap-2">
        <RefreshCw size={14} className="animate-spin" /> Загружаю…
      </div>
    );
  }

  const routableProcesses = doc?.routable_processes || {};

  return (
    <div className="space-y-6 max-w-3xl">
      <Section title="Сплит-туннель VPN">
        <p className="text-sm text-[color:var(--color-muted-foreground)]">
          Локальный прокси на базе xray-core (тот же движок, что у Happ) — работает headless,
          без GUI-приложения. Ссылка на подписку может меняться со временем: обновите её здесь,
          когда провайдер выдаст новую.
        </p>

        <Field label="Ссылка на подписку VPN" hint="Та же ссылка, что вставляется в Happ (https://.../sub/...)">
          <div className="flex gap-2">
            <input
              className="modal-control flex-1 font-mono text-xs"
              placeholder="https://.../sub/..."
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
            />
            <button className="btn btn--primary shrink-0" onClick={saveSubscription} disabled={saving || !urlInput.trim()}>
              Сохранить
            </button>
          </div>
        </Field>
      </Section>

      <Section title="Сервер">
        {!doc?.subscription_url ? (
          <p className="text-sm text-[color:var(--color-muted-foreground)]">Сначала сохраните ссылку на подписку выше.</p>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <span className="text-sm text-[color:var(--color-muted-foreground)]">
                {profiles ? `Доступно серверов: ${profiles.length}` : 'Список серверов не загружен'}
              </span>
              <button className="btn btn--secondary btn--sm flex items-center gap-1.5" onClick={() => loadProfiles(true)} disabled={profilesLoading}>
                <RefreshCw size={13} className={profilesLoading ? 'animate-spin' : ''} /> Обновить список
              </button>
            </div>

            {profiles && profiles.length > 0 && (
              <div className="space-y-1.5 max-h-80 overflow-y-auto">
                {profiles.map((p) => {
                  const active = doc?.active_profile?.remarks === p.remarks;
                  const selected = selectedRemarks === p.remarks;
                  return (
                    <label
                      key={p.remarks}
                      className={`flex items-center gap-2.5 rounded-lg border px-3 py-2 text-sm cursor-pointer transition-colors ${
                        selected ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)]/5' : 'border-[color:var(--color-border)]'
                      }`}
                    >
                      <input type="radio" name="vpn-profile" checked={selected}
                        onChange={() => setSelectedRemarks(p.remarks)} />
                      <span className="flex-1 truncate">{p.remarks}</span>
                      {active && (
                        <span className="text-xs text-[color:var(--color-success)] flex items-center gap-1 shrink-0">
                          <Check size={13} /> активен
                        </span>
                      )}
                    </label>
                  );
                })}
              </div>
            )}

            {doc?.active_profile && (
              <div className="rounded-lg border border-[color:var(--color-border)] p-3 text-sm space-y-1 font-mono text-xs">
                <div>SOCKS5: {doc.active_profile.socks_proxy}</div>
                {doc.active_profile.http_proxy && <div>HTTP: {doc.active_profile.http_proxy}</div>}
              </div>
            )}

            <button className="btn btn--primary flex items-center gap-2" onClick={applyProfile}
              disabled={saving || !selectedRemarks || selectedRemarks === doc?.active_profile?.remarks}>
              <Power size={15} /> Применить сервер
            </button>
            <p className="text-xs text-[color:var(--color-muted-foreground)]">
              Если порты локального прокси уже заняты (например, ещё открыт GUI-Happ), применение
              вернёт ошибку — закройте Happ (и его службу HappService) и повторите.
            </p>
          </>
        )}
      </Section>

      <Section title="Что идёт через VPN">
        <p className="text-sm text-[color:var(--color-muted-foreground)]">
          Список — весь наш пул процессов (тот же, что на вкладке «Диагностика»), не заранее
          выбранные два-три пункта: любой процесс здесь можно пустить через прокси. Переключатель
          сам перезапускает нужный процесс на новом значении — подождите несколько секунд.
        </p>
        <div className="space-y-2">
          {Object.entries(routableProcesses).map(([key, label]) => (
            <label key={key} className="flex items-center justify-between gap-3 rounded-lg border border-[color:var(--color-border)] px-3 py-2.5 text-sm">
              <span className="flex items-center gap-2">
                {label}
                {restarting.includes(key) && (
                  <span className="text-xs text-[color:var(--color-muted-foreground)] flex items-center gap-1">
                    <RefreshCw size={11} className="animate-spin" /> перезапуск…
                  </span>
                )}
              </span>
              <input type="checkbox" checked={!!doc?.route?.[key]}
                onChange={(e) => toggleRoute(key, e.target.checked)}
                disabled={saving || !doc?.active_profile || restarting.includes(key)} />
            </label>
          ))}
        </div>
        {!doc?.active_profile && (
          <p className="text-xs text-amber-600">Сначала примените сервер выше — без него переключатели ни на что не повлияют.</p>
        )}
      </Section>

      <Section title="Любой процесс (браузер, сторонние приложения)">
        <p className="text-sm text-[color:var(--color-muted-foreground)]">
          Список выше — только наш собственный пул процессов. Здесь можно направить через VPN вообще
          любой запущенный на этой машине процесс — браузер, сторонний бот и т.д. Работает иначе:
          вместо переменной окружения одного процесса, xray-core перехватывает весь сетевой трафик
          машины (TUN-адаптер) и разбирает его обратно на «через VPN» (только выбранные ниже процессы)
          и «напрямую» (всё остальное, по умолчанию).
        </p>

        <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-400 flex gap-2">
          <AlertTriangle size={15} className="shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p>
              Это влияет на сеть всей машины, а не только на выбранные процессы — если что-то пойдёт не
              так, может отвалиться интернет целиком, включая туннель (сайт станет недоступен даже для
              удалённого доступа). Кнопка «Выключить» ниже — аварийный откат, действует сразу.
            </p>
            <p>
              Если сама админка станет недоступна: на этой машине локально, от администратора —{' '}
              <code className="font-mono">schtasks /end /tn BonjourVpnTun</code>.
            </p>
          </div>
        </div>

        <div className="flex items-center justify-between rounded-lg border border-[color:var(--color-border)] px-3 py-2.5">
          <div className="flex items-center gap-2 text-sm">
            <span className={`h-2 w-2 rounded-full ${tunStatus?.running ? 'bg-[color:var(--color-success)]' : 'bg-[color:var(--color-muted-foreground)]'}`} />
            {tunStatus === null ? 'Проверяю статус…' : tunStatus.running ? 'Перехват включён' : tunStatus.installed ? 'Выключен' : 'Задача ещё не настроена'}
          </div>
          <div className="flex gap-2">
            {tunStatus?.running ? (
              <button className="btn btn--danger btn--sm flex items-center gap-1.5" onClick={stopTun} disabled={tunBusy}>
                <Square size={13} /> Выключить
              </button>
            ) : (
              <button className="btn btn--primary btn--sm flex items-center gap-1.5" onClick={startTun}
                disabled={tunBusy || !doc?.active_profile}>
                <Power size={13} /> Включить
              </button>
            )}
          </div>
        </div>
        {!doc?.active_profile && (
          <p className="text-xs text-amber-600">Сначала примените сервер в разделе «Сервер» выше.</p>
        )}

        {tunStatus?.log_tail && (
          <div>
            <button className="text-xs text-[color:var(--color-primary)] hover:underline" onClick={() => setTunLogOpen((v) => !v)}>
              {tunLogOpen ? 'Скрыть лог' : 'Показать лог xray'}
            </button>
            {tunLogOpen && (
              <pre className="mt-1.5 max-h-48 overflow-auto rounded-lg border border-[color:var(--color-border)] p-2 text-[11px] font-mono whitespace-pre-wrap">
                {tunStatus.log_tail}
              </pre>
            )}
          </div>
        )}

        <Field label="Выбранные процессы">
          {(doc?.tun_processes || []).length === 0 ? (
            <p className="text-sm text-[color:var(--color-muted-foreground)]">Пока ни один процесс не выбран — трафик идёт напрямую.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {(doc?.tun_processes || []).map((p) => (
                <span key={p.path} className="inline-flex items-center gap-1.5 rounded-full border border-[color:var(--color-border)] pl-3 pr-1.5 py-1 text-xs">
                  {p.label}
                  <button onClick={() => removeTunProcess(p.path)} disabled={saving} className="rounded-full hover:bg-[color:var(--color-muted)] p-0.5">
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          )}
        </Field>

        <Field label="Добавить процесс" hint="Список запущенных сейчас процессов с исполняемым файлом — обновите, если нужного пока нет в списке (например, ещё не запущен)">
          <div className="flex gap-2 mb-2">
            <input
              className="modal-control flex-1 text-sm"
              placeholder="Фильтр по названию…"
              value={osFilter}
              onChange={(e) => setOsFilter(e.target.value)}
            />
            <button className="btn btn--secondary btn--sm flex items-center gap-1.5 shrink-0" onClick={loadOsProcesses} disabled={osProcessesLoading}>
              <RefreshCw size={13} className={osProcessesLoading ? 'animate-spin' : ''} /> Обновить список
            </button>
          </div>
          {osProcesses === null ? (
            <p className="text-sm text-[color:var(--color-muted-foreground)]">Нажмите «Обновить список», чтобы увидеть запущенные процессы.</p>
          ) : (
            <div className="space-y-1 max-h-72 overflow-y-auto">
              {osProcesses
                .filter((p) => p.label.toLowerCase().includes(osFilter.toLowerCase()))
                .map((p) => {
                  const added = (doc?.tun_processes || []).some((t) => t.path === p.path);
                  return (
                    <div key={p.path} className="flex items-center justify-between gap-2 rounded-lg border border-[color:var(--color-border)] px-3 py-1.5 text-sm">
                      <div className="min-w-0">
                        <div className="truncate">{p.label}</div>
                        <div className="truncate text-[11px] text-[color:var(--color-muted-foreground)] font-mono">{p.path}</div>
                      </div>
                      <button
                        className="btn btn--secondary btn--sm flex items-center gap-1 shrink-0"
                        onClick={() => addTunProcess(p)}
                        disabled={saving || added}
                      >
                        {added ? <Check size={13} /> : <Plus size={13} />}
                        {added ? 'Добавлен' : 'Добавить'}
                      </button>
                    </div>
                  );
                })}
            </div>
          )}
        </Field>
      </Section>

      <a href="/admin/settings/diagnostics" className="inline-flex items-center gap-1.5 text-sm text-[color:var(--color-primary)] hover:underline">
        <ExternalLink size={14} /> Статус процесса прокси — на вкладке «Диагностика»
      </a>
    </div>
  );
}
