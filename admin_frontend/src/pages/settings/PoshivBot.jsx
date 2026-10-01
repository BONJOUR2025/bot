import { useEffect, useState } from 'react';
import { RefreshCw, Save, Power, AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';
import { Section, Field, StatusDot } from './shared.jsx';

// Бот пошива живёт вне этого репозитория (рабочий стол) и деплоем не
// обновляется. Отсюда мы только читаем его состояние и пишем оверлей
// настроек — сам конфиг бота правится в его config.py.
// Telegram ID → число, username → «@name»; пусто → null, мусор → undefined.
function normPerson(raw) {
  const s = String(raw ?? '').trim();
  if (!s) return null;
  if (/^\d+$/.test(s)) return Number(s);
  const m = s.match(/^@?([A-Za-z0-9_]{4,32})$/);
  return m ? `@${m[1].toLowerCase()}` : undefined;
}

/** Под username — к какому ID бот его привязал, или что человек ему ещё не писал. */
function UsernameStatus({ value, usernames }) {
  const s = String(value ?? '').trim();
  if (!s || /^\d+$/.test(s)) return null;
  const key = `@${s.replace(/^@/, '').toLowerCase()}`;
  if (!(key in (usernames || {}))) {
    return <span className="text-xs text-[color:var(--color-muted-foreground)]">сохраните — бот проверит username</span>;
  }
  const id = usernames[key];
  return id
    ? <span className="text-xs text-[color:var(--color-success)]">{key} → ID {id}</span>
    : <span className="text-xs text-[color:var(--color-warning)]">{key} ещё не писал боту — пусть отправит ему /start</span>;
}

export default function SettingsPoshivBot() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [doc, setDoc] = useState(null);
  const [health, setHealth] = useState(null);
  const [logOpen, setLogOpen] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Редактируемые поля
  const [checkTime, setCheckTime] = useState('');
  const [managers, setManagers] = useState('');
  const [masters, setMasters] = useState({});
  const [stageNext, setStageNext] = useState({});

  useEffect(() => {
    load();
    loadHealth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get('poshiv-bot/settings');
      setDoc(res.data);
      const eff = res.data.effective || {};
      setCheckTime(eff.check_time || '');
      setManagers((eff.manager_ids || []).join(', '));
      setMasters(
        Object.fromEntries(
          (res.data.stages || []).map((s) => [s.key, eff.masters?.[s.key] ?? '']),
        ),
      );
      setStageNext({ ...(eff.stage_next || {}) });
      setDirty(false);
    } catch (err) {
      toast(err?.response?.data?.detail || 'Не удалось загрузить настройки бота', 'error');
    } finally {
      setLoading(false);
    }
  }

  async function loadHealth() {
    try {
      const res = await api.get('poshiv-bot/health');
      setHealth(res.data);
    } catch {
      // Диагностика необязательна — страница не должна падать из-за неё
    }
  }

  async function save() {
    const ids = managers
      .split(/[,\s]+/)
      .filter(Boolean)
      .map(normPerson);
    if (ids.some((v) => v === undefined)) {
      toast('Руководители — Telegram ID или @username через запятую', 'error');
      return;
    }
    const masterVals = Object.entries(masters).map(([k, v]) => [k, v === '' ? null : normPerson(v)]);
    const badMaster = masterVals.find(([, v]) => v === undefined);
    if (badMaster) {
      toast(`Мастер «${badMaster[0]}»: нужен Telegram ID или @username`, 'error');
      return;
    }
    setSaving(true);
    try {
      await api.put('poshiv-bot/settings', {
        manager_ids: ids,
        check_time: checkTime,
        masters: Object.fromEntries(masterVals),
        stage_next: stageNext,
      });
      toast('Сохранено. Изменения применятся после перезапуска бота', 'success');
      setDirty(false);
      await load();
    } catch (err) {
      toast(err?.response?.data?.detail || 'Не удалось сохранить', 'error');
    } finally {
      setSaving(false);
    }
  }

  async function restart() {
    if (!window.confirm('Перезапустить бота пошива (pm2 restart)?')) return;
    setRestarting(true);
    try {
      await api.post('system/process-status/poshiv_bot/restart');
      toast('Бот перезапускается', 'success');
      setTimeout(loadHealth, 4000);
    } catch (err) {
      toast(err?.response?.data?.detail || 'Не удалось перезапустить', 'error');
    } finally {
      setRestarting(false);
    }
  }

  function edit(setter) {
    return (...args) => {
      setDirty(true);
      setter(...args);
    };
  }

  if (loading) {
    return (
      <div className="app-card p-5 flex items-center gap-2 text-sm text-[color:var(--color-muted-foreground)]">
        <RefreshCw size={15} className="animate-spin" /> Загрузка…
      </div>
    );
  }

  const stages = doc?.stages || [];
  const proc = health?.process;
  const token = health?.amo_token;

  return (
    <div className="space-y-5">
      <Section title="Состояние">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex items-center gap-2 text-sm">
            <StatusDot ok={!!proc?.online} loading={!health} />
            <span className="font-medium">Процесс</span>
            <span className="text-[color:var(--color-muted-foreground)]">
              {proc
                ? proc.online
                  ? `работает, pid ${proc.pid ?? '—'}${
                      proc.memory_mb ? `, ${proc.memory_mb} МБ` : ''
                    }`
                  : 'остановлен'
                : '—'}
            </span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <StatusDot ok={!!token?.ok} loading={!health} />
            <span className="font-medium">Токен amoCRM</span>
            <span className="text-[color:var(--color-muted-foreground)]">
              {token
                ? token.ok
                  ? `действует ещё ${token.hours_left} ч`
                  : token.detail || 'недействителен'
                : '—'}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 pt-1">
          <button className="btn btn--secondary btn--sm flex items-center gap-1.5" onClick={loadHealth}>
            <RefreshCw size={14} /> Обновить
          </button>
          <button
            className="btn btn--secondary btn--sm flex items-center gap-1.5"
            onClick={restart}
            disabled={restarting}
            title="pm2 restart poshiv-bot"
          >
            <Power size={14} className={restarting ? 'animate-pulse' : ''} /> Перезапустить бота
          </button>
          <button
            className="btn btn--secondary btn--sm flex items-center gap-1.5"
            onClick={() => setLogOpen((v) => !v)}
          >
            {logOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Лог
          </button>
        </div>

        {logOpen && (
          <pre className="text-[11px] leading-relaxed bg-[color:var(--color-bg-secondary)] rounded-lg p-3 overflow-x-auto max-h-72 overflow-y-auto">
            {(health?.log_tail || []).join('\n') || 'Лог пуст'}
          </pre>
        )}
      </Section>

      <Section title="Основные настройки">
        <Field
          label="Время ежедневной проверки заказов"
          hint="Во сколько бот забирает из Агбиса новые заказы индивидуального пошива."
        >
          <input
            type="time"
            className="input max-w-[10rem]"
            value={checkTime}
            onChange={(e) => edit(setCheckTime)(e.target.value)}
          />
        </Field>

        <Field
          label="Руководители — Telegram ID или @username"
          hint="Через запятую. Им приходят карточки новых заказов и уведомления мастеров. По @username бот узнаёт человека, когда тот ему напишет."
        >
          <input
            type="text"
            className="input"
            value={managers}
            onChange={(e) => edit(setManagers)(e.target.value)}
            placeholder="699539809, @username"
          />
          <div className="mt-1 flex flex-col gap-0.5">
            {managers.split(/[,\s]+/).filter((t) => t && !/^\d+$/.test(t)).map((t) => (
              <UsernameStatus key={t} value={t} usernames={doc?.usernames} />
            ))}
          </div>
        </Field>
      </Section>

      <Section title="Мастера по этапам">
        <p className="text-xs text-[color:var(--color-muted-foreground)]">
          Telegram ID или @username мастера, которому уходит карточка задания при переводе
          заказа на этап. Пустое поле — мастер не назначен: этап продолжает работать, просто
          без уведомления. Мастер, записанный по @username, начинает получать карточки после
          того, как сам напишет боту (/start) — до этого Telegram не даёт боту ему писать.
        </p>
        <div className="space-y-2">
          {stages.map((s) => (
            <div
              key={s.key}
              className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3"
            >
              <span className="text-sm sm:w-48 sm:shrink-0">{s.label}</span>
              <input
                type="text"
                className="input sm:max-w-[14rem]"
                value={masters[s.key] ?? ''}
                onChange={(e) =>
                  edit(setMasters)((m) => ({
                    ...m,
                    [s.key]: e.target.value.replace(/\s/g, ''),
                  }))
                }
                placeholder="ID или @username"
              />
              <UsernameStatus value={masters[s.key]} usernames={doc?.usernames} />
            </div>
          ))}
        </div>
      </Section>

      <Section title="Движение по воронке">
        <p className="text-xs text-[color:var(--color-muted-foreground)]">
          Куда уходит заказ в amoCRM, когда мастер нажимает «Отметить готовность».
          «Дальше вручную» — заказ остаётся на месте, этап меняет руководитель.
        </p>
        <div className="space-y-2">
          {stages.map((s) => (
            <div
              key={s.key}
              className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3"
            >
              <span className="text-sm sm:w-48 sm:shrink-0">{s.label}</span>
              <span className="hidden sm:inline text-[color:var(--color-muted-foreground)] text-sm">
                →
              </span>
              <select
                className="input sm:max-w-[14rem]"
                value={stageNext[s.key] || ''}
                onChange={(e) =>
                  edit(setStageNext)((n) => ({ ...n, [s.key]: e.target.value || null }))
                }
              >
                <option value="">дальше вручную</option>
                {stages
                  .filter((o) => o.key !== s.key)
                  .map((o) => (
                    <option key={o.key} value={o.key}>
                      {o.label}
                    </option>
                  ))}
              </select>
            </div>
          ))}
        </div>
      </Section>

      <div className="flex items-center gap-3">
        <button className="btn btn--primary flex items-center gap-2" onClick={save} disabled={saving || !dirty}>
          <Save size={15} /> Сохранить
        </button>
        {dirty && (
          <span className="text-xs text-[color:var(--color-muted-foreground)] flex items-center gap-1.5">
            <AlertTriangle size={13} /> После сохранения бота нужно перезапустить —
            настройки он читает только при старте
          </span>
        )}
      </div>

      <p className="text-xs text-[color:var(--color-muted-foreground)]">
        Каталог бота: <code>{doc?.bot_dir}</code>. Настройки пишутся в{' '}
        <code>{doc?.settings_file}</code> и накладываются поверх значений из его{' '}
        <code>config.py</code>.
      </p>
    </div>
  );
}
