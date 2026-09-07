import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Smartphone, RefreshCw, Copy, KeyRound, ShieldCheck, ShieldAlert,
  Lock, MapPin, RotateCw, Download, Trash2, Unlink, BatteryMedium,
  Upload, QrCode, PackageCheck, Boxes, ListRestart,
} from 'lucide-react';
import QRCode from 'qrcode';
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
  const [agent, setAgent] = useState(null);
  const [provisioning, setProvisioning] = useState(null);
  const [qrOpen, setQrOpen] = useState(false);
  const qrCanvas = useRef(null);
  const apkInput = useRef(null);
  const [library, setLibrary] = useState([]);
  const libraryInput = useRef(null);

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
      const [devicesRes, enrollmentRes, agentRes, provisioningRes, libraryRes] = await Promise.all([
        api.get('mdm/devices'),
        api.get('mdm/enrollment'),
        api.get('mdm/agent'),
        api.get('mdm/provisioning'),
        api.get('mdm/apps'),
      ]);
      setDevices(devicesRes.data);
      setEnrollment(enrollmentRes.data);
      setAgent(agentRes.data);
      setProvisioning(provisioningRes.data);
      setLibrary(libraryRes.data);
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  // QR рисуем только когда он открыт: строка длинная, код получается плотным,
  // и постоянно держать его на экране незачем.
  useEffect(() => {
    if (!qrOpen || !provisioning?.payload || !qrCanvas.current) return;
    QRCode.toCanvas(qrCanvas.current, provisioning.payload, {
      width: 320,
      margin: 1,
      errorCorrectionLevel: 'M',
    }).catch((err) => toast(`Не удалось нарисовать QR: ${err.message}`, 'error'));
  }, [qrOpen, provisioning?.payload]);

  async function uploadApk(file) {
    if (!file) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await api.post('mdm/agent', form);
      setAgent(res.data);
      toast(`Загружен агент ${res.data.version_name || 'без версии'}`, 'success');
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
      if (apkInput.current) apkInput.current.value = '';
    }
  }

  async function uploadLibraryApp(file) {
    if (!file) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await api.post('mdm/apps', form);
      toast(`Загружено: ${res.data.package || res.data.filename}`, 'success');
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
      if (libraryInput.current) libraryInput.current.value = '';
    }
  }

  async function deleteLibraryApp(app) {
    if (!window.confirm(`Убрать «${app.package || app.filename}» из каталога? На телефонах приложение останется.`)) return;
    try {
      await api.delete(`mdm/apps/${app.id}`);
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    }
  }

  async function installLibraryApp(appId) {
    if (!selected) {
      toast('Сначала выберите телефон в списке ниже', 'error');
      return;
    }
    setBusy(true);
    try {
      await api.post(`mdm/devices/${selected.id}/install/${appId}`);
      toast('Установка поставлена в очередь', 'success');
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function rolloutAgent() {
    if (!window.confirm(
      `Обновить агента на ${agent?.outdated_devices} телефон(ах)? `
      + 'Телефоны скачают и поставят его сами, вмешательства не потребуется.',
    )) return;
    setBusy(true);
    try {
      const res = await api.post('mdm/agent/rollout');
      toast(`Поставлено в очередь: ${res.data.queued}, пропущено: ${res.data.skipped}`, 'success');
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
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

  /** Интервал опроса задаётся ключом MDM_COMMAND_POLL_SECONDS в config.json;
   *  показываем фактическое значение, чтобы обещание в интерфейсе не разошлось
   *  с тем, что телефоны делают на самом деле. */
  const pollSeconds = enrollment?.command_poll_seconds ?? 120;
  const pollText = pollSeconds % 60 === 0
    ? `${pollSeconds / 60} мин`
    : `${pollSeconds} с`;

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
            <p className="text-xs text-[color:var(--color-text-muted)]">
              {`Телефоны забирают команды раз в ${pollText}. Менять — ключом `}
              <code>MDM_COMMAND_POLL_SECONDS</code>
              {' в config.json, перезапуск не нужен.'}
            </p>
          </>
        ) : (
          <p className="text-sm text-red-600">
            Ключ регистрации не задан: пропишите <code>MDM_ENROLL_KEY</code> в <code>config.json</code>,
            иначе телефоны не смогут зарегистрироваться.
          </p>
        )}
      </section>

      <section className="bg-[color:var(--color-bg-secondary)] rounded-xl p-4 flex flex-col gap-3">
        <div className="flex items-center gap-2 font-medium">
          <PackageCheck size={16} /> Агент на сервере
        </div>

        {agent?.available ? (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span>
              Версия <b>{agent.version_name || 'неизвестна'}</b>
              {agent.version_code ? ` (сборка ${agent.version_code})` : ''}
            </span>
            <span className="text-[color:var(--color-text-muted)]">
              {Math.round(agent.size / 1024)} КБ
            </span>
            {agent.outdated_devices > 0 ? (
              <span className="text-amber-600">
                {`Устарел на ${agent.outdated_devices} телефон(ах)`}
              </span>
            ) : (
              <span>Все телефоны на этой версии</span>
            )}
          </div>
        ) : (
          <p className="text-sm text-red-600">
            APK агента не загружен. Без него не работают ни обновление по воздуху,
            ни подключение по QR.
          </p>
        )}

        <div className="flex flex-wrap gap-2">
          <input
            ref={apkInput}
            type="file"
            accept=".apk,application/vnd.android.package-archive"
            className="hidden"
            onChange={(e) => uploadApk(e.target.files?.[0])}
          />
          <button
            type="button"
            className="btn flex items-center gap-1.5"
            disabled={busy}
            onClick={() => apkInput.current?.click()}
          >
            <Upload size={14} /> Загрузить APK
          </button>
          <button
            type="button"
            className="btn btn--primary flex items-center gap-1.5"
            disabled={busy || !agent?.available || !agent?.outdated_devices}
            onClick={rolloutAgent}
          >
            <Download size={14} /> Обновить телефоны
          </button>
          <button
            type="button"
            className="btn btn--secondary flex items-center gap-1.5"
            disabled={!provisioning?.ready}
            onClick={() => setQrOpen((v) => !v)}
          >
            <QrCode size={14} /> {qrOpen ? 'Скрыть QR' : 'QR для нового телефона'}
          </button>
        </div>

        {provisioning && !provisioning.ready && (
          <p className="text-sm text-red-600">
            {`Подключение по QR недоступно: ${provisioning.problems.join('; ')}`}
          </p>
        )}

        {qrOpen && provisioning?.ready && (
          <div className="flex flex-col sm:flex-row gap-4 items-start pt-2">
            <canvas ref={qrCanvas} className="bg-white p-2 rounded-lg shrink-0" />
            <ol className="text-sm flex flex-col gap-1.5 list-decimal pl-4">
              <li>Сбросьте телефон до заводских настроек (или возьмите новый).</li>
              <li>На самом первом экране приветствия тапните шесть раз подряд.</li>
              <li>Подключитесь к Wi-Fi, когда телефон попросит.</li>
              <li>Наведите камеру телефона на этот код.</li>
              <li>
                Дальше телефон всё сделает сам: скачает агента, станет управляемым
                и появится в списке ниже.
              </li>
            </ol>
          </div>
        )}
      </section>

      <section className="bg-[color:var(--color-bg-secondary)] rounded-xl p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 font-medium">
            <Boxes size={16} /> Приложения для раздачи
          </div>
          <input
            ref={libraryInput}
            type="file"
            accept=".apk,application/vnd.android.package-archive"
            className="hidden"
            onChange={(e) => uploadLibraryApp(e.target.files?.[0])}
          />
          <button
            type="button"
            className="btn btn--secondary btn--sm flex items-center gap-1.5"
            disabled={busy}
            onClick={() => libraryInput.current?.click()}
          >
            <Upload size={14} /> Загрузить APK
          </button>
        </div>

        {library.length === 0 ? (
          <p className="text-sm text-[color:var(--color-text-muted)]">
            Каталог пуст. Загрузите APK — и его можно будет ставить на телефоны одной кнопкой,
            не вводя ссылок руками.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {library.map((app) => (
              <div key={app.id} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium">{app.package || app.filename}</span>
                {app.version_name && (
                  <span className="text-[color:var(--color-text-muted)]">{app.version_name}</span>
                )}
                <span className="text-[color:var(--color-text-muted)]">
                  {Math.round(app.size / 1024 / 1024 * 10) / 10} МБ
                </span>
                {app.installed_on > 0 && (
                  <span className="text-[color:var(--color-text-muted)]">
                    {`стоит на ${app.installed_on}`}
                  </span>
                )}
                <span className="grow" />
                <button
                  type="button"
                  className="btn btn--primary btn--sm"
                  disabled={busy || !selected}
                  title={selected ? '' : 'Выберите телефон в списке ниже'}
                  onClick={() => installLibraryApp(app.id)}
                >
                  Поставить
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => deleteLibraryApp(app)}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            <p className="text-xs text-[color:var(--color-text-muted)]">
              «Поставить» отправляет приложение на выбранный телефон
              {selected ? ` — сейчас это «${selected.name || selected.model}»` : ''}.
            </p>
          </div>
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
              {`Команда исполнится в течение ${pollText} — телефон опрашивает очередь будильником.`}
            </p>
          </div>

          <div>
            <div className="flex items-center justify-between gap-3 mb-2">
              <h2 className="font-medium">
                {`Установлено на телефоне${selected.apps?.length ? `: ${selected.apps.length}` : ''}`}
              </h2>
              <button
                type="button"
                className="btn btn--ghost btn--sm flex items-center gap-1.5"
                disabled={busy}
                onClick={() => sendCommand('refresh_apps')}
              >
                <ListRestart size={14} /> Обновить список
              </button>
            </div>
            {selected.apps?.length ? (
              <>
                <div className="flex flex-col gap-1 max-h-80 overflow-y-auto pr-1">
                  {[...selected.apps]
                    .sort((a, b) => Number(a.system) - Number(b.system)
                      || (a.label || a.package).localeCompare(b.label || b.package, 'ru'))
                    .map((app) => (
                      <div key={app.package} className="flex flex-wrap items-center gap-2 text-sm">
                        <span className={app.enabled ? '' : 'text-[color:var(--color-text-muted)]'}>
                          {app.label || app.package}
                        </span>
                        <span className="text-xs text-[color:var(--color-text-muted)]">
                          {app.package}
                        </span>
                        {app.version_name && (
                          <span className="text-xs text-[color:var(--color-text-muted)]">
                            {app.version_name}
                          </span>
                        )}
                        {app.system && (
                          <span className="text-xs text-[color:var(--color-text-muted)]">системное</span>
                        )}
                        <span className="grow" />
                        {!app.system && (
                          <button
                            type="button"
                            className="btn btn--ghost btn--sm"
                            disabled={busy}
                            onClick={() => {
                              if (!window.confirm(`Удалить «${app.label || app.package}» с телефона?`)) return;
                              sendCommand('uninstall', { package: app.package });
                            }}
                          >
                            Удалить
                          </button>
                        )}
                      </div>
                    ))}
                </div>
                <p className="text-xs text-[color:var(--color-text-muted)] mt-2">
                  {`Список от ${fmtDateTime(selected.apps_updated_at)}. Системные приложения `
                   + 'показаны только те, что видны сотруднику в меню, и удалить их нельзя.'}
                </p>
              </>
            ) : (
              <p className="text-sm text-[color:var(--color-text-muted)]">
                Телефон ещё не присылал список. Он приедет с ближайшим чек-ином.
              </p>
            )}
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
