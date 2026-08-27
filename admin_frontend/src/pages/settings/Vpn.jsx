import { useEffect, useState } from 'react';
import { RefreshCw, Check, Power, ExternalLink } from 'lucide-react';
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

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

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

      <a href="/admin/settings/diagnostics" className="inline-flex items-center gap-1.5 text-sm text-[color:var(--color-primary)] hover:underline">
        <ExternalLink size={14} /> Статус процесса прокси — на вкладке «Диагностика»
      </a>
    </div>
  );
}
