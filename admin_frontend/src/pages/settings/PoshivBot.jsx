import { useEffect, useState } from 'react';
import { RefreshCw, Save, Power, AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';
import { Section, Field, StatusDot } from './shared.jsx';

// Бот пошива живёт вне этого репозитория (рабочий стол) и деплоем не
// обновляется. Отсюда мы только читаем его состояние и пишем оверлей
// настроек — сам конфиг бота правится в его config.py.
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
      .map(Number);
    if (ids.some((n) => !Number.isInteger(n) || n <= 0)) {
      toast('ID руководителей — только целые числа через запятую', 'error');
      return;
    }
    setSaving(true);
    try {
      await api.put('poshiv-bot/settings', {
        manager_ids: ids,
        check_time: checkTime,
        masters: Object.fromEntries(
          Object.entries(masters).map(([k, v]) => [k, v === '' ? null : Number(v)]),
        ),
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
          <button className="ui-btn ui-btn--ghost text-sm" onClick={loadHealth}>
            <RefreshCw size={14} /> Обновить
          </button>
          <button
            className="ui-btn ui-btn--ghost text-sm"
            onClick={restart}
            disabled={restarting}
            title="pm2 restart poshiv-bot"
          >
            <Power size={14} className={restarting ? 'animate-pulse' : ''} /> Перезапустить бота
          </button>
          <button
            className="ui-btn ui-btn--ghost text-sm"
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
            className="ui-input w-40"
            value={checkTime}
            onChange={(e) => edit(setCheckTime)(e.target.value)}
          />
        </Field>

        <Field
          label="Telegram ID руководителей"
          hint="Через запятую. Им приходят карточки новых заказов и уведомления мастеров."
        >
          <input
            type="text"
            className="ui-input"
            value={managers}
            onChange={(e) => edit(setManagers)(e.target.value)}
            placeholder="699539809, 5495663985"
          />
        </Field>
      </Section>

      <Section title="Мастера по этапам">
        <p className="text-xs text-[color:var(--color-muted-foreground)]">
          Telegram ID мастера, которому уходит карточка задания при переводе заказа на
          этап. Пустое поле — мастер не назначен: этап продолжает работать, просто без
          уведомления. Неверный ID здесь ломает отправку, поэтому вписывайте только
          подтверждённые.
        </p>
        <div className="space-y-2">
          {stages.map((s) => (
            <div key={s.key} className="flex items-center gap-3">
              <span className="text-sm w-48 shrink-0">{s.label}</span>
              <input
                type="text"
                inputMode="numeric"
                className="ui-input w-56"
                value={masters[s.key] ?? ''}
                onChange={(e) =>
                  edit(setMasters)((m) => ({
                    ...m,
                    [s.key]: e.target.value.replace(/\D/g, ''),
                  }))
                }
                placeholder="не назначен"
              />
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
            <div key={s.key} className="flex items-center gap-3">
              <span className="text-sm w-48 shrink-0">{s.label}</span>
              <span className="text-[color:var(--color-muted-foreground)] text-sm">→</span>
              <select
                className="ui-input w-56"
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
        <button className="ui-btn ui-btn--primary" onClick={save} disabled={saving || !dirty}>
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
