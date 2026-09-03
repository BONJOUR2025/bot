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
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Phone, PhoneMissed, PhoneOff, Clock, MessageSquare, X, Check,
  Loader2, Undo2, CalendarClock, RefreshCw, Briefcase, ArrowRight,
  CalendarOff, Info, ExternalLink,
} from 'lucide-react';
import api from '../api';
import { formatPhone, telHref } from '../utils/phone';
import { basisNote, resumeHeadline, verdictBadge } from '../utils/resume';
import { useToast } from '../providers/ToastProvider.jsx';

const DEFAULT_NO_ANSWER_MSG =
  'Здравствуйте! Пробовали до вас дозвониться, но не получилось. ' +
  'Подскажите, когда вам удобно поговорить?';

const ONBOARDING_KEY = 'callqueue_intro_seen';

const OUTCOMES = [
  { key: 'reached',   label: 'Дозвонился',            icon: Check,         tone: 'primary' },
  { key: 'no_answer', label: 'Не дозвонился',         icon: PhoneMissed,   tone: 'default' },
  { key: 'later',     label: 'Перезвонить позже',     icon: CalendarClock, tone: 'default' },
  { key: 'inbound',   label: 'Кандидат сам связался', icon: MessageSquare, tone: 'default' },
  { key: 'rejected',  label: 'Не подходит',           icon: X,             tone: 'danger' },
];
const OUTCOME_LABEL = Object.fromEntries(OUTCOMES.map(o => [o.key, o.label]));

const WEEKDAY_FULL = ['воскресенье', 'понедельник', 'вторник', 'среду',
  'четверг', 'пятницу', 'субботу'];

/* ─── время ───────────────────────────────────────────────────────────────
 * Бэкенд отдаёт два разных вида времени, и путать их нельзя:
 *   next_attempt_at, next_window_start — уже локальные (см. модель);
 *   last_call_at, last_message_at      — UTC, как всё остальное в базе.
 * new Date('...') без суффикса разбирает строку как локальную, поэтому UTC
 * приходится помечать явно — иначе прошлая попытка показывалась на три часа
 * раньше, чем была.
 */
function parseLocal(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

function parseUtc(iso) {
  if (!iso) return null;
  const hasZone = /[Zz]$/.test(iso) || /[+-]\d{2}:\d{2}$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function timeOf(d) {
  return d ? d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : '';
}

function dayAndTime(d) {
  if (!d) return '';
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return `сегодня в ${timeOf(d)}`;
  if (d.toDateString() === tomorrow.toDateString()) return `завтра в ${timeOf(d)}`;
  if (d.toDateString() === yesterday.toDateString()) return `вчера в ${timeOf(d)}`;
  return `${d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })} в ${timeOf(d)}`;
}

function ago(d) {
  if (!d) return '';
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 60) return 'только что';
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} ч назад`;
  const days = Math.round(hours / 24);
  return days === 1 ? 'вчера' : `${days} дн. назад`;
}

/** Локальное время в формате datetime-local. Без toISOString(): бэкенд
 *  трактует next_at как местное время, и UTC-строка сдвинула бы каждый
 *  назначенный звонок на три часа. */
function localInputValue(date) {
  const pad = n => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Ошибка API человеческим языком. Технические подробности рекрутеру не
 *  помогают — ему нужно знать, что делать дальше. */
function humanError(e) {
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  const status = e?.response?.status;
  if (!e?.response) return 'Нет связи с сервером. Проверьте интернет и обновите очередь.';
  if (status === 401) return 'Сессия истекла. Войдите заново.';
  if (status === 403) return 'Недостаточно прав для этого действия.';
  if (status === 404) return 'Кандидат не найден — возможно, карточку удалили.';
  if (status >= 500) return 'Сервер не ответил. Попробуйте ещё раз через минуту.';
  return 'Не получилось выполнить действие. Попробуйте ещё раз.';
}

export default function CallQueue({ onOpenCandidate, onCountsChange }) {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  // Отдельная форма показывается только для тех исходов, где без неё
  // результат недоопределён: время для «позже», текст для первого недозвона.
  const [pending, setPending] = useState(null);
  const [lastAction, setLastAction] = useState(null);
  const [showAwaiting, setShowAwaiting] = useState(false);
  const [introHidden, setIntroHidden] = useState(() => {
    try {
      return localStorage.getItem(ONBOARDING_KEY) === '1';
    } catch {
      return false;
    }
  });

  // Колбэк держим в ref, а не в зависимостях load: родитель передаёт стрелку,
  // которая пересоздаётся на каждый его рендер, и load вместе с ней. Эффект
  // тогда перезапрашивал очередь бесконечно и на каждом круге сбрасывал
  // pending — форма «перезвонить позже» не успевала открыться.
  const countsRef = useRef(onCountsChange);
  countsRef.current = onCountsChange;

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/recruitment/call-queue');
      setData(res.data);
      setPending(null);
      countsRef.current?.({
        queue: res.data.queue_count,
        awaiting: res.data.awaiting_reply_count,
        within: res.data.within_call_hours,
      });
    } catch (e) {
      setError(humanError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const candidate = data?.next || null;
  const canCallNow = data ? data.within_call_hours !== false : true;

  function dismissIntro() {
    setIntroHidden(true);
    try {
      localStorage.setItem(ONBOARDING_KEY, '1');
    } catch { /* приватный режим — подсказка просто вернётся в следующий раз */ }
  }

  async function submit(outcome, extra = {}) {
    if (!candidate) return;
    setBusy(true);
    try {
      const res = await api.post(
        `/recruitment/candidates/${candidate.id}/call-outcome`,
        { outcome, ...extra },
      );
      if (res.data?.warning) toast(res.data.warning, 'warning');
      else if (res.data?.message_sent) toast('Кандидату отправлено сообщение в переписку');
      if (res.data?.task) toast('Время сохранено в задаче');
      setLastAction({ id: candidate.id, name: candidate.name, outcome });
    } catch (e) {
      toast(humanError(e), 'error');
    } finally {
      // Очередь перезапрашивается в любом случае: и после успеха — чтобы
      // сразу показать следующего, и после ошибки — чтобы не залипнуть на
      // карточке, которая по правилам уже обработана.
      await load();
      setBusy(false);
    }
  }

  async function undo() {
    if (!lastAction) return;
    setBusy(true);
    try {
      const res = await api.post(
        `/recruitment/candidates/${lastAction.id}/call-outcome/undo`);
      toast(res.data?.message_not_recalled
        ? 'Результат отменён. Отправленное сообщение вернуть уже нельзя.'
        : 'Результат отменён');
      setLastAction(null);
      await load();
    } catch (e) {
      toast(humanError(e), 'error');
    } finally {
      setBusy(false);
    }
  }

  function pick(outcome) {
    // Время — единственное решение, которое рекрутер принимает сам, поэтому
    // форма ровно одна. Недозвон подтверждения не требует: сообщение после
    // первой попытки шлётся само (бэкенд сам решает, первая она или нет),
    // а лишний экран между «не взял трубку» и следующим кандидатом только
    // замедляет обзвон.
    if (outcome === 'later') {
      setPending({ outcome });
      return;
    }
    submit(outcome, outcome === 'no_answer'
      ? { send_message: true, text: DEFAULT_NO_ANSWER_MSG }
      : {});
  }

  return (
    <div className="p-5 space-y-5">
      {!introHidden && <Intro onClose={dismissIntro} />}

      <QueueHeader
        data={data}
        onRefresh={load}
        loading={loading}
        onShowAwaiting={() => setShowAwaiting(true)}
      />

      <div className="max-w-3xl space-y-4">
        {!!error && (
          <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 flex items-center justify-between gap-3">
            <span>{error}</span>
            <button onClick={load} className="btn btn--ghost btn--sm flex-shrink-0">
              Обновить
            </button>
          </div>
        )}

        {!!lastAction && (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-muted)]/25 px-4 py-2.5 text-sm">
            <span className="text-[color:var(--color-text-muted)]">
              {lastAction.name} — {(OUTCOME_LABEL[lastAction.outcome] || '').toLowerCase()}
            </span>
            <button onClick={undo} disabled={busy}
                    className="btn btn--ghost btn--sm flex items-center gap-1.5 flex-shrink-0">
              <Undo2 size={14} /> Отменить
            </button>
          </div>
        )}

        {loading && !data && (
          <div className="flex items-center gap-2 text-sm text-[color:var(--color-text-muted)]">
            <Loader2 size={16} className="animate-spin" /> Собираем очередь…
          </div>
        )}

        {!!data && !canCallNow && <ClosedWindow data={data} />}

        {!!data && canCallNow && !candidate && !loading && <EmptyQueue data={data} />}

        {!!data && canCallNow && !!candidate && (
          <CallCard
            c={candidate}
            busy={busy}
            pending={pending}
            onPick={pick}
            onOpenCandidate={onOpenCandidate}
            onCancelPending={() => setPending(null)}
            onChangePending={patch => setPending(p => ({ ...p, ...patch }))}
            onConfirmPending={when => submit('later', {
              next_at: localInputValue(when),
            })}
          />
        )}
      </div>

      {showAwaiting && (
        <AwaitingReplyPanel
          onClose={() => setShowAwaiting(false)}
          onOpenCandidate={onOpenCandidate}
        />
      )}
    </div>
  );
}

// ── подсказка при первом открытии ───────────────────────────────────────

function Intro({ onClose }) {
  return (
    <div className="max-w-3xl rounded-xl border border-[color:var(--color-primary)]/30 bg-[color:var(--color-primary)]/[0.06] px-4 py-3 flex items-start gap-3">
      <Info size={16} className="text-[color:var(--color-primary)] flex-shrink-0 mt-0.5" />
      <div className="text-sm min-w-0 flex-1">
        <div className="font-semibold mb-0.5">Прозвон</div>
        <p className="text-[color:var(--color-text-muted)]">
          Здесь система сама показывает следующего кандидата, которому нужно позвонить.
          Позвоните кандидату и выберите результат разговора — система сама определит,
          что делать дальше.
        </p>
      </div>
      <button onClick={onClose} className="btn btn--ghost btn--sm flex-shrink-0">
        Понятно
      </button>
    </div>
  );
}

// ── шапка со счётчиками ─────────────────────────────────────────────────

function QueueHeader({ data, onRefresh, loading, onShowAwaiting }) {
  const awaiting = data?.awaiting_reply_count ?? 0;
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
        <Counter value={data?.queue_count} label="в очереди" />
        <Counter value={data?.calls_today} label="звонков сегодня" />
        <button
          type="button"
          onClick={onShowAwaiting}
          disabled={!awaiting}
          className="text-left rounded-lg px-2 py-1 -mx-2 transition-colors enabled:hover:bg-[color:var(--color-muted)]/40 disabled:cursor-default"
          title={awaiting ? 'Открыть список — этим кандидатам нужен ответ в переписке' : undefined}
        >
          <div className="text-xl font-bold tabular-nums leading-none flex items-center gap-1">
            {data ? awaiting : '—'}
            {!!awaiting && <ArrowRight size={14} className="text-[color:var(--color-primary)]" />}
          </div>
          <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-text-muted)] mt-1">
            ждут ответа в чате
          </div>
        </button>
        <button onClick={onRefresh} disabled={loading}
                className="btn btn--ghost btn--sm flex items-center gap-1.5"
                title="Обновить очередь">
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Обновить
        </button>
      </div>
    </div>
  );
}

function Counter({ value, label }) {
  return (
    <div>
      <div className="text-xl font-bold tabular-nums leading-none">
        {value ?? '—'}
      </div>
      <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-text-muted)] mt-1">
        {label}
      </div>
    </div>
  );
}

// ── «сейчас звонить нельзя» ─────────────────────────────────────────────

function ClosedWindow({ data }) {
  const opens = parseLocal(data.next_window_start);
  const dayOff = !!data.is_day_off;
  let when = '';
  if (opens) {
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    if (opens.toDateString() === today.toDateString()) when = `сегодня в ${timeOf(opens)}`;
    else if (opens.toDateString() === tomorrow.toDateString()) when = `завтра в ${timeOf(opens)}`;
    else when = `в ${WEEKDAY_FULL[opens.getDay()]}, ${timeOf(opens)}`;
  }
  return (
    <StateCard
      icon={dayOff ? <CalendarOff size={22} /> : <Clock size={22} />}
      title={dayOff ? 'Сегодня звонки не выполняются' : 'Сейчас нерабочее время'}
      text={when
        ? `Следующее окно звонков — ${when}.`
        : 'Окно звонков закрыто. Расписание настраивается в «Интеграциях».'}
      data={data}
    />
  );
}

// ── пустая очередь ──────────────────────────────────────────────────────

function EmptyQueue({ data }) {
  const next = parseLocal(data.next_candidate_at);
  return (
    <StateCard
      icon={<Check size={22} />}
      title="Все кандидаты обзвонены"
      text={next
        ? `Следующий кандидат появится ${dayAndTime(next)}.`
        : 'Новые появятся, когда кандидаты пройдут опрос или наступит назначенное время.'}
      data={data}
    />
  );
}

/** Общая рамка для «нечего делать»: карточку кандидата не показываем, кнопки
 *  «Позвонить» нет, но счётчики остаются — они и есть полезная часть такого
 *  экрана. */
function StateCard({ icon, title, text, data }) {
  return (
    <div className="rounded-2xl border border-[color:var(--color-border)] bg-[color:var(--color-surface)] px-6 py-9 text-center">
      <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-[color:var(--color-muted)]/40 mb-4">
        {icon}
      </div>
      <div className="text-base font-semibold">{title}</div>
      <p className="text-sm text-[color:var(--color-text-muted)] mt-1.5 max-w-md mx-auto">
        {text}
      </p>
      <div className="flex items-center justify-center gap-7 mt-6 pt-5 border-t border-[color:var(--color-border)]">
        <Counter value={data?.queue_count} label="в очереди" />
        <Counter value={data?.calls_today} label="звонков сегодня" />
        <Counter value={data?.awaiting_reply_count} label="ждут ответа" />
      </div>
    </div>
  );
}

// ── карточка звонка ─────────────────────────────────────────────────────

/** «Почему сейчас» человеческим языком: рекрутер должен понимать, обещали мы
 *  этот звонок или просто дошла очередь. */
function reasonText(c) {
  if (c.reason === 'scheduled') {
    const at = parseLocal(c.next_attempt_at);
    return at ? `Обещали позвонить ${dayAndTime(at)}` : 'Наступило назначенное время';
  }
  if (c.reason === 'never_called') return 'Новый отклик — ещё не звонили';
  if (c.reason === 'retry') return 'Повторная попытка — прошлый день закрыт';
  return 'В очереди на звонок';
}

/** Сводка ИИ по итогам опроса: вердикт, оценка, два-три довода.
 *  Полный разбор — в карточке кандидата, здесь ровно столько, сколько
 *  успеваешь прочитать, пока идёт вызов. */
function AiSummary({ profile }) {
  if (!profile?.summary && !profile?.recommendation) return null;
  const verdict = verdictBadge(profile);
  const points = [
    ...(profile.strengths || []).slice(0, 2).map(t => ({ mark: '+', text: t, good: true })),
    ...(profile.red_flags || []).slice(0, 2).map(t => ({ mark: '\u26a0', text: t, good: false })),
  ];
  return (
    <div className="mt-3.5 rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-muted)]/20 px-4 py-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[11px] uppercase tracking-wide text-[color:var(--color-text-muted)]">
          Сводка ИИ
        </span>
        {!!basisNote(profile) && (
          <span className="text-[11px] text-[color:var(--color-warning)]">{basisNote(profile)}</span>
        )}
        {profile.score != null && (
          <span className="text-sm font-semibold">{profile.score}<span className="text-[color:var(--color-text-muted)] font-normal">/100</span></span>
        )}
        {!!verdict && (
          <span className={`text-[11px] px-2 py-0.5 rounded-md border ${verdict.tone}`}>
            {verdict.label}
          </span>
        )}
      </div>
      {!!profile.summary && (
        <p className="text-sm leading-snug mt-1.5">{profile.summary}</p>
      )}
      {points.length > 0 && (
        <ul className="mt-1.5 space-y-0.5">
          {points.map((p, i) => (
            <li key={i} className={`text-xs ${p.good ? 'text-emerald-700' : 'text-amber-700'}`}>
              {p.mark} {p.text}
            </li>
          ))}
        </ul>
      )}
      {/* Ровно то, ради чего звонят: чего в данных не хватает. */}
      {!!(profile.to_ask || []).length && (
        <p className="mt-1.5 text-xs text-[color:var(--color-text-muted)]">
          Спросить: {profile.to_ask.slice(0, 3).join(' · ')}
        </p>
      )}
    </div>
  );
}

function CallCard({ c, busy, pending, onPick, onOpenCandidate,
                    onCancelPending, onChangePending, onConfirmPending }) {
  const attempts = c.call_attempts || 0;
  const lastCall = parseUtc(c.last_call_at);
  const scheduled = parseLocal(c.next_attempt_at);
  const task = c.linked_task;
  const taskDue = task?.due_date
    ? parseLocal(`${task.due_date}T${String(task.due_time || '09:00:00').slice(0, 5)}`)
    : null;

  return (
    <div className="rounded-2xl border border-[color:var(--color-border)] bg-[color:var(--color-surface)] overflow-hidden">
      <div className="px-6 pt-5 pb-5 border-b border-[color:var(--color-border)]">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <h2 className="text-lg font-bold leading-tight">{c.name}</h2>
            {!!c.vacancy_title && (
              <div className="flex items-center gap-1.5 text-sm text-[color:var(--color-text-muted)] mt-1">
                <Briefcase size={13} /> {c.vacancy_title}
              </div>
            )}
            {/* Должность, стаж и ожидания по зарплате — то, что раньше
                смотрели на hh.ru в соседней вкладке уже во время гудков. */}
            {!!resumeHeadline(c.resume_profile) && (
              <p className="text-sm text-[color:var(--color-text-muted)] mt-1">
                {resumeHeadline(c.resume_profile)}
              </p>
            )}
          </div>
          <span className="text-xs px-2.5 py-1 rounded-lg border border-[color:var(--color-border)] bg-[color:var(--color-muted)]/30 text-[color:var(--color-text-muted)]">
            {reasonText(c)}
          </span>
        </div>

        {/* Главное действие экрана. На телефоне это один тап до звонка, на
            десктопе — команда софтфону; номер виден целиком в любом случае. */}
        <a href={telHref(c.phone)}
           className="btn btn--primary mt-4 inline-flex items-center gap-2.5 text-base"
           style={{ paddingTop: '0.6rem', paddingBottom: '0.6rem' }}>
          <Phone size={17} /> Позвонить · {formatPhone(c.phone) || c.phone}
        </a>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mt-3.5 text-sm text-[color:var(--color-text-muted)]">
          <span className="inline-flex items-center gap-1.5">
            <PhoneOff size={13} />
            {attempts > 0 ? `Попытка ${attempts + 1} из 3` : 'Первый звонок'}
          </span>
          {!!lastCall && <span>Прошлая — {dayAndTime(lastCall)}</span>}
          {!!scheduled && c.reason !== 'scheduled' && (
            <span className="inline-flex items-center gap-1.5">
              <CalendarClock size={13} /> Назначено на {dayAndTime(scheduled)}
            </span>
          )}
        </div>

        <AiSummary profile={c.profile} />

        {(!!(c.flags || []).length || !c.has_chat) && (
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
        )}

        {!!task && (
          <div className="mt-3 flex items-center gap-2 text-sm text-[color:var(--color-text-muted)]">
            <CalendarClock size={14} />
            Задача: {task.title}{taskDue ? ` — ${dayAndTime(taskDue)}` : ''}
          </div>
        )}

        <div className="flex flex-wrap gap-2 mt-4">
          <button onClick={() => onOpenCandidate?.(c, 'info')}
                  className="btn btn-secondary btn--sm flex items-center gap-1.5">
            <ExternalLink size={14} /> Карточка
          </button>
          {!!c.has_chat && (
            <button onClick={() => onOpenCandidate?.(c, 'chat')}
                    className="btn btn-secondary btn--sm flex items-center gap-1.5">
              <MessageSquare size={14} /> Переписка
            </button>
          )}
        </div>
      </div>

      {/* Ответы опроса — то, ради чего звонок и становится осмысленным:
          звонить, не зная, что человек уже написал, значит спрашивать заново
          то, на что он ответил. */}
      {!!(c.answers || []).length && (
        <div className="px-6 py-4 border-b border-[color:var(--color-border)] space-y-2.5">
          {c.answers.map((a, i) => (
            <div key={i}>
              <div className="text-xs text-[color:var(--color-text-muted)]">
                {a.q || a.question || `Вопрос ${i + 1}`}
              </div>
              <div className="text-sm">{a.a || a.answer || '—'}</div>
            </div>
          ))}
        </div>
      )}

      <div className="px-6 py-4">
        {pending
          ? <PendingForm pending={pending} busy={busy} onChange={onChangePending}
                         onCancel={onCancelPending} onConfirm={onConfirmPending} />
          : (
            <>
              <div className="text-xs uppercase tracking-wide text-[color:var(--color-text-muted)] mb-2.5">
                Как прошёл звонок
              </div>
              <div className="flex flex-wrap items-center gap-2">
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
                {busy && (
                  <span className="inline-flex items-center gap-1.5 text-sm text-[color:var(--color-text-muted)] px-1">
                    <Loader2 size={14} className="animate-spin" /> Записываем…
                  </span>
                )}
              </div>
            </>
          )}
      </div>
    </div>
  );
}

function PendingForm({ pending, busy, onChange, onCancel, onConfirm }) {
  // Единственное место ручного ввода во всём режиме — и то сведено к двум
  // нажатиям: день и час. Дату строкой набирать не нужно.
  const now = new Date();
  const day = pending.day || 'tomorrow';
  const time = pending.time || '10:00';
  const customDate = pending.date || (() => {
    const d = new Date(now);
    d.setDate(d.getDate() + 2);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  })();

  const days = [
    { key: 'today', label: 'Сегодня' },
    { key: 'tomorrow', label: 'Завтра' },
    { key: 'other', label: 'Другой день' },
  ];
  // Часы окна звонков: предлагать 03:00 бессмысленно — бэкенд всё равно
  // сдвинет такое время в ближайшее окно.
  const hours = ['10:00', '11:00', '12:00', '13:00', '14:00',
                 '15:00', '16:00', '17:00', '18:00', '19:00'];

  function resolved() {
    let d = new Date(now);
    if (day === 'tomorrow') d.setDate(d.getDate() + 1);
    if (day === 'other') {
      const [y, m, dd] = customDate.split('-').map(Number);
      d = new Date(y, m - 1, dd);
    }
    const [hh, mm] = time.split(':').map(Number);
    d.setHours(hh, mm, 0, 0);
    return d;
  }

  const when = resolved();
  const inPast = when.getTime() <= now.getTime();

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium">Когда перезвонить</div>

      <div className="flex flex-wrap gap-1.5">
        {days.map(d => (
          <button
            key={d.key}
            type="button"
            onClick={() => onChange({ day: d.key })}
            className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
              day === d.key
                ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]'
                : 'bg-[color:var(--color-control-bg)] border-[color:var(--color-border)] hover:bg-[color:var(--color-muted)]'
            }`}
          >
            {d.label}
          </button>
        ))}
        {day === 'other' && (
          <input
            type="date"
            value={customDate}
            onChange={e => onChange({ date: e.target.value })}
            className="input"
            style={{ maxWidth: '11rem' }}
          />
        )}
      </div>

      <div className="flex flex-wrap gap-1.5 items-center">
        {hours.map(h => (
          <button
            key={h}
            type="button"
            onClick={() => onChange({ time: h })}
            className={`px-2.5 py-1 rounded-lg text-sm tabular-nums border transition-colors ${
              time === h
                ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]'
                : 'bg-[color:var(--color-control-bg)] border-[color:var(--color-border)] hover:bg-[color:var(--color-muted)]'
            }`}
          >
            {h}
          </button>
        ))}
        <input
          type="time"
          value={time}
          onChange={e => onChange({ time: e.target.value })}
          className="input"
          style={{ maxWidth: '7.5rem' }}
          title="Другое время"
        />
      </div>

      <p className="text-sm">
        Перезвонить <b>{dayAndTime(when)}</b>
      </p>
      {inPast && (
        <p className="text-xs text-amber-700">
          Это время уже прошло — выберите более позднее.
        </p>
      )}
      {/* Правило дня объясняем заранее и без обещаний: напоминание сейчас
          никуда не отправляется, задача просто появляется в списке дел. */}
      <p className="text-xs text-[color:var(--color-text-muted)]">
        Время сохранится в задаче «Позвонить: …» в разделе «Задачи». Если сегодня
        этому кандидату уже звонили, звонок перенесётся на ближайший следующий
        рабочий день: больше одного звонка в день не делаем.
      </p>
      <div className="flex gap-2">
        <button onClick={() => onConfirm(when)} disabled={busy || inPast}
                className="btn btn--primary btn--sm">
          {busy ? 'Сохраняем…' : 'Сохранить и дальше'}
        </button>
        <button onClick={onCancel} disabled={busy}
                className="btn btn--ghost btn--sm">Отмена</button>
      </div>
    </div>
  );
}

// ── ждут ответа в переписке ─────────────────────────────────────────────

/** Отдельный список, а не вторая очередь: этим людям нужен текст, а не
 *  звонок. Поэтому здесь нет ни «следующего», ни результатов звонка — только
 *  переход в переписку. */
function AwaitingReplyPanel({ onClose, onOpenCandidate }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    api.get('/recruitment/awaiting-reply')
      .then(r => { if (alive) setRows(r.data); })
      .catch(e => { if (alive) setError(humanError(e)); });
    return () => { alive = false; };
  }, []);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card max-w-2xl w-full" onClick={e => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="font-semibold text-base">Ждут ответа в переписке</h3>
            <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">
              Эти кандидаты написали последними. Им нужен ответ текстом, а не звонок.
            </p>
          </div>
          <button onClick={onClose} className="btn btn--ghost btn--sm flex-shrink-0">
            <X size={16} />
          </button>
        </div>

        <div className="mt-4 max-h-[60vh] overflow-y-auto divide-y divide-[color:var(--color-border)]">
          {rows === null && !error && (
            <div className="py-6 flex items-center gap-2 text-sm text-[color:var(--color-text-muted)]">
              <Loader2 size={15} className="animate-spin" /> Загружаем…
            </div>
          )}
          {!!error && <div className="py-6 text-sm text-red-600">{error}</div>}
          {rows?.length === 0 && (
            <div className="py-6 text-sm text-[color:var(--color-text-muted)]">
              Все ответы даны — никто не ждёт.
            </div>
          )}
          {(rows || []).map(c => {
            const at = parseUtc(c.last_message_at);
            // Этап подписываем явно: «Мастер по ремонту · ответил · 1 ч назад»
            // читается как «ответил час назад», хотя «ответил» здесь — колонка
            // воронки.
            const stage = c.stage
              ? `этап: ${c.stage.charAt(0).toUpperCase()}${c.stage.slice(1)}`
              : '';
            const meta = [c.vacancy_title, stage, at ? `написал ${ago(at)}` : '']
              .filter(Boolean).join(' · ');
            return (
              <div key={c.id} className="py-3 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium">{c.name}</div>
                  {!!meta && (
                    <div className="text-xs text-[color:var(--color-text-muted)] mt-0.5">
                      {meta}
                    </div>
                  )}
                  {!!c.last_message_text && (
                    <div className="text-sm mt-1 line-clamp-2 text-[color:var(--color-text-muted)]">
                      «{c.last_message_text}»
                    </div>
                  )}
                </div>
                {/* Панель НЕ закрываем: карточка кандидата открывается
                    поверх, и, ответив, рекрутер возвращается ровно в тот же
                    список — обращения разбираются подряд, а не по одному
                    с возвратом через счётчик. */}
                <button
                  onClick={() => onOpenCandidate?.(c, 'chat')}
                  className="btn btn-secondary btn--sm flex items-center gap-1.5 flex-shrink-0"
                >
                  <MessageSquare size={14} /> Ответить
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
