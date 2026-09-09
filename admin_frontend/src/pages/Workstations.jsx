import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Monitor, RefreshCw, HardDrive, Cpu, Clock, Power, Lock, LogOut,
  MessageSquareWarning, RotateCw, Play, Eraser, Trash2, Ban, User,
} from 'lucide-react';
import api from '../api.js';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { useToast } from '../providers/ToastProvider.jsx';

/** Компьютер молчит дольше этого — считаем офлайн.
 *
 *  Втрое больше интервала отчёта (5 минут): один пропущенный отчёт из-за
 *  моргнувшей сети не должен красить рабочую машину в «офлайн», иначе на
 *  индикатор перестанут смотреть. */
const OFFLINE_AFTER_MS = 15 * 60 * 1000;

/** Порог тревоги по месту. Совпадает с сервером (LOW_DISK_PERCENT): при
 *  переполнении встаёт Firebird, а вместе с ним продажи салона. */
const LOW_DISK_PERCENT = 10;
const LOW_DISK_GB = 5;

/** Как часто перечитывать список. Показатели меняются раз в пять минут, но
 *  после отправленной команды результат хочется видеть сразу. */
const REFRESH_MS = 10000;

const STATUS_LABELS = {
  pending: 'ждёт',
  sent: 'на компьютере',
  done: 'выполнено',
  failed: 'сбой',
  canceled: 'отменено',
};

function fmtUptime(seconds) {
  if (!seconds && seconds !== 0) return '—';
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  if (days) return `${days} д ${hours} ч`;
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours ? `${hours} ч ${minutes} мин` : `${minutes} мин`;
}

function fmtSeen(iso) {
  if (!iso) return 'ни разу';
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60000) return 'только что';
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  return `${Math.floor(hours / 24)} д назад`;
}

function isOnline(ws) {
  if (!ws.last_seen_at) return false;
  return Date.now() - new Date(ws.last_seen_at).getTime() < OFFLINE_AFTER_MS;
}

function diskTrouble(disk) {
  return disk.free_percent < LOW_DISK_PERCENT || disk.free_gb < LOW_DISK_GB;
}

/** Что не так с машиной. Повторяет правила сервера, чтобы список и карточка
 *  говорили одно и то же. */
function problems(ws) {
  const found = [];
  if (!isOnline(ws)) found.push('нет связи');
  for (const disk of ws.disks || []) {
    if (diskTrouble(disk)) {
      found.push(`мало места на ${disk.mount} (${disk.free_gb} ГБ)`);
    }
  }
  for (const [name, running] of Object.entries(ws.processes || {})) {
    if (running === false) found.push(`не запущен ${name}`);
  }
  if (ws.pending_reboot) found.push('ждёт перезагрузки');
  if (ws.last_error) found.push(ws.last_error);
  return found;
}

export default function Workstations() {
  const { toast } = useToast();
  const [items, setItems] = useState([]);
  const [allowedApps, setAllowedApps] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const timer = useRef(null);

  const selected = useMemo(
    () => items.find((w) => w.id === selectedId) || null,
    [items, selectedId],
  );

  async function load({ quiet = false } = {}) {
    if (!quiet) setLoading(true);
    try {
      const [list, apps] = await Promise.all([
        api.get('workstations'),
        api.get('workstations/allowed-apps'),
      ]);
      setItems(list.data || []);
      setAllowedApps(apps.data || []);
    } catch (err) {
      if (!quiet) toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      if (!quiet) setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // Тихое обновление: без индикатора загрузки и без тостов на ошибке —
    // моргнувшая сеть не должна дёргать оператора, который просто смотрит.
    timer.current = setInterval(() => load({ quiet: true }), REFRESH_MS);
    return () => clearInterval(timer.current);
  }, []);

  async function send(type, params = {}, confirmText) {
    if (!selected) return;
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true);
    try {
      await api.post(`workstations/${selected.id}/commands`, { type, params });
      toast('Команда поставлена в очередь', 'success');
      await load({ quiet: true });
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast(
        detail === 'app_not_allowed'
          ? 'Эта программа не разрешена: добавьте её в WORKSTATION_ALLOWED_APPS на сервере и в agent.ini машины'
          : detail || err.message,
        'error',
      );
    } finally {
      setBusy(false);
    }
  }

  async function cancelCommand(commandId) {
    setBusy(true);
    try {
      await api.delete(`workstations/${selected.id}/commands/${commandId}`);
      toast('Команда снята с очереди', 'success');
    } catch (err) {
      const detail = err.response?.data?.detail;
      // Гонка штатная: компьютер мог забрать команду за те секунды, пока
      // оператор целился в кнопку.
      toast(detail === 'command_not_cancelable'
        ? 'Поздно: компьютер уже забрал команду'
        : detail || err.message, 'error');
    } finally {
      await load({ quiet: true });
      setBusy(false);
    }
  }

  function showMessage() {
    const text = window.prompt('Текст сообщения на экран компьютера:');
    if (text === null) return;
    if (!text.trim()) {
      toast('Пустое сообщение показывать нечего', 'error');
      return;
    }
    send('message', { text: text.trim(), title: 'BONJOUR' });
  }

  function powerOff(type) {
    const raw = window.prompt(
      'Через сколько секунд? Отсрочка нужна, чтобы за кассой успели закрыть смену:',
      '60',
    );
    if (raw === null) return;
    const delay = Number(raw);
    if (!Number.isFinite(delay) || delay < 0) {
      toast('Нужно число секунд', 'error');
      return;
    }
    send(type, { delay_seconds: delay },
      type === 'reboot'
        ? `Перезагрузить «${selected.name || selected.hostname}» через ${delay} с?`
        : `Выключить «${selected.name || selected.hostname}» через ${delay} с?`);
  }

  async function rename() {
    const name = window.prompt('Название компьютера в панели:', selected.name || '');
    if (name === null) return;
    setBusy(true);
    try {
      await api.patch(`workstations/${selected.id}`, { name: name.trim() });
      await load({ quiet: true });
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function forget() {
    if (!window.confirm(
      `Убрать «${selected.name || selected.hostname}» из панели?\n\n`
      + 'Агент на компьютере продолжит работать и зарегистрируется заново — '
      + 'чтобы он замолчал, его нужно остановить на самой машине.',
    )) return;
    setBusy(true);
    try {
      await api.delete(`workstations/${selected.id}`);
      setSelectedId(null);
      await load({ quiet: true });
    } catch (err) {
      toast(err.response?.data?.detail || err.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  const columns = [
    {
      label: 'Компьютер',
      render: (w) => (
        <span className="min-w-0">
          <span className="block truncate font-medium">{w.name || w.hostname || w.id}</span>
          <span className="block text-xs text-[color:var(--color-text-muted)] truncate">
            {[w.hostname, w.ip_address].filter(Boolean).join(' · ')}
          </span>
        </span>
      ),
    },
    {
      label: 'Связь',
      render: (w) => (
        <span className={isOnline(w) ? '' : 'text-red-600'}>
          {isOnline(w) ? 'на связи' : 'нет связи'}
          <span className="block text-xs text-[color:var(--color-text-muted)]">
            {fmtSeen(w.last_seen_at)}
          </span>
        </span>
      ),
    },
    {
      label: 'Диски',
      render: (w) => (
        <span className="text-xs">
          {(w.disks || []).length === 0 ? '—' : (w.disks || []).map((d) => (
            <span key={d.mount} className={`block ${diskTrouble(d) ? 'text-amber-600' : ''}`}>
              {d.mount} {d.free_gb} ГБ ({d.free_percent}%)
            </span>
          ))}
        </span>
      ),
    },
    {
      label: 'Нагрузка',
      render: (w) => (
        <span className="text-xs">
          <span className="block">ЦП {w.cpu_percent ?? '—'}%</span>
          <span className="block">ОЗУ {w.ram_used_percent ?? '—'}%</span>
        </span>
      ),
    },
    {
      label: 'Замечания',
      render: (w) => {
        const found = problems(w);
        if (!found.length) return <span className="text-xs text-[color:var(--color-text-muted)]">нет</span>;
        return <span className="text-xs text-amber-600">{found.join('; ')}</span>;
      },
    },
    {
      label: '',
      isAction: true,
      render: (w) => (
        <button
          type="button"
          className="btn btn--secondary btn--sm"
          onClick={() => setSelectedId(w.id === selectedId ? null : w.id)}
        >
          {w.id === selectedId ? 'Свернуть' : 'Управление'}
        </button>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Monitor size={20} /> Компьютеры салонов
        </h1>
        <button type="button" className="btn flex items-center gap-1.5"
          onClick={() => load()} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Обновить
        </button>
      </div>

      <ResponsiveTable
        columns={columns}
        data={items}
        keyFn={(w) => w.id}
        loading={loading}
        emptyText="Ни один компьютер ещё не зарегистрирован"
        emptyHint="Поставьте агент на салонный ПК — см. device/pc_agent/README.md"
        rowState={(w) => (w.id === selectedId ? 'selected' : (problems(w).length ? 'warning' : null))}
        updatedKey={(w) => w.last_seen_at}
      />

      {selected && (
        <section className="bg-[color:var(--color-bg-secondary)] rounded-xl p-4 flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-medium">{selected.name || selected.hostname}</h2>
            <button type="button" className="btn btn--ghost btn--sm" disabled={busy} onClick={rename}>
              Переименовать
            </button>
          </div>

          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div>
              <dt className="text-xs text-[color:var(--color-text-muted)]">Система</dt>
              <dd className="break-words">{selected.os_version || '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-[color:var(--color-text-muted)] flex items-center gap-1">
                <Clock size={12} /> Аптайм
              </dt>
              <dd>{fmtUptime(selected.uptime_seconds)}</dd>
            </div>
            <div>
              <dt className="text-xs text-[color:var(--color-text-muted)] flex items-center gap-1">
                <Cpu size={12} /> ОЗУ
              </dt>
              <dd>{selected.ram_total_mb ? `${Math.round(selected.ram_total_mb / 1024)} ГБ` : '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-[color:var(--color-text-muted)] flex items-center gap-1">
                <User size={12} /> В системе
              </dt>
              <dd>{selected.logged_user || '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-[color:var(--color-text-muted)]">Агент</dt>
              <dd>{selected.agent_version || '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-[color:var(--color-text-muted)]">Перезагрузка</dt>
              <dd className={selected.pending_reboot ? 'text-amber-600' : ''}>
                {selected.pending_reboot == null ? '—' : selected.pending_reboot ? 'требуется' : 'не нужна'}
              </dd>
            </div>
          </dl>

          <div>
            <h3 className="text-sm font-medium mb-2 flex items-center gap-1.5">
              <HardDrive size={14} /> Диски
            </h3>
            <div className="flex flex-wrap gap-3 text-sm">
              {(selected.disks || []).map((d) => (
                <span key={d.mount} className={diskTrouble(d) ? 'text-amber-600' : ''}>
                  {d.mount} — {d.free_gb} из {d.total_gb} ГБ свободно ({d.free_percent}%)
                </span>
              ))}
              {!(selected.disks || []).length && (
                <span className="text-[color:var(--color-text-muted)]">нет данных</span>
              )}
            </div>
          </div>

          {Object.keys(selected.processes || {}).length > 0 && (
            <div>
              <h3 className="text-sm font-medium mb-2">Программы</h3>
              <div className="flex flex-wrap gap-3 text-sm">
                {Object.entries(selected.processes).map(([name, running]) => (
                  <span key={name} className={running ? '' : 'text-red-600'}>
                    {name}: {running ? 'запущена' : 'не запущена'}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div>
            <h3 className="text-sm font-medium mb-2">Действия</h3>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                onClick={showMessage}>
                <MessageSquareWarning size={14} /> Сообщение на экран
              </button>
              <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                onClick={() => send('lock')}>
                <Lock size={14} /> Заблокировать экран
              </button>
              <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                onClick={() => send('collect_now')}>
                <RefreshCw size={14} /> Обновить показатели
              </button>
              <button type="button" className="btn flex items-center gap-1.5" disabled={busy}
                onClick={() => send('cleanup_temp', {}, 'Очистить временные файлы на этом компьютере?')}>
                <Eraser size={14} /> Очистить временные файлы
              </button>
              <button type="button" className="btn btn--secondary flex items-center gap-1.5" disabled={busy}
                onClick={() => send('logoff', {}, 'Завершить сеанс пользователя? Несохранённое будет потеряно.')}>
                <LogOut size={14} /> Завершить сеанс
              </button>
            </div>
          </div>

          {allowedApps.length > 0 && (
            <div>
              <h3 className="text-sm font-medium mb-2">Программы из белого списка</h3>
              <div className="flex flex-wrap gap-2">
                {allowedApps.map((app) => (
                  <span key={app} className="flex gap-1">
                    <button type="button" className="btn btn--secondary btn--sm flex items-center gap-1.5"
                      disabled={busy} onClick={() => send('run_app', { app })}>
                      <Play size={14} /> {app}
                    </button>
                    <button type="button" className="btn btn--ghost btn--sm" disabled={busy}
                      title="Перезапустить"
                      onClick={() => send('restart_process', { app },
                        `Перезапустить «${app}»? Несохранённое в ней будет потеряно.`)}>
                      <RotateCw size={14} />
                    </button>
                  </span>
                ))}
              </div>
              {/* Путь к программе знает только сама машина — см. agent.ini.
                  Сервер хранит имена, чтобы «запустить» не означало «выполнить
                  что угодно» на кассовом компьютере. */}
              <p className="text-xs text-[color:var(--color-text-muted)] mt-2">
                Список задаётся ключом <code>WORKSTATION_ALLOWED_APPS</code> на сервере,
                а путь к программе — в <code>agent.ini</code> самой машины.
              </p>
            </div>
          )}

          <div className="border-t border-[color:var(--color-border)] pt-3">
            <h3 className="text-sm font-medium mb-2">История команд</h3>
            {(selected.commands || []).length === 0 ? (
              <p className="text-sm text-[color:var(--color-text-muted)]">Команд ещё не было.</p>
            ) : (
              <div className="flex flex-col gap-1 text-sm">
                {[...selected.commands].reverse().slice(0, 15).map((c) => (
                  <div key={c.id} className="flex flex-wrap gap-2 items-baseline py-1 border-b border-[color:var(--color-border)] last:border-0">
                    <span className="font-medium">{c.type}</span>
                    <span className={c.status === 'failed' ? 'text-red-600'
                      : c.status === 'done' || c.status === 'canceled'
                        ? 'text-[color:var(--color-text-muted)]' : 'text-amber-600'}>
                      {STATUS_LABELS[c.status] || c.status}
                    </span>
                    {c.result && (
                      <span className="text-xs text-[color:var(--color-text-muted)] break-all">{c.result}</span>
                    )}
                    {/* Отменить можно только то, что компьютер ещё не забрал.
                        Секунды, но именно в них и надо успеть, если перезагрузку
                        отправили не на ту машину. */}
                    {c.status === 'pending' && (
                      <button type="button" className="btn btn--ghost btn--sm ml-auto"
                        disabled={busy} onClick={() => cancelCommand(c.id)}>
                        <Ban size={14} /> Отменить
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="border-t border-[color:var(--color-danger)] pt-3 flex flex-wrap items-center gap-2">
            <span className="text-xs text-[color:var(--color-text-muted)] w-full">
              Выключение и перезагрузка — с отсрочкой, чтобы за кассой успели закрыть смену
            </span>
            <button type="button" className="btn btn--secondary btn--sm flex items-center gap-1.5"
              disabled={busy} onClick={() => powerOff('reboot')}>
              <RotateCw size={14} /> Перезагрузить
            </button>
            <button type="button" className="btn btn--danger btn--sm flex items-center gap-1.5"
              disabled={busy} onClick={() => powerOff('shutdown')}>
              <Power size={14} /> Выключить
            </button>
            <button type="button" className="btn btn--ghost btn--sm flex items-center gap-1.5"
              disabled={busy} onClick={() => send('cancel_shutdown')}>
              <Ban size={14} /> Отменить выключение
            </button>
            <button type="button" className="btn btn--ghost btn--sm flex items-center gap-1.5 ml-auto"
              disabled={busy} onClick={forget}>
              <Trash2 size={14} /> Убрать из панели
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
