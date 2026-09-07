import { useEffect, useMemo, useState } from 'react';
import {
  Smartphone, RefreshCw, Copy, KeyRound, ShieldCheck, ShieldAlert,
  Lock, MapPin, RotateCw, Download, Trash2, Unlink, BatteryMedium,
} from 'lucide-react';
import api from '../api';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { useToast } from '../providers/ToastProvider.jsx';

/** Порядок намеренный: сверху безобидные запреты, снизу — тот, что отбирает
 *  последний аварийный люк. См. device/mdm_agent/README.md. */
const RESTRICTIONS = [
  { id: 'no_install_apps', label: 'Запретить установку приложений' },
  { id: 'no_uninstall_apps', label: 'Запретить удаление приложений' },
  { id: 'no_install_unknown_sources', label: 'Запретить установку из неизвестных источников' },
  { id: 'no_add_user', label: 'Запретить добавление пользователей' },
  { id: 'no_modify_accounts', label: 'Запретить изменение аккаунтов' },
  { id: 'no_config_mobile_networks', label: 'Запретить настройку мобильных сетей и SIM' },
  { id: 'no_config_tethering', label: 'Запретить раздачу интернета' },
  { id: 'no_safe_boot', label: 'Запретить безопасный режим' },
  { id: 'no_debugging_features', label: 'Запретить отладку по USB' },
  { id: 'no_outgoing_calls', label: 'Запретить исходящие звонки' },
  { id: 'no_sms', label: 'Запретить SMS' },
  { id: 'camera_disabled', label: 'Отключить камеру' },
  { id: 'no_factory_reset', label: 'Запретить сброс до заводских настроек', danger: true },
];

function fmtDateTime(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString('ru-RU');
}

function sinceText(value) {
  if (!value) return 'никогда';
  const minutes = Math.round((Date.now() - new Date(value).getTime()) / 60000);
  if (minutes < 2) return 'только что';
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  return `${Math.round(hours / 24)} дн назад`;
}

/** Телефон опрашивает команды раз в пару минут и делает полный чек-ин раз в
 *  15 минут; час молчания — уже повод смотреть. */
function isStale(device) {
  if (!device.last_seen_at) return true;
  return Date.now() - new Date(device.last_seen_at).getTime() > 60 * 60 * 1000;
}

export default function MdmDevices() {
  const { toast } = useToast();
  const [devices, setDevices] = useState([]);
  const [enrollment, setEnrollment] = useState(null);
  const [salons, setSalons] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [policyDraft, setPolicyDraft] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const selected = useMemo(
    () => devices.find((d) => d.id === selectedId) || null,
    [devices, selectedId],
  );

  useEffect(() => {
    load();
    loadSalons();
  }, []);

  useEffect(() => {
    setPolicyDraft(selected ? structuredClone(selected.policy) : null);
  }, [selectedId, selected?.policy_version]);

  async function load() {
    setLoading(true);
    try {
      const [devicesRes, enrollmentRes] = await Promise.all([
        api.get('mdm/devices'),
        api.get('mdm/enrollment'),
      ]);
      setDevices(devicesRes.data);
      setEnrollment(enrollmentRes.data);
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  async function loadSalons() {
    try {
      const res = await api.get('salons/');
      setSalons(res.data);
    } catch {
      // Список салонов — украшение карточки, без него страница работает.
    }
  }

  async function savePolicy() {
    if (!selected || !policyDraft) return;
    setBusy(true);
    try {
      await api.put(`mdm/devices/${selected.id}/policy`, policyDraft);
      toast('Политика сохранена. Телефон применит её на ближайшей связи', 'success');
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function sendCommand(type, params = {}) {
    if (!selected) return;
    setBusy(true);
    try {
      await api.post(`mdm/devices/${selected.id}/commands`, { type, params });
      toast('Команда поставлена в очередь', 'success');
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function renameDevice(name) {
    if (!selected) return;
    try {
      await api.patch(`mdm/devices/${selected.id}`, { name });
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    }
  }

  async function assignSalon(salonId) {
    if (!selected) return;
    try {
      await api.patch(`mdm/devices/${selected.id}`, { salon_id: salonId || null });
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    }
  }

  function installApk() {
    const url = window.prompt('Ссылка на APK (только https)');
    if (!url) return;
    sendCommand('install_apk', { url: url.trim() });
  }

  function uninstallApp() {
    const pkg = window.prompt('Имя пакета, например com.whatsapp');
    if (!pkg) return;
    sendCommand('uninstall', { package: pkg.trim() });
  }

  function releaseOwner() {
    if (!window.confirm(
      'Снять управление с телефона? Все запреты будут сняты, и вернуть управление '
      + 'можно будет только сбросом до заводских настроек.',
    )) return;
    sendCommand('release_owner');
  }

  function wipeDevice() {
    if (!window.confirm('Стереть телефон полностью? Все данные будут удалены безвозвратно.')) return;
    const name = selected?.name || selected?.model || selected?.id;
    if (window.prompt(`Для подтверждения введите название телефона: ${name}`) !== name) {
      toast('Название не совпало, стирание отменено', 'error');
      return;
    }
    sendCommand('wipe');
  }

  function toggleRestriction(id) {
    setPolicyDraft((prev) => ({
      ...prev,
      restrictions: { ...prev.restrictions, [id]: !prev.restrictions[id] },
    }));
  }

  const columns = [
    {
      label: 'Телефон',
      primary: true,
      render: (d) => (
        <div>
          <div className="font-medium">{d.name || `${d.manufacturer || ''} ${d.model || ''}`.trim() || d.id}</div>
          <div className="text-xs text-[color:var(--color-text-muted)]">
            {[d.manufacturer, d.model, d.android_version && `Android ${d.android_version}`]
              .filter(Boolean).join(' · ') || d.id}
          </div>
        </div>
      ),
    },
    {
      label: 'Салон',
      render: (d) => salons.find((s) => s.id === d.salon_id)?.name || '—',
    },
    {
      label: 'Управление',
      status: true,
      render: (d) => (d.device_owner
        ? <span className="inline-flex items-center gap-1 text-xs"><ShieldCheck size={14} /> владелец</span>
        : <span className="inline-flex items-center gap-1 text-xs text-red-600"><ShieldAlert size={14} /> нет прав</span>),
    },
    {
      label: 'Политика',
      status: true,
      render: (d) => (d.applied_policy_version === d.policy_version
        ? <span className="text-xs">применена</span>
        : <span className="text-xs text-amber-600">ждёт применения</span>),
    },
    {
      label: 'Батарея',
      numeric: true,
      render: (d) => (d.battery == null ? '—' : `${d.battery}%`),
    },
    {
      label: 'Связь',
      render: (d) => (
        <span className={isStale(d) ? 'text-red-600' : ''}>{sinceText(d.last_seen_at)}</span>
      ),
    },
    {
      label: '',
      isAction: true,
      render: (d) => (
        <button
          type="button"
          className="btn btn--secondary btn--sm"
          onClick={() => setSelectedId(d.id === selectedId ? null : d.id)}
        >
          {d.id === selectedId ? 'Свернуть' : 'Настроить'}
        </button>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Smartphone size={20} /> Телефоны салонов
        </h1>
        <button type="button" className="btn flex items-center gap-1.5" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Обновить
        </button>
      </div>

      <section className="bg-[color:var(--color-bg-secondary)] rounded-xl p-4 flex flex-col gap-2">
        <div className="flex items-center gap-2 font-medium">
          <KeyRound size={16} /> Подключение нового телефона
        </div>
        {enrollment?.configured ? (
          <>
            <p className="text-sm text-[color:var(--color-text-muted)]">
              Установите агента на сброшенный телефон, откройте «BONJOUR MDM» и введите эти данные.
              Порядок целиком — в <code>device/mdm_agent/README.md</code>.
            </p>
            <div className="flex flex-wrap gap-2 items-center text-sm">
              <code className="px-2 py-1 rounded bg-[color:var(--color-bg-subtle)]">{enrollment.server_url}</code>
              <button
                type="button"
                className="btn btn--secondary btn--sm flex items-center gap-1.5"
                onClick={() => {
                  navigator.clipboard.writeText(enrollment.enroll_key);
                  toast('Ключ скопирован', 'success');
                }}
              >
                <Copy size={14} /> Скопировать ключ регистрации
              </button>
            </div>
          </>
        ) : (
          <p className="text-sm text-red-600">
            Ключ регистрации не задан: пропишите <code>MDM_ENROLL_KEY</code> в <code>config.json</code>,
            иначе телефоны не смогут зарегистрироваться.
          </p>
        )}
      </section>

      <ResponsiveTable
        columns={columns}
        data={devices}
        keyFn={(d) => d.id}
        loading={loading}
        emptyText="Ни один телефон пока не зарегистрирован"
        emptyHint="Поставьте агента на сброшенный телефон и зарегистрируйте его ключом выше"
        rowState={(d) => (d.id === selectedId ? 'selected' : (isStale(d) ? 'warning' : null))}
        updatedKey={(d) => d.last_seen_at}
      />

      {selected && policyDraft && (
        <section className="bg-[color:var(--color-bg-secondary)] rounded-xl p-4 flex flex-col gap-5">
          <div className="flex flex-col sm:flex-row sm:items-end gap-3">
            <div className="flex-1">
              <label className="block text-xs text-[color:var(--color-text-muted)] mb-1">Название</label>
              <input
                className="input w-full"
                defaultValue={selected.name || ''}
                placeholder="Ресепшен Озерки"
                onBlur={(e) => renameDevice(e.target.value.trim())}
              />
            </div>
            <div className="flex-1">
              <label className="block text-xs text-[color:var(--color-text-muted)] mb-1">Салон</label>
              <select
                className="input w-full"
                value={selected.salon_id || ''}
                onChange={(e) => assignSalon(e.target.value)}
              >
                <option value="">Не указан</option>
                {salons.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
          </div>

          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div>
              <dt className="text-xs text-[color:var(--color-text-muted)]">Последняя связь</dt>
              <dd>{fmtDateTime(selected.last_seen_at)}</dd>
            </div>
            <div>
              <dt className="text-xs text-[color:var(--color-text-muted)]">Зарегистрирован</dt>
              <dd>{fmtDateTime(selected.enrolled_at)}</dd>
            </div>
            <div>
              <dt className="text-xs text-[color:var(--color-text-muted)]">Версия агента</dt>
              <dd>{selected.agent_version || '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-[color:var(--color-text-muted)] flex items-center gap-1">
                <BatteryMedium size={12} /> Батарея
              </dt>
              <dd>{selected.battery == null ? '—' : `${selected.battery}%`}</dd>
            </div>
          </dl>

          {selected.last_error && (
            <p className="text-sm text-red-600">
              Телефон сообщает об ошибке: {selected.last_error}
            </p>
          )}

          {selected.location_at && (
            <p className="text-sm flex items-center gap-1.5">
              <MapPin size={14} />
              <a
                className="underline"
                href={`https://yandex.ru/maps/?pt=${selected.longitude},${selected.latitude}&z=17&l=map`}
                target="_blank"
                rel="noreferrer"
              >
                {selected.latitude?.toFixed(5)}, {selected.longitude?.toFixed(5)}
              </a>
              <span className="text-[color:var(--color-text-muted)]">({fmtDateTime(selected.location_at)})</span>
            </p>
          )}

          <div>
            <h2 className="font-medium mb-2">Запреты</h2>
            <div className="grid sm:grid-cols-2 gap-2">
              {RESTRICTIONS.map(({ id, label, danger }) => (
                <label key={id} className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={!!policyDraft.restrictions[id]}
                    onChange={() => toggleRestriction(id)}
                  />
                  <span className={danger ? 'text-red-600' : ''}>{label}</span>
                </label>
              ))}
            </div>
            {policyDraft.restrictions.no_factory_reset && (
              <p className="text-xs text-red-600 mt-2">
                С этим запретом сброс руками перестаёт работать: снять управление можно будет
                только через агента или командой «Снять управление». Включайте последним.
              </p>
            )}
            <button
              type="button"
              className="btn btn--primary mt-3"
              onClick={savePolicy}
              disabled={busy}
            >
              Сохранить политику
            </button>
          </div>

          <div>
            <h2 className="font-medium mb-2">Команды</h2>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                onClick={() => sendCommand('lock')}>
                <Lock size={14} /> Заблокировать экран
              </button>
              <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                onClick={() => sendCommand('locate')}>
                <MapPin size={14} /> Где телефон
              </button>
              <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                onClick={() => sendCommand('reboot')}>
                <RotateCw size={14} /> Перезагрузить
              </button>
              <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                onClick={installApk}>
                <Download size={14} /> Поставить приложение
              </button>
              <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                onClick={uninstallApp}>
                <Trash2 size={14} /> Удалить приложение
              </button>
              <button type="button" className="btn btn--secondary flex items-center gap-1.5" disabled={busy}
                onClick={releaseOwner}>
                <Unlink size={14} /> Снять управление
              </button>
              <button type="button" className="btn btn--danger flex items-center gap-1.5" disabled={busy}
                onClick={wipeDevice}>
                <Trash2 size={14} /> Стереть телефон
              </button>
            </div>
            <p className="text-xs text-[color:var(--color-text-muted)] mt-2">
              Команда исполнится в течение двух минут — телефон опрашивает очередь будильником.
            </p>
          </div>

          {selected.commands?.length > 0 && (
            <div>
              <h2 className="font-medium mb-2">История команд</h2>
              <div className="flex flex-col gap-1 text-sm">
                {[...selected.commands].reverse().slice(0, 10).map((c) => (
                  <div key={c.id} className="flex flex-wrap gap-2 items-baseline">
                    <span className="text-[color:var(--color-text-muted)] text-xs">
                      {fmtDateTime(c.created_at)}
                    </span>
                    <span className="font-medium">{c.type}</span>
                    <span className={c.status === 'failed' ? 'text-red-600' : ''}>{c.status}</span>
                    {c.result && (
                      <span className="text-[color:var(--color-text-muted)] text-xs">{c.result}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
