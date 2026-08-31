/** Режим «Прозвон» — один кандидат на экране.
 *
 * Смысл экрана ровно в том, чего нет: списка. Разбирая канбан, рекрутёр сам
 * решает, кому звонить, — и каждый раз заново вспоминает, кому уже звонили
 * сегодня и кто просил перезвонить в четверг. Здесь этот выбор делает
 * очередь, а человеку остаётся набрать номер и нажать результат.
 *
 * Очередь считается на бэкенде предикатом (app/services/call_queue.py) и
 * нигде не хранится, поэтому после каждого результата экран просто
 * перезапрашивает следующего — своего состояния очереди у него нет.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  Phone, PhoneMissed, PhoneOff, Clock, MessageSquare, X, Check,
  Loader2, Undo2, CalendarClock, RefreshCw, Briefcase,
} from 'lucide-react';
import api from '../api';
import { formatPhone, telHref } from '../utils/phone';
import { useToast } from '../providers/ToastProvider.jsx';

const DEFAULT_NO_ANSWER_MSG =
  'Здравствуйте! Пробовали до вас дозвониться, но не получилось. ' +
  'Подскажите, когда вам удобно поговорить?';

// Подписи причин попадания в очередь. Приходят кодами (call_queue.REASON_*),
// чтобы формулировка жила в одном месте, а не собиралась из полей карточки.
const REASON_LABEL = {
  scheduled: 'Назначенное время наступило',
  never_called: 'Ещё ни разу не звонили',
  retry: 'Повторная попытка — прошлый день закрыт',
};

const OUTCOMES = [
  { key: 'reached',   label: 'Дозвонился',        icon: Check,          tone: 'primary' },
  { key: 'no_answer', label: 'Не дозвонился',     icon: PhoneMissed,    tone: 'default' },
  { key: 'later',     label: 'Перезвонить позже', icon: CalendarClock,  tone: 'default' },
  { key: 'inbound',   label: 'Написал сам',       icon: MessageSquare,  tone: 'default' },
  { key: 'rejected',  label: 'Отказ',             icon: X,              tone: 'danger' },
];

/** Локальное «сейчас» + N часов в формате datetime-local.
 *
 * Именно локальное, без toISOString(): бэкенд трактует next_at как местное
 * время (см. комментарий к next_attempt_at в модели), и UTC-строка сдвинула
 * бы каждый назначенный звонок на три часа.
 */
function localInputValue(date) {
  const pad = n => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatWhen(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

export default function CallQueue() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  // Отдельная форма показывается только для тех исходов, где без неё
  // результат недоопределён: время для «позже», текст для «не дозвонился».
  const [pending, setPending] = useState(null);
  const [lastAction, setLastAction] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/recruitment/call-queue');
      setData(res.data);
      setPending(null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const candidate = data?.next || null;
  const attempts = candidate?.call_attempts || 0;

  async function submit(outcome, extra = {}) {
    if (!candidate) return;
    setBusy(true);
    try {
      const res = await api.post(
        `/recruitment/candidates/${candidate.id}/call-outcome`,
        { outcome, ...extra },
      );
      if (res.data?.warning) toast(res.data.warning, 'warning');
      setLastAction({ id: candidate.id, name: candidate.name, outcome });
      await load();
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    if (!lastAction) return;
    setBusy(true);
    try {
      const res = await api.post(
        `/recruitment/candidates/${lastAction.id}/call-outcome/undo`);
      if (res.data?.message_not_recalled) {
        toast('Результат откачен, но отправленное сообщение уже не вернуть', 'warning');
      } else {
        toast('Результат откачен');
      }
      setLastAction(null);
      await load();
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  function pick(outcome) {
    if (outcome === 'later') {
      const d = new Date();
      d.setDate(d.getDate() + 1);
      d.setHours(11, 0, 0, 0);
      setPending({ outcome, next_at: localInputValue(d) });
      return;
    }
    if (outcome === 'no_answer' && attempts === 0) {
      // Сообщение пишем только после ПЕРВОГО недозвона: второе и третье
      // такое же подряд выглядит как автоответчик.
      setPending({ outcome, send_message: true, text: DEFAULT_NO_ANSWER_MSG });
      return;
    }
    submit(outcome);
  }

  return (
    <div className="p-5 space-y-5">
      <QueueHeader data={data} onRefresh={load} loading={loading} />

      <div className="max-w-3xl space-y-4">
        {error && (
          <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
            {error}
          </div>
        )}

        {lastAction && (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-muted)]/25 px-4 py-2.5 text-sm">
            <span className="text-[color:var(--color-text-muted)]">
              {lastAction.name}: {OUTCOMES.find(o => o.key === lastAction.outcome)?.label.toLowerCase()}
            </span>
            <button onClick={undo} disabled={busy}
                    className="btn btn--ghost btn--sm flex items-center gap-1.5">
              <Undo2 size={14} /> Отменить
            </button>
          </div>
        )}

        {loading && !data && (
          <div className="flex items-center gap-2 text-sm text-[color:var(--color-text-muted)]">
            <Loader2 size={16} className="animate-spin" /> Собираем очередь…
          </div>
        )}

        {!loading && !candidate && <EmptyQueue data={data} />}

        {candidate && (
          <CallCard
            c={candidate}
            busy={busy}
            pending={pending}
            onPick={pick}
            onCancelPending={() => setPending(null)}
            onChangePending={patch => setPending(p => ({ ...p, ...patch }))}
            onConfirmPending={() => {
              const { outcome, ...extra } = pending;
              submit(outcome, extra);
            }}
          />
        )}
      </div>
    </div>
  );
}

// ── шапка со счётчиками ─────────────────────────────────────────────────

function QueueHeader({ data, onRefresh, loading }) {
  const counters = [
    { label: 'в очереди', value: data?.queue_count ?? '—' },
    { label: 'звонков сегодня', value: data?.calls_today ?? '—' },
    { label: 'ждут ответа', value: data?.awaiting_reply_count ?? '—' },
  ];
  return (
    <div className="flex items-end justify-between gap-4 flex-wrap">
      <div>
        <span className="ui-eyebrow mb-3">Режим прозвона</span>
        <h1 className="text-xl font-bold">Кому звонить сейчас</h1>
        <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">
          Один кандидат за раз — очередь выбирает сама
        </p>
      </div>
      <div className="flex items-center gap-5 flex-wrap">
        {counters.map(c => (
          <div key={c.label}>
            <div className="text-xl font-bold tabular-nums leading-none">{c.value}</div>
            <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-text-muted)] mt-1">
              {c.label}
            </div>
          </div>
        ))}
        <button onClick={onRefresh} disabled={loading}
                className="btn btn--ghost btn--sm flex items-center gap-1.5" title="Обновить очередь">
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Обновить
        </button>
      </div>
    </div>
  );
}

// ── пустая очередь ──────────────────────────────────────────────────────

function EmptyQueue({ data }) {
  // Пустая очередь бывает по двум причинам, и они требуют разного: закрытое
  // окно — «вернитесь позже», а разобранная очередь — «на сегодня всё».
  const closed = data && data.within_call_hours === false;
  return (
    <div className="rounded-2xl border border-[color:var(--color-border)] bg-[color:var(--color-surface)] px-6 py-10 text-center">
      <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-[color:var(--color-muted)]/40 mb-4">
        {closed ? <Clock size={22} /> : <Check size={22} />}
      </div>
      <div className="text-base font-semibold">
        {closed ? 'Сейчас не время для звонков' : 'Очередь пуста'}
      </div>
      <p className="text-sm text-[color:var(--color-text-muted)] mt-1.5 max-w-sm mx-auto">
        {closed
          ? (data?.next_window_start
            ? `Звонить можно с ${formatWhen(data.next_window_start)}. Часы звонков настраиваются в разделе «Интеграции».`
            : 'Окно звонков закрыто — проверьте настройки часов звонков.')
          : 'Всех, кому нужен звонок, уже обзвонили. Новые появятся, когда кандидаты пройдут опрос или наступит назначенное время.'}
      </p>
      {!closed && (data?.awaiting_reply_count ?? 0) > 0 && (
        <p className="text-sm text-[color:var(--color-text-muted)] mt-3">
          {data.awaiting_reply_count} кандидат(ов) ждут ответа в переписке — им нужен текст, а не звонок.
        </p>
      )}
    </div>
  );
}

// ── карточка звонка ─────────────────────────────────────────────────────

function CallCard({ c, busy, pending, onPick, onCancelPending, onChangePending, onConfirmPending }) {
  const attempts = c.call_attempts || 0;
  return (
    <div className="rounded-2xl border border-[color:var(--color-border)] bg-[color:var(--color-surface)] overflow-hidden">
      <div className="px-6 pt-5 pb-4 border-b border-[color:var(--color-border)]">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <h2 className="text-lg font-bold leading-tight">{c.name}</h2>
            {c.vacancy_title && (
              <div className="flex items-center gap-1.5 text-sm text-[color:var(--color-text-muted)] mt-1">
                <Briefcase size={13} /> {c.vacancy_title}
              </div>
            )}
          </div>
          <span className="text-xs px-2 py-1 rounded-lg border border-[color:var(--color-border)] bg-[color:var(--color-muted)]/30 text-[color:var(--color-text-muted)]">
            {REASON_LABEL[c.reason] || 'В очереди'}
          </span>
        </div>

        {/* Номер — главное действие экрана, поэтому набран крупно и сам
            является ссылкой: на телефоне это один тап до звонка. */}
        <a href={telHref(c.phone)}
           className="mt-4 inline-flex items-center gap-2.5 text-2xl font-bold tracking-tight hover:text-[color:var(--color-primary)] transition-colors">
          <Phone size={20} /> {formatPhone(c.phone) || c.phone}
        </a>

        <div className="flex flex-wrap items-center gap-2 mt-3">
          {(c.flags || []).map(f => (
            <span key={f.code}
                  className="text-[11px] px-2 py-0.5 rounded-md border border-[color:var(--color-border)] bg-[color:var(--color-muted)]/25">
              {f.label}
            </span>
          ))}
          {!c.has_chat && (
            <span className="text-[11px] px-2 py-0.5 rounded-md border border-amber-200 bg-amber-50 text-amber-800">
              переписки нет — только телефон
            </span>
          )}
        </div>

        {c.linked_task && (
          <div className="mt-3 flex items-center gap-2 text-sm text-[color:var(--color-text-muted)]">
            <CalendarClock size={14} />
            Задача: {c.linked_task.title}
            {c.linked_task.due_date && ` — ${c.linked_task.due_date}`}
            {c.linked_task.due_time && ` ${String(c.linked_task.due_time).slice(0, 5)}`}
          </div>
        )}
      </div>

      {/* Ответы опроса — то, ради чего звонок и делается осмысленным:
          звонить, не зная, что человек уже написал, значит спрашивать
          заново то, на что он ответил. */}
      {!!(c.answers || []).length && (
        <div className="px-6 py-4 border-b border-[color:var(--color-border)] space-y-2.5">
          {c.answers.map((a, i) => (
            <div key={i}>
              <div className="text-xs text-[color:var(--color-text-muted)]">
                {a.question || a.q || `Вопрос ${i + 1}`}
              </div>
              <div className="text-sm">{a.answer || a.a || ''}</div>
            </div>
          ))}
        </div>
      )}

      {attempts > 0 && (
        <div className="px-6 py-2.5 border-b border-[color:var(--color-border)] text-sm text-[color:var(--color-text-muted)] flex items-center gap-1.5">
          <PhoneOff size={14} /> Попыток дозвона: {attempts} из 3
        </div>
      )}

      <div className="px-6 py-4">
        {pending
          ? <PendingForm pending={pending} busy={busy} onChange={onChangePending}
                         onCancel={onCancelPending} onConfirm={onConfirmPending} />
          : (
            <div className="flex flex-wrap gap-2">
              {OUTCOMES.map(o => {
                const Icon = o.icon;
                return (
                  <button
                    key={o.key}
                    onClick={() => onPick(o.key)}
                    disabled={busy}
                    className={`btn btn--sm flex items-center gap-1.5 ${
                      o.tone === 'primary' ? 'btn--primary'
                        : o.tone === 'danger' ? 'btn--ghost text-red-600'
                          : 'btn-secondary'
                    }`}
                  >
                    <Icon size={14} /> {o.label}
                  </button>
                );
              })}
            </div>
          )}
      </div>
    </div>
  );
}

function PendingForm({ pending, busy, onChange, onCancel, onConfirm }) {
  if (pending.outcome === 'later') {
    return (
      <div className="space-y-3">
        <label className="block text-sm font-medium">Когда перезвонить</label>
        <input
          type="datetime-local"
          value={pending.next_at}
          onChange={e => onChange({ next_at: e.target.value })}
          className="input"
          style={{ maxWidth: '16rem' }}
        />
        {/* Правило дня объясняем заранее: иначе выбранное «сегодня в 18:00»
            молча уезжает на завтра, и это выглядит как ошибка. */}
        <p className="text-xs text-[color:var(--color-text-muted)]">
          Если сегодня этому кандидату уже звонили, время перенесётся на
          ближайший следующий день: больше одного звонка в день не делаем.
        </p>
        <div className="flex gap-2">
          <button onClick={onConfirm} disabled={busy || !pending.next_at}
                  className="btn btn--primary btn--sm">Сохранить</button>
          <button onClick={onCancel} disabled={busy}
                  className="btn btn--ghost btn--sm">Отмена</button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={!!pending.send_message}
          onChange={e => onChange({ send_message: e.target.checked })}
        />
        Написать кандидату в переписку
      </label>
      {pending.send_message && (
        <textarea
          value={pending.text}
          onChange={e => onChange({ text: e.target.value })}
          rows={3}
          className="input"
        />
      )}
      <p className="text-xs text-[color:var(--color-text-muted)]">
        Сообщение отправляется только после первого недозвона — дальше звоним молча.
      </p>
      <div className="flex gap-2">
        <button onClick={onConfirm} disabled={busy}
                className="btn btn--primary btn--sm">Записать попытку</button>
        <button onClick={onCancel} disabled={busy}
                className="btn btn--ghost btn--sm">Отмена</button>
      </div>
    </div>
  );
}
