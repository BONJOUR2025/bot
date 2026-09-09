import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Smartphone, RefreshCw, Copy, KeyRound, ShieldCheck, ShieldAlert,
  Lock, MapPin, RotateCw, Download, Trash2, Unlink, BatteryMedium,
  Upload, QrCode, PackageCheck, Boxes, ListRestart, Camera as CameraIcon,
  Gauge, ShieldBan, AppWindow, History as HistoryIcon,
  Volume2, MessageSquareWarning, HardDrive, Wifi, Cpu, Clock, EyeOff, Eraser,
  MonitorSmartphone, Play, KeyRound as KeyIcon, Sun, Radio, Send,
  Siren, CalendarClock, Plus, VolumeX, Moon, BellOff,
} from 'lucide-react';
import QRCode from 'qrcode';
import api from '../api';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { useToast } from '../providers/ToastProvider.jsx';

/** Статусы команды по-русски: история читается оператором, а не разработчиком.
 *  «Ждёт» и «на телефоне» — разные вещи: отменить можно только первое. */
const CMD_STATUS = {
  pending: 'ждёт',
  sent: 'на телефоне',
  done: 'выполнено',
  failed: 'сбой',
  canceled: 'отменено',
};

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
  { id: 'no_screen_capture', label: 'Запретить скриншоты и запись экрана' },
  { id: 'no_bluetooth', label: 'Запретить Bluetooth' },
  { id: 'no_usb_file_transfer', label: 'Запретить передачу файлов по USB' },
  { id: 'no_config_wifi', label: 'Запретить менять настройки Wi-Fi' },
  { id: 'no_factory_reset', label: 'Запретить сброс до заводских настроек', danger: true },
];

function fmtBytes(mb) {
  if (mb == null) return '—';
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} ГБ`;
  return `${mb} МБ`;
}

function fmtUptime(sec) {
  if (sec == null) return '—';
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d > 0) return `${d} дн ${h} ч`;
  if (h > 0) return `${h} ч ${m} мин`;
  return `${m} мин`;
}

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

function SnapshotThumb({ snap }) {
  // Ссылка подписана на сервере и открывается в браузере как скан паспорта —
  // никакой blob-возни: в iOS-обёртке blob-ссылки с target=_blank не работают,
  // а обычный https-адрес открывается везде.
  const label = `${snap.lens === 'front' ? 'передняя' : 'задняя'} · ${fmtDateTime(snap.taken_at)}`;
  return (
    <a
      href={snap.url}
      target="_blank"
      rel="noreferrer"
      className="block w-full max-w-[10rem]"
      title={label}
    >
      <img
        src={snap.url}
        alt="снимок"
        loading="lazy"
        className="w-full aspect-square object-cover rounded-lg border border-[color:var(--color-border)] bg-black"
      />
      <span className="block text-xs text-[color:var(--color-text-muted)] mt-1 truncate">{label}</span>
    </a>
  );
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
  const [pollDraft, setPollDraft] = useState('');
  const [appFilter, setAppFilter] = useState('');
  const [showSystemApps, setShowSystemApps] = useState(false);
  const [selectedApps, setSelectedApps] = useState(() => new Set());
  const [deviceTab, setDeviceTab] = useState('overview');
  const [kioskDraft, setKioskDraft] = useState(null);
  const [schedules, setSchedules] = useState([]);
  // Работает ли живое обновление. Показываем честно: если оно оборвалось,
  // оператор должен знать, что смотрит на застывшую картинку.
  const [live, setLive] = useState(false);

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
    setKioskDraft(selected ? structuredClone(selected.policy.kiosk || {}) : null);
  }, [selectedId, selected?.policy_version]);

  // Выделение и поиск относятся к конкретному телефону: при переключении их
  // нужно сбросить, иначе на новом аппарате окажутся отмечены чужие пакеты.
  useEffect(() => {
    setSelectedApps(new Set());
    setAppFilter('');
    setShowSystemApps(false);
    setDeviceTab('overview');
  }, [selectedId]);

  async function load() {
    setLoading(true);
    try {
      const [devicesRes, enrollmentRes, agentRes, provisioningRes, libraryRes, schedulesRes] = await Promise.all([
        api.get('mdm/devices'),
        api.get('mdm/enrollment'),
        api.get('mdm/agent'),
        api.get('mdm/provisioning'),
        api.get('mdm/apps'),
        api.get('mdm/schedules'),
      ]);
      setDevices(devicesRes.data);
      setEnrollment(enrollmentRes.data);
      setAgent(agentRes.data);
      setProvisioning(provisioningRes.data);
      setLibrary(libraryRes.data);
      setSchedules(schedulesRes.data);
      setPollDraft(String(enrollmentRes.data.command_poll_seconds ?? 120));
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  /** Живое обновление парка.
   *
   *  Запрос висит на сервере, пока в парке ничего не менялось, и возвращается
   *  сразу, как что-то произошло: приехал снимок с камеры, телефон ответил на
   *  команду, обновилась телеметрия. Раньше всё это ждало, пока оператор
   *  догадается нажать «обновить» — а снимок с камеры заказывают как раз
   *  тогда, когда смотрят на экран и ждут его сию секунду.
   *
   *  Обновляем молча: без индикатора загрузки и без сброса того, что оператор
   *  сейчас правит. Черновики политики завязаны на policy_version, поэтому
   *  чужие изменения телеметрии их не трогают.
   */
  const watchMarker = useRef('');

  useEffect(() => {
    let stopped = false;
    const controller = new AbortController();
    const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    async function watch() {
      let failures = 0;
      while (!stopped) {
        // Вкладку свернули — держать открытое соединение незачем.
        if (document.hidden) {
          await pause(1000);
          continue;
        }
        try {
          const res = await api.get('mdm/devices/watch', {
            params: { marker: watchMarker.current },
            signal: controller.signal,
          });
          if (stopped) return;
          watchMarker.current = res.data.marker;
          if (res.data.changed) setDevices(res.data.devices);
          setLive(true);
          failures = 0;
        } catch (err) {
          if (stopped || err.code === 'ERR_CANCELED') return;
          setLive(false);
          // Обрыв висящего запроса — штатное дело: туннель, сон вкладки,
          // пересборка сервера. Молчим и отступаем, а не сыплем тостами:
          // оператор ничего не сделал не так и починить это не может.
          failures += 1;
          await pause(Math.min(2000 * failures, 30000));
        }
      }
    }

    watch();
    return () => {
      stopped = true;
      controller.abort();
    };
  }, []);

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

  async function savePollSeconds() {
    const value = Number(pollDraft);
    if (!Number.isFinite(value) || value < 30 || value > 3600) {
      toast('Допустимо от 30 до 3600 секунд', 'error');
      return;
    }
    setBusy(true);
    try {
      const res = await api.put('mdm/settings', { command_poll_seconds: value });
      setEnrollment(res.data);
      toast('Телефоны перейдут на новый интервал в течение одного цикла', 'success');
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
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

  async function saveKiosk() {
    if (!selected || !policyDraft || !kioskDraft) return;
    if (kioskDraft.enabled && !kioskDraft.home && !(kioskDraft.packages || []).length) {
      toast('Выберите приложение для киоска', 'error');
      return;
    }
    setBusy(true);
    try {
      const next = { ...structuredClone(selected.policy), kiosk: kioskDraft };
      await api.put(`mdm/devices/${selected.id}/policy`, next);
      toast('Настройки киоска сохранены. Телефон применит их на ближайшей связи', 'success');
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  function addWifi() {
    const ssid = window.prompt('Имя сети Wi-Fi (SSID)');
    if (!ssid) return;
    const password = window.prompt('Пароль (пусто — открытая сеть)') || '';
    sendCommand('add_wifi', { ssid: ssid.trim(), password, hidden: false });
  }

  function toggleStayAwake(enabled) {
    sendCommand('set_stay_awake', { enabled });
  }

  function toggleStatusBar(disabled) {
    sendCommand('set_status_bar', { disabled });
  }

  function syncTime() {
    sendCommand('set_time', { epoch_ms: Date.now() });
  }

  async function broadcast() {
    const type = window.prompt('Команда всем телефонам: lock, reboot, refresh_apps, set_time');
    if (!type) return;
    if (!window.confirm(`Отправить «${type.trim()}» ВСЕМ телефонам (${devices.length})?`)) return;
    setBusy(true);
    try {
      const params = type.trim() === 'set_time' ? { epoch_ms: Date.now() } : {};
      const res = await api.post('mdm/broadcast', { type: type.trim(), params });
      toast(`Отправлено на ${res.data.queued} из ${res.data.total}`, 'success');
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function lostMode() {
    if (!selected) return;
    if (!window.confirm(
      `Включить режим пропажи для «${selected.name || selected.model}»?

`
      + 'Телефон заблокируется, покажет сообщение на экране, поднимет сигнал, '
      + 'пришлёт координаты и кадр с камеры.',
    )) return;
    const message = window.prompt(
      'Текст на экране блокировки:',
      'Телефон потерян. Пожалуйста, верните владельцу.',
    );
    if (message === null) return;
    setBusy(true);
    try {
      await api.post(`mdm/devices/${selected.id}/lost-mode`, { message });
      toast('Режим пропажи включён — команды в очереди', 'success');
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  /** Отбой: телефон нашёлся. Снимает то, что режим пропажи оставил включённым
   *  и что само не погаснет, — сигнал и сообщение на экране. Разбирать это по
   *  одной команде пришлось бы как раз в спешке. */
  async function foundMode() {
    if (!selected) return;
    setBusy(true);
    try {
      await api.post(`mdm/devices/${selected.id}/found-mode`);
      toast('Отбой: сигнал выключен, сообщение снято', 'success');
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function cancelCommand(commandId) {
    if (!selected) return;
    setBusy(true);
    try {
      await api.delete(`mdm/devices/${selected.id}/commands/${commandId}`);
      toast('Команда снята с очереди', 'success');
      await load();
    } catch (err) {
      // Гонка здесь штатная: телефон мог забрать команду за те секунды, пока
      // оператор целился в кнопку. Говорим об этом прямо, а не «ошибка».
      const detail = err.response?.data?.detail;
      toast(
        detail === 'command_not_cancelable'
          ? 'Поздно: телефон уже забрал команду'
          : detail || err.message,
        'error',
      );
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function addSchedule() {
    const time = window.prompt('Время по Москве (ЧЧ:ММ), например 04:30');
    if (!time) return;
    const command_type = window.prompt('Команда: reboot, refresh_apps, locate, set_time, lock');
    if (!command_type) return;
    setBusy(true);
    try {
      const params = command_type.trim() === 'set_time' ? {} : {};
      await api.post('mdm/schedules', {
        time: time.trim(), command_type: command_type.trim(), command_params: params, target: 'all', enabled: true,
      });
      toast('Расписание добавлено', 'success');
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function deleteSchedule(id) {
    if (!window.confirm('Удалить расписание?')) return;
    try {
      await api.delete(`mdm/schedules/${id}`);
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    }
  }

  function launchApp() {
    const pkg = window.prompt('Имя пакета, которое открыть, напр. com.yandex.browser');
    if (!pkg) return;
    sendCommand('launch_app', { package: pkg.trim() });
  }

  /** @param grant true — выдать разрешение, false — отозвать. */
  function grantPermission(grant) {
    const what = grant ? 'выдать' : 'отозвать';
    const pkg = window.prompt(`Имя пакета, которому ${what} разрешение, напр. ru.agbis.AgbisPhoto`);
    if (!pkg) return;
    const perm = window.prompt('Разрешение, напр. android.permission.CAMERA');
    if (!perm) return;
    sendCommand('grant_permission', { package: pkg.trim(), permission: perm.trim(), grant });
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

  function ringPhone() {
    sendCommand('ring', { seconds: 30 });
  }

  function stopRing() {
    sendCommand('stop_ring');
  }

  function clearLockMessage() {
    sendCommand('message', { text: '' });
  }

  /** Сообщение во весь экран — в отличие от надписи под замком, его видит
   *  сотрудник, который прямо сейчас работает на телефоне. */
  function showAlert() {
    const text = window.prompt('Текст сообщения во весь экран телефона:');
    if (text === null) return;
    if (!text.trim()) {
      toast('Пустое сообщение показывать нечего', 'error');
      return;
    }
    const title = window.prompt('Заголовок (можно пусто):', 'Сообщение от руководства') || '';
    // Неснимаемым окном останавливают работу на телефоне, поэтому спрашиваем
    // отдельно: закрыть его сотрудник уже не сможет, только команда stop_alert.
    const locking = window.confirm(
      'Разрешить сотруднику закрыть сообщение кнопкой?\n\n'
      + 'OK — сотрудник закроет сам.\n'
      + 'Отмена — окно останется на экране, пока вы не уберёте его командой.',
    );
    sendCommand('alert', { text: text.trim(), title: title.trim(), dismissible: locking });
  }

  function stopAlert() {
    sendCommand('stop_alert');
  }

  /** Сменить код экрана. Пустой — снять блокировку. */
  function setScreenPassword() {
    const code = window.prompt(
      'Новый код разблокировки (минимум 4 знака).\n'
      + 'Оставьте пустым, чтобы снять блокировку совсем:',
      '',
    );
    if (code === null) return;
    const value = code.trim();
    if (value && value.length < 4) {
      toast('Android не примет код короче четырёх знаков', 'error');
      return;
    }
    if (!value && !window.confirm(
      'Снять блокировку экрана полностью?\n\n'
      + 'Телефон останется без кода: его сможет взять и разблокировать кто угодно. '
      + 'Панель будет предупреждать об этом, пока код не поставят снова.',
    )) return;
    sendCommand('set_password', { password: value });
  }

  function setLockMessage() {
    const current = selected?.lock_message || '';
    const text = window.prompt(
      'Текст на экране блокировки (для потерянного телефона). Пусто — убрать сообщение:',
      current,
    );
    if (text === null) return;
    sendCommand('message', { text: text.trim() });
  }

  function setVolume() {
    const raw = window.prompt('Громкость в процентах (0–100):', '100');
    if (raw === null) return;
    const percent = Number(raw);
    if (!Number.isFinite(percent) || percent < 0 || percent > 100) {
      toast('Нужно число от 0 до 100', 'error');
      return;
    }
    sendCommand('set_volume', { percent });
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

  async function forgetDevice() {
    if (!selected) return;
    const title = selected.name || `${selected.manufacturer || ''} ${selected.model || ''}`.trim() || selected.id;
    // Формулировка намеренно длинная: удаление карточки — не то же самое, что
    // снятие управления, и перепутать их дорого.
    if (!window.confirm(
      `Убрать «${title}» из списка?

`
      + 'Сам телефон при этом останется управляемым: запреты продолжат действовать, '
      + 'а агент начнёт получать отказ на каждой попытке связаться. Если телефон живой '
      + 'и нужно вернуть его в обычное состояние — сначала «Снять управление», и только потом убирать.',
    )) return;
    setBusy(true);
    try {
      await api.delete(`mdm/devices/${selected.id}`);
      setSelectedId(null);
      toast('Телефон убран из списка', 'success');
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  function toggleRestriction(id) {
    setPolicyDraft((prev) => ({
      ...prev,
      restrictions: { ...prev.restrictions, [id]: !prev.restrictions[id] },
    }));
  }

  const matchesFilter = (app) => {
    const needle = appFilter.trim().toLowerCase();
    if (!needle) return true;
    return `${app.label || ''} ${app.package}`.toLowerCase().includes(needle);
  };

  const byName = (a, b) => (a.label || a.package).localeCompare(b.label || b.package, 'ru');

  const removableApps = (selected?.apps || []).filter((a) => !a.system && matchesFilter(a)).sort(byName);
  const systemApps = (selected?.apps || []).filter((a) => a.system && matchesFilter(a)).sort(byName);

  function toggleApp(pkg) {
    setSelectedApps((prev) => {
      const next = new Set(prev);
      if (next.has(pkg)) next.delete(pkg); else next.add(pkg);
      return next;
    });
  }

  function toggleAllApps() {
    setSelectedApps((prev) => (
      prev.size === removableApps.length ? new Set() : new Set(removableApps.map((a) => a.package))
    ));
  }

  async function uninstallSelected() {
    const packages = [...selectedApps];
    if (!packages.length) return;
    if (!window.confirm(`Удалить с телефона ${packages.length} приложени(й)?`)) return;
    setBusy(true);
    try {
      // По одной команде на приложение: телефон исполнит их подряд на
      // ближайшей связи, а в истории будет видно, что именно удалялось.
      for (const pkg of packages) {
        await api.post(`mdm/devices/${selected.id}/commands`, {
          type: 'uninstall',
          params: { package: pkg },
        });
      }
      toast(`Удаление ${packages.length} приложени(й) поставлено в очередь`, 'success');
      setSelectedApps(new Set());
      await load();
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
    }
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
        <div className="flex items-center gap-2">
          <span
            className="flex items-center gap-1.5 text-xs text-[color:var(--color-text-muted)]"
            title={live
              ? 'Снимки, ответы на команды и телеметрия появляются сами'
              : 'Живое обновление оборвалось — данные могут устареть'}
          >
            <span className={`inline-block w-1.5 h-1.5 rounded-full ${
              live ? 'bg-emerald-500 animate-pulse' : 'bg-[color:var(--color-text-muted)]'}`}
            />
            {live ? 'обновляется само' : 'нет связи'}
          </span>
          <button type="button" className="btn btn--secondary flex items-center gap-1.5"
            disabled={busy || !devices.length} onClick={broadcast}>
            <Send size={14} /> Команда всем
          </button>
          <button type="button" className="btn flex items-center gap-1.5" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Обновить
          </button>
        </div>
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
            <div className="flex flex-wrap items-end gap-2 pt-1">
              <div>
                <label className="block text-xs text-[color:var(--color-text-muted)] mb-1">
                  Телефоны присылают полный отчёт раз в, секунд
                </label>
                <input
                  type="number"
                  min={30}
                  max={3600}
                  step={30}
                  className="input w-full sm:w-40"
                  value={pollDraft}
                  onChange={(e) => setPollDraft(e.target.value)}
                />
              </div>
              <button
                type="button"
                className="btn btn--secondary"
                disabled={busy || String(enrollment.command_poll_seconds) === pollDraft}
                onClick={savePollSeconds}
              >
                Сохранить
              </button>
              <p className="text-xs text-[color:var(--color-text-muted)] basis-full">
                Сейчас {pollText}. Это про телеметрию — заряд, память, список приложений.
                На скорость команд не влияет: телефон держит открытый запрос и получает
                команду за секунды. Допустимо от 30 секунд до часа; телефоны перейдут на
                новое значение в течение одного цикла, ничего перезапускать не нужно.
              </p>
            </div>
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
            accept=".apk,.xapk,application/vnd.android.package-archive"
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
            Каталог пуст. Загрузите APK или XAPK — и его можно будет ставить на телефоны
            одной кнопкой, не вводя ссылок руками.
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
                {app.parts > 1 && (
                  <span className="text-[color:var(--color-text-muted)]">
                    {`набор из ${app.parts} частей`}
                  </span>
                )}
                {app.has_obb && (
                  <span className="text-amber-600" title="Данные для игр мы не раскладываем">
                    внутри данные для игр
                  </span>
                )}
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

      <section className="bg-[color:var(--color-bg-secondary)] rounded-xl p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 font-medium">
            <CalendarClock size={16} /> Расписание команд
          </div>
          <button type="button" className="btn btn--secondary btn--sm flex items-center gap-1.5"
            disabled={busy} onClick={addSchedule}>
            <Plus size={14} /> Добавить
          </button>
        </div>
        {schedules.length === 0 ? (
          <p className="text-sm text-[color:var(--color-text-muted)]">
            Нет расписаний. Например: перезагрузка всех телефонов каждую ночь в 04:30
            или обновление списка приложений утром.
          </p>
        ) : (
          <div className="flex flex-col gap-1">
            {schedules.map((s) => (
              <div key={s.id} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium tabular-nums">{s.time}</span>
                <span>{s.command_type}</span>
                <span className="text-[color:var(--color-text-muted)]">
                  {s.target === 'all' ? 'всем' : s.target.startsWith('salon:') ? 'салон' : 'телефону'}
                </span>
                {!s.enabled && <span className="text-[color:var(--color-text-muted)]">(выключено)</span>}
                {s.last_run_date && (
                  <span className="text-xs text-[color:var(--color-text-muted)]">
                    последний запуск {s.last_run_date}
                  </span>
                )}
                <span className="grow" />
                <button type="button" className="btn btn--ghost btn--sm"
                  onClick={() => deleteSchedule(s.id)}>
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
        <p className="text-xs text-[color:var(--color-text-muted)]">
          Время — по Москве. Проверка раз в минуту; команда уходит телефонам на их ближайшей связи.
        </p>
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
        <section className="bg-[color:var(--color-bg-secondary)] rounded-xl p-4 flex flex-col gap-4">
          {/* Шапка: название, салон, ключевое состояние — видно на любой вкладке */}
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

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <span className="inline-flex items-center gap-1">
              {selected.device_owner
                ? <><ShieldCheck size={14} /> под управлением</>
                : <span className="inline-flex items-center gap-1 text-red-600"><ShieldAlert size={14} /> нет прав</span>}
            </span>
            <span className={isStale(selected) ? 'text-red-600' : 'text-[color:var(--color-text-muted)]'}>
              связь {sinceText(selected.last_seen_at)}
            </span>
            {selected.battery != null && (
              <span className="inline-flex items-center gap-1 text-[color:var(--color-text-muted)]">
                <BatteryMedium size={13} /> {selected.battery}%
              </span>
            )}
            <span className="text-[color:var(--color-text-muted)]">агент {selected.agent_version || '—'}</span>
            <span className={selected.applied_policy_version === selected.policy_version
              ? 'text-[color:var(--color-text-muted)]' : 'text-amber-600'}>
              {selected.applied_policy_version === selected.policy_version
                ? 'политика применена' : 'политика ждёт применения'}
            </span>
          </div>

          {selected.last_error && (
            <p className="text-sm text-red-600">Телефон сообщает об ошибке: {selected.last_error}</p>
          )}

          {/* Вкладки */}
          <nav className="flex gap-1.5 bg-[color:var(--color-bg-subtle)] rounded-xl p-1.5 overflow-x-auto">
            {[
              { id: 'overview', label: 'Обзор', Icon: Gauge },
              { id: 'policy', label: 'Запреты', Icon: ShieldBan },
              { id: 'apps', label: 'Приложения', Icon: AppWindow },
              { id: 'kiosk', label: 'Киоск', Icon: MonitorSmartphone },
              { id: 'history', label: 'История', Icon: HistoryIcon },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setDeviceTab(tab.id)}
                className={`px-3.5 py-2 rounded-lg text-sm font-medium transition-colors inline-flex items-center gap-1.5 whitespace-nowrap shrink-0 ${
                  deviceTab === tab.id
                    ? 'bg-[color:var(--color-primary)] text-white'
                    : 'text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-surface)]'
                }`}
              >
                <tab.Icon size={14} /> {tab.label}
              </button>
            ))}
          </nav>

          {/* ── Обзор ── */}
          {deviceTab === 'overview' && (
            <div className="flex flex-col gap-5">
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
                  <dt className="text-xs text-[color:var(--color-text-muted)]">Модель</dt>
                  <dd>{[selected.manufacturer, selected.model].filter(Boolean).join(' ') || '—'}</dd>
                </div>
                <div>
                  <dt className="text-xs text-[color:var(--color-text-muted)]">Android</dt>
                  <dd>{selected.android_version || '—'}</dd>
                </div>
                <div>
                  <dt className="text-xs text-[color:var(--color-text-muted)] flex items-center gap-1">
                    <HardDrive size={12} /> Память
                  </dt>
                  <dd>{`${fmtBytes(selected.storage_free_mb)} свободно из ${fmtBytes(selected.storage_total_mb)}`}</dd>
                </div>
                <div>
                  <dt className="text-xs text-[color:var(--color-text-muted)] flex items-center gap-1">
                    <Cpu size={12} /> ОЗУ
                  </dt>
                  <dd>{fmtBytes(selected.ram_total_mb)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-[color:var(--color-text-muted)] flex items-center gap-1">
                    <Wifi size={12} /> Сеть
                  </dt>
                  <dd>
                    {selected.network === 'wifi'
                      ? (selected.wifi_ssid || 'Wi-Fi')
                      : selected.network === 'mobile' ? 'Моб. интернет'
                      : selected.network === 'none' ? 'Нет сети' : (selected.network || '—')}
                    {selected.ip_address && (
                      <span className="text-xs text-[color:var(--color-text-muted)]"> · {selected.ip_address}</span>
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-[color:var(--color-text-muted)] flex items-center gap-1">
                    <Clock size={12} /> Аптайм
                  </dt>
                  <dd>{fmtUptime(selected.uptime_seconds)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-[color:var(--color-text-muted)]">Экран защищён</dt>
                  <dd className={selected.secure_lock === false ? 'text-amber-600' : ''}>
                    {selected.secure_lock == null ? '—' : selected.secure_lock ? 'да' : 'нет пароля'}
                  </dd>
                </div>
                {/* Готовность к удалённой разблокировке — знание на будущее:
                    выдать токен задним числом нельзя, а выяснять это в момент,
                    когда сотрудник забыл код, уже поздно. */}
                <div>
                  <dt className="text-xs text-[color:var(--color-text-muted)]">Разблокировка удалённо</dt>
                  <dd className={selected.can_reset_password === false ? 'text-amber-600' : ''}>
                    {selected.can_reset_password == null
                      ? '—'
                      : selected.can_reset_password
                        ? 'доступна'
                        : 'нет — разблокируйте телефон один раз вручную'}
                  </dd>
                </div>
                {selected.serial_number && (
                  <div>
                    <dt className="text-xs text-[color:var(--color-text-muted)]">Серийный номер</dt>
                    <dd className="break-all">{selected.serial_number}</dd>
                  </div>
                )}
                {selected.imei && (
                  <div>
                    <dt className="text-xs text-[color:var(--color-text-muted)]">IMEI</dt>
                    <dd className="break-all">{selected.imei}</dd>
                  </div>
                )}
                {selected.sim_operator && (
                  <div>
                    <dt className="text-xs text-[color:var(--color-text-muted)]">Оператор</dt>
                    <dd>{selected.sim_operator}</dd>
                  </div>
                )}
              </dl>

              {selected.play_protect && (
                <div className="text-sm text-amber-600 flex flex-col gap-1 bg-[color:var(--color-bg-subtle)] rounded-lg p-3">
                  <span>
                    Включена Play Защита — она отклоняет установку наших приложений,
                    и команда «поставить» будет падать с ошибкой проверки.
                  </span>
                  <span className="text-xs text-[color:var(--color-text-muted)]">
                    Выключить можно только на телефоне: Play Маркет → значок профиля →
                    Play Защита → шестерёнка → «Сканировать приложения».
                  </span>
                </div>
              )}

              {/* Геолокация */}
              <div>
                <h2 className="font-medium mb-2 flex items-center gap-1.5"><MapPin size={15} /> Где телефон</h2>
                {selected.location_at ? (
                  <p className="text-sm flex flex-wrap items-center gap-1.5">
                    <a
                      className="underline"
                      href={`https://yandex.ru/maps/?pt=${selected.longitude},${selected.latitude}&z=17&l=map`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {selected.latitude?.toFixed(5)}, {selected.longitude?.toFixed(5)}
                    </a>
                    <span className="text-[color:var(--color-text-muted)]">
                      снято {fmtDateTime(selected.location_at)}
                    </span>
                  </p>
                ) : (
                  <p className="text-sm text-[color:var(--color-text-muted)]">Координаты ещё не запрашивались.</p>
                )}
                <button type="button" className="btn btn--secondary btn--sm mt-2 flex items-center gap-1.5"
                  disabled={busy} onClick={() => sendCommand('locate')}>
                  <MapPin size={14} /> Запросить координаты
                </button>
              </div>

              {/* Камера */}
              <div>
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <h2 className="font-medium flex items-center gap-1.5"><CameraIcon size={15} /> Камера</h2>
                  <span className="grow" />
                  <button type="button" className="btn btn--secondary btn--sm" disabled={busy}
                    onClick={() => sendCommand('camera', { lens: 'back' })}>
                    Снять заднюю
                  </button>
                  <button type="button" className="btn btn--secondary btn--sm" disabled={busy}
                    onClick={() => sendCommand('camera', { lens: 'front' })}>
                    Снять переднюю
                  </button>
                </div>
                {selected.snapshots?.length > 0 ? (
                  <div className="grid grid-cols-2 sm:flex sm:flex-wrap gap-3">
                    {[...selected.snapshots].reverse().map((snap) => (
                      <SnapshotThumb key={snap.id} snap={snap} />
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-[color:var(--color-text-muted)]">Снимков пока нет.</p>
                )}
              </div>

              {/* Быстрые команды */}
              <div>
                <h2 className="font-medium mb-2">Действия</h2>
                <div className="flex flex-wrap gap-2">
                  <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                    onClick={() => sendCommand('lock')}>
                    <Lock size={14} /> Заблокировать экран
                  </button>
                  {/* Пара к «Заблокировать»: телефон лежит с погашенным экраном,
                      кнопка зажигает его и показывает рабочий стол. Если на
                      телефоне стоит код, покажется запрос кода — обойти его
                      было бы то же, что сделать код бесполезным. */}
                  <button type="button" className="btn btn--secondary flex items-center gap-1.5" disabled={busy}
                    onClick={() => sendCommand('wake', { seconds: 60, show_home: true })}
                    title={selected.secure_lock
                      ? 'Экран загорится; код на телефоне придётся ввести вручную'
                      : 'Экран загорится и покажет рабочий стол'}>
                    <Sun size={14} /> Разбудить экран
                  </button>
                  <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                    onClick={() => sendCommand('reboot')}>
                    <RotateCw size={14} /> Перезагрузить
                  </button>
                  {/* Обратное к «Заблокировать»: сменить код или снять его.
                      Доступность зависит от токена сброса, поэтому кнопка
                      гаснет, а рядом объясняется почему. */}
                  <button type="button" className="btn btn--secondary flex items-center gap-1.5"
                    disabled={busy || selected.can_reset_password === false}
                    title={selected.can_reset_password === false
                      ? 'Телефон ещё не разблокировали вручную после установки агента'
                      : 'Поставить новый код или снять блокировку'}
                    onClick={setScreenPassword}>
                    <KeyRound size={14} /> Код разблокировки
                  </button>
                  <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                    onClick={ringPhone}>
                    <Volume2 size={14} /> Звук поиска
                  </button>
                  <button type="button" className="btn btn--secondary flex items-center gap-1.5" disabled={busy}
                    onClick={stopRing}>
                    <VolumeX size={14} /> Выключить сигнал
                  </button>
                  <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                    onClick={setLockMessage}>
                    <MessageSquareWarning size={14} /> Надпись под замком
                  </button>
                  <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                    onClick={showAlert}>
                    <MonitorSmartphone size={14} /> Сообщение на весь экран
                  </button>
                  <button type="button" className="btn btn--secondary flex items-center gap-1.5" disabled={busy}
                    onClick={stopAlert}>
                    <MonitorSmartphone size={14} /> Убрать окно
                  </button>
                  <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                    onClick={setVolume}>
                    <Volume2 size={14} /> Громкость
                  </button>
                  <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                    onClick={launchApp}>
                    <Play size={14} /> Открыть приложение
                  </button>
                  <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                    onClick={() => grantPermission(true)}>
                    <KeyIcon size={14} /> Выдать разрешение
                  </button>
                  <button type="button" className="btn btn--secondary flex items-center gap-1.5" disabled={busy}
                    onClick={() => grantPermission(false)}>
                    <KeyIcon size={14} /> Отозвать разрешение
                  </button>
                  <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                    onClick={addWifi}>
                    <Wifi size={14} /> Прописать Wi-Fi
                  </button>
                  <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                    onClick={syncTime}>
                    <Clock size={14} /> Синхронизировать время
                  </button>
                  <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                    onClick={() => toggleStayAwake(true)}>
                    <Sun size={14} /> Не гасить при зарядке
                  </button>
                  <button type="button" className="btn btn--secondary flex items-center gap-1.5" disabled={busy}
                    onClick={() => toggleStayAwake(false)}>
                    <Moon size={14} /> Гасить как обычно
                  </button>
                  <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                    onClick={() => toggleStatusBar(true)}>
                    <Radio size={14} /> Скрыть строку состояния
                  </button>
                  <button type="button" className="btn btn--secondary flex items-center gap-1.5" disabled={busy}
                    onClick={() => toggleStatusBar(false)}>
                    <Radio size={14} /> Показать строку состояния
                  </button>
                </div>
                {/* Снять сообщение можно ровно там, где видно, что оно висит:
                    отдельной кнопки в общем ряду для этого мало — она нужна
                    только когда сообщение вообще есть. */}
                {selected.lock_message && (
                  <p className="text-xs text-[color:var(--color-text-muted)] mt-2 flex items-center gap-2 flex-wrap">
                    <span>На экране блокировки: «{selected.lock_message}»</span>
                    <button type="button" className="btn btn--ghost btn--sm" disabled={busy}
                      onClick={clearLockMessage}>
                      Снять сообщение
                    </button>
                  </p>
                )}
                <p className="text-xs text-[color:var(--color-text-muted)] mt-2">
                  Команда уходит на телефон за секунды — он держит открытый запрос к серверу.
                  Если аппарат вне сети, команда ждёт в очереди и уйдёт, как только он вернётся.
                </p>
              </div>
            </div>
          )}

          {/* ── Запреты ── */}
          {deviceTab === 'policy' && (
            <div>
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
          )}

          {/* ── Приложения ── */}
          {deviceTab === 'apps' && (
            <div>
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" className="btn btn--secondary btn--sm flex items-center gap-1.5"
                    disabled={busy} onClick={installApk}>
                    <Download size={14} /> Поставить по ссылке
                  </button>
                  <button type="button" className="btn btn--ghost btn--sm flex items-center gap-1.5"
                    disabled={busy} onClick={uninstallApp}>
                    <Trash2 size={14} /> Удалить по имени пакета
                  </button>
                </div>
                <div className="flex items-center gap-2 w-full sm:w-auto">
                  <input
                    className="input flex-1 sm:w-48"
                    placeholder="Найти приложение"
                    value={appFilter}
                    onChange={(e) => setAppFilter(e.target.value)}
                  />
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm flex items-center gap-1.5"
                    disabled={busy}
                    onClick={() => sendCommand('refresh_apps')}
                  >
                    <ListRestart size={14} /> Обновить
                  </button>
                </div>
              </div>

              {selected.apps?.length ? (
                <>
                  <div className="flex flex-wrap items-center gap-3 mb-2">
                    <span className="text-sm font-medium">
                      {`Можно удалить · ${removableApps.length}`}
                    </span>
                    {removableApps.length > 0 && (
                      <button type="button" className="btn btn--ghost btn--sm" onClick={toggleAllApps}>
                        {selectedApps.size === removableApps.length ? 'Снять выделение' : 'Выделить все'}
                      </button>
                    )}
                    {selectedApps.size > 0 && (
                      <button type="button" className="btn btn--danger btn--sm" disabled={busy}
                        onClick={uninstallSelected}>
                        {`Удалить выбранные (${selectedApps.size})`}
                      </button>
                    )}
                  </div>

                  <div className="flex flex-col divide-y divide-[color:var(--color-border)] max-h-96 overflow-y-auto">
                    {removableApps.map((app) => (
                      <label key={app.package} className="flex items-center gap-3 py-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selectedApps.has(app.package)}
                          onChange={() => toggleApp(app.package)}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate">
                            {app.label || app.package}
                            {!app.enabled && (
                              <span className="text-xs text-[color:var(--color-text-muted)]"> · отключено</span>
                            )}
                          </span>
                          <span className="block text-xs text-[color:var(--color-text-muted)] truncate">
                            {[app.package, app.version_name].filter(Boolean).join(' · ')}
                          </span>
                        </span>
                        <span className="flex items-center gap-1 shrink-0">
                          {/* Открыть прямо отсюда: имя пакета уже известно —
                              заставлять оператора перепечатывать его в диалог
                              было нечестно. Отключённое не откроется. */}
                          <button
                            type="button"
                            className="btn btn--ghost btn--sm"
                            disabled={busy || !app.enabled}
                            title={app.enabled ? 'Открыть на телефоне' : 'Приложение скрыто — сначала покажите его'}
                            onClick={(e) => {
                              e.preventDefault();
                              sendCommand('launch_app', { package: app.package });
                            }}
                          >
                            <Play size={14} />
                          </button>
                          <button
                            type="button"
                            className="btn btn--ghost btn--sm"
                            disabled={busy}
                            title="Очистить данные приложения"
                            onClick={(e) => {
                              e.preventDefault();
                              if (!window.confirm(`Очистить данные «${app.label || app.package}»? Приложение останется, но сбросится в исходное состояние.`)) return;
                              sendCommand('clear_app_data', { package: app.package });
                            }}
                          >
                            <Eraser size={14} />
                          </button>
                          <button
                            type="button"
                            className="btn btn--ghost btn--sm"
                            disabled={busy}
                            title={app.enabled ? 'Скрыть от сотрудника' : 'Показать снова'}
                            onClick={(e) => {
                              e.preventDefault();
                              sendCommand('set_app_enabled', { package: app.package, enabled: !app.enabled });
                            }}
                          >
                            <EyeOff size={14} />
                          </button>
                          <button
                            type="button"
                            className="btn btn--ghost btn--sm"
                            disabled={busy}
                            onClick={(e) => {
                              e.preventDefault();
                              if (!window.confirm(`Удалить «${app.label || app.package}» с телефона?`)) return;
                              sendCommand('uninstall', { package: app.package });
                            }}
                          >
                            Удалить
                          </button>
                        </span>
                      </label>
                    ))}
                    {removableApps.length === 0 && (
                      <span className="text-sm text-[color:var(--color-text-muted)] py-2">
                        {appFilter ? 'Ничего не найдено' : 'Нечего удалять'}
                      </span>
                    )}
                  </div>

                  <button
                    type="button"
                    className="btn btn--ghost btn--sm mt-3"
                    onClick={() => setShowSystemApps((v) => !v)}
                  >
                    {`${showSystemApps ? 'Скрыть' : 'Показать'} системные · ${systemApps.length}`}
                  </button>

                  {showSystemApps && (
                    <div className="flex flex-col divide-y divide-[color:var(--color-border)] max-h-72 overflow-y-auto mt-2">
                      {systemApps.map((app) => (
                        <span key={app.package} className="py-2 min-w-0 flex items-center gap-2">
                          <span className="min-w-0 grow">
                            <span className="block truncate text-sm">{app.label || app.package}</span>
                            <span className="block text-xs text-[color:var(--color-text-muted)] truncate">
                              {[app.package, app.version_name].filter(Boolean).join(' · ')}
                            </span>
                          </span>
                          {/* Удалить системное нельзя, а открыть — можно и
                              бывает нужно: те же «Настройки» на телефоне,
                              который стоит в другом салоне. */}
                          <button
                            type="button"
                            className="btn btn--ghost btn--sm shrink-0"
                            disabled={busy}
                            title="Открыть на телефоне"
                            onClick={() => sendCommand('launch_app', { package: app.package })}
                          >
                            <Play size={14} />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}

                  <p className="text-xs text-[color:var(--color-text-muted)] mt-3">
                    {`Список от ${fmtDateTime(selected.apps_updated_at)}. Системные приложения удалить `
                     + 'нельзя — показаны только те, что сотрудник видит в меню.'}
                  </p>
                </>
              ) : (
                <p className="text-sm text-[color:var(--color-text-muted)]">
                  Телефон ещё не присылал список. Он приедет с ближайшим чек-ином.
                </p>
              )}
            </div>
          )}

          {/* ── Киоск ── */}
          {deviceTab === 'kiosk' && kioskDraft && (
            <div className="flex flex-col gap-4">
              <p className="text-sm text-[color:var(--color-text-muted)]">
                Киоск превращает телефон в терминал одного приложения: выбранное
                приложение становится домашним экраном и залипает на нём, выйти в
                настройки или другие программы нельзя.
              </p>

              <label className="flex items-center gap-2 text-sm font-medium">
                <input
                  type="checkbox"
                  checked={!!kioskDraft.enabled}
                  onChange={() => setKioskDraft((k) => ({ ...k, enabled: !k.enabled }))}
                />
                Включить киоск
              </label>

              <div>
                <label className="block text-xs text-[color:var(--color-text-muted)] mb-1">
                  Приложение киоска
                </label>
                <select
                  className="input w-full"
                  value={kioskDraft.home || ''}
                  onChange={(e) => setKioskDraft((k) => ({ ...k, home: e.target.value || null }))}
                >
                  <option value="">Не выбрано</option>
                  {(selected.apps || [])
                    .filter((a) => !a.system || a.enabled)
                    .sort((a, b) => (a.label || a.package).localeCompare(b.label || b.package, 'ru'))
                    .map((a) => (
                      <option key={a.package} value={a.package}>
                        {(a.label || a.package)} — {a.package}
                      </option>
                    ))}
                </select>
                <p className="text-xs text-[color:var(--color-text-muted)] mt-1">
                  Если приложения нет в списке — сначала поставьте его и обновите список на вкладке «Приложения».
                </p>
              </div>

              <div>
                <span className="block text-xs text-[color:var(--color-text-muted)] mb-1">
                  Что оставить доступным в киоске
                </span>
                <div className="grid sm:grid-cols-2 gap-2">
                  {[
                    { id: 'allow_home_button', label: 'Кнопка «Домой»' },
                    { id: 'allow_recents', label: 'Недавние приложения' },
                    { id: 'allow_notifications', label: 'Уведомления' },
                    { id: 'allow_system_info', label: 'Строка состояния (часы, батарея)' },
                  ].map(({ id, label }) => (
                    <label key={id} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={!!kioskDraft[id]}
                        onChange={() => setKioskDraft((k) => ({ ...k, [id]: !k[id] }))}
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn btn--primary" disabled={busy} onClick={saveKiosk}>
                  Сохранить киоск
                </button>
                <button type="button" className="btn btn--secondary flex items-center gap-1.5"
                  disabled={busy} onClick={() => sendCommand('kiosk_exit')}>
                  <MonitorSmartphone size={14} /> Аварийно выйти из киоска
                </button>
              </div>
              <p className="text-xs text-[color:var(--color-text-muted)]">
                Если что-то пошло не так и телефон завис в приложении — «аварийно выйти»
                снимет киоск на ближайшей связи.
              </p>
            </div>
          )}

          {/* ── История ── */}
          {deviceTab === 'history' && (
            selected.commands?.length > 0 ? (
              <div className="flex flex-col gap-1 text-sm">
                {[...selected.commands].reverse().map((c) => (
                  <div key={c.id} className="flex flex-wrap gap-2 items-baseline py-1 border-b border-[color:var(--color-border)] last:border-0">
                    <span className="text-[color:var(--color-text-muted)] text-xs w-32 shrink-0">
                      {fmtDateTime(c.created_at)}
                    </span>
                    <span className="font-medium">{c.type}</span>
                    <span className={c.status === 'failed' ? 'text-red-600'
                      : c.status === 'done' || c.status === 'canceled' ? 'text-[color:var(--color-text-muted)]'
                      : 'text-amber-600'}>
                      {CMD_STATUS[c.status] || c.status}
                    </span>
                    {c.result && (
                      <span className="text-[color:var(--color-text-muted)] text-xs break-all">{c.result}</span>
                    )}
                    {/* Отменить можно только то, что телефон ещё не забрал.
                        С длинным опросом это секунды, но именно в них и стоит
                        успеть, если нажали wipe не на том аппарате. */}
                    {c.status === 'pending' && (
                      <button type="button" className="btn btn--ghost btn--sm ml-auto"
                        disabled={busy} onClick={() => cancelCommand(c.id)}>
                        Отменить
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[color:var(--color-text-muted)]">Команд ещё не было.</p>
            )
          )}

          <div className="border-t border-[color:var(--color-border)] pt-3 flex flex-wrap items-center gap-2">
            <button type="button" className="btn btn--danger flex items-center gap-1.5"
              disabled={busy} onClick={lostMode}>
              <Siren size={14} /> Режим пропажи
            </button>
            <button type="button" className="btn btn--secondary flex items-center gap-1.5"
              disabled={busy} onClick={foundMode}>
              <BellOff size={14} /> Отбой — нашёлся
            </button>
            <span className="text-xs text-[color:var(--color-text-muted)] basis-full">
              Пропажа: заблокировать + сообщение + сигнал + локация + снимок, одной кнопкой.
              Отбой выключает сигнал и снимает сообщение; блокировка экрана остаётся —
              она снимается обычным PIN-ом.
            </span>
          </div>

          {/* Опасная зона — всегда под вкладками, отделена */}
          <div className="border-t border-[color:var(--color-danger)] pt-3 flex flex-wrap items-center gap-2 mt-1">
            <span className="text-xs text-[color:var(--color-text-muted)] w-full">Необратимые действия</span>
            <button type="button" className="btn btn--secondary btn--sm flex items-center gap-1.5"
              disabled={busy} onClick={releaseOwner}>
              <Unlink size={14} /> Снять управление
            </button>
            <button type="button" className="btn btn--danger btn--sm flex items-center gap-1.5"
              disabled={busy} onClick={wipeDevice}>
              <Trash2 size={14} /> Стереть телефон
            </button>
            <button type="button" className="btn btn--ghost btn--sm flex items-center gap-1.5"
              disabled={busy} onClick={forgetDevice}>
              <Trash2 size={14} /> Убрать из списка
            </button>
          </div>
        </section>
      )}

    </div>
  );
}
