import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlarmClock, Archive, BookOpen, CalendarDays, ClipboardCheck, ClipboardList, Inbox, KeyRound, MessageCircle,
  Phone, PhoneOff, RefreshCw, ScanBarcode, Send, Sparkles, StickyNote, Trash2, Truck, UserSearch, Wallet, X,
} from 'lucide-react';
import api, { POINT_TOKEN_KEY } from '../api.js';
import { OrderSearch, OrderView } from './employee/WorkshopOrder.jsx';
import { StatCard } from '../components/ui/SalaryUI.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import useBackClose from '../hooks/useBackClose.js';

/** Кабинет точки — открыт весь день на рабочем ПК салона (/admin/point).
 *
 *  Вход не по логину: ПК подключают один раз кодом из «Салонов», дальше
 *  браузер помнит ключ точки. Оболочка та же, что у админки (боковое меню,
 *  верхняя строка, карточки), чтобы администратор и руководитель видели
 *  одну систему. Разделы отвечают на вопросы смены: кто на точке, что
 *  выдать и кому позвонить, что просрочено, что едет из цеха, как найти
 *  клиента и что сказать ему по прайсу. Сканер бирок — вверху на любой
 *  странице: ручной сканер печатает бирку в поле и открывает заказ. */

const SECTIONS = [
  {
    name: 'Смена',
    items: [
      { key: 'today', label: 'Сегодня', icon: ClipboardList },
      { key: 'ready', label: 'Выдача', icon: Inbox, count: (l) => l.ready.length },
      { key: 'due', label: 'Сроки', icon: AlarmClock, count: (l) => l.due.length },
      { key: 'stale', label: 'Долго лежат', icon: Archive, count: (l) => l.stale.length },
      { key: 'handover', label: 'Передача смены', icon: ClipboardCheck, count: (l) => l.notesNow || null },
    ],
  },
  {
    name: 'Точка',
    items: [
      { key: 'cash', label: 'Касса', icon: Wallet },
      { key: 'accepted', label: 'Принято сегодня', icon: Send },
      { key: 'schedule', label: 'График', icon: CalendarDays },
    ],
  },
  {
    name: 'Помощь',
    items: [
      { key: 'clients', label: 'Клиенты', icon: UserSearch },
      { key: 'kb', label: 'База знаний', icon: BookOpen },
    ],
  },
];
const TITLES = {
  today: ['Смена', 'Сегодня на точке', 'Кого обзвонить, что предупредить и что лежит на полке — одним экраном.'],
  ready: ['Смена', 'Готово к выдаче', 'Изделия готовы, клиент ещё не забрал. Сначала те, кому ещё не звонили.'],
  due: ['Смена', 'Сроки', 'Не готово, а срок выдачи сегодня или уже прошёл. Предупредите клиента до того, как он приедет.'],
  stale: ['Смена', 'Долго лежат', 'Готовы больше 14 дней назад и до сих пор не выданы. Напомните клиенту.'],
  handover: ['Смена', 'Передача смены', 'Заметки для смены пишите в течение дня — на любую дату и к заказу. При уходе сдайте смену: пересчёт кассы и чек-лист.'],
  cash: ['Точка', 'Касса', 'Касса точки в Агбисе за сегодня: остаток, приход и перемещения в «Основную».'],
  accepted: ['Точка', 'Принято сегодня', 'Заказы, оформленные на точке за сегодня.'],
  schedule: ['Точка', 'График на неделю', 'Кто работает на точке — по общему графику.'],
  clients: ['Помощь', 'Клиенты', 'Поиск по фамилии, телефону или номеру заказа. История заказов и пароль от личного кабинета.'],
  kb: ['Помощь', 'База знаний', 'Прайсы, методички и регламенты. Помощник отвечает на вопросы строго по ним.'],
};
const CALL_RESULTS = [
  { key: 'reached', label: 'Дозвонилась', icon: Phone },
  { key: 'no_answer', label: 'Не ответил', icon: PhoneOff },
  { key: 'message', label: 'Написала', icon: MessageCircle },
];
const CALL_LABEL = { reached: 'дозвонилась', no_answer: 'не ответил', message: 'написала' };

function readToken() {
  try { return window.localStorage.getItem(POINT_TOKEN_KEY); } catch { return null; }
}
const money = (n) => `${Math.round(Number(n) || 0).toLocaleString('ru-RU')} ₽`;
function day(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}
function weekday(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'short' });
}
function dayTime(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—'
    : d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}
function hhmm(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}
function errText(e, fallback) {
  const d = e?.response?.data?.detail;
  return typeof d === 'string' ? d : fallback;
}
function isEditable(el) {
  return !!el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
}

/** Данные раздела: грузим при первом открытии, дальше — по кнопке «Обновить». */
function useSection(url, enabled, tick) {
  const [state, setState] = useState({ data: null, loading: false, error: '' });
  useEffect(() => {
    if (!enabled) return undefined;
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: '' }));
    api.get(url)
      .then((r) => alive && setState({ data: r.data, loading: false, error: '' }))
      .catch((e) => alive && setState((s) => ({ ...s, loading: false, error: errText(e, 'Не удалось загрузить.') })));
    return () => { alive = false; };
  }, [url, enabled, tick]);
  return state;
}

/* ── подключение ПК ─────────────────────────────────────────────── */
function Activate({ onDone }) {
  const [code, setCode] = useState('');
  const [label, setLabel] = useState('Стойка');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const r = await api.post('/point/activate', { code: code.trim(), label });
      try { window.localStorage.setItem(POINT_TOKEN_KEY, r.data.token); } catch { /* без ключа войти не выйдет */ }
      onDone();
    } catch (err) {
      setError(errText(err, 'Не удалось подключить компьютер.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="pc-activate">
      <form className="app-card pc-activate__card" onSubmit={submit}>
        <span className="sidebar__badge">B</span>
        <span className="ui-eyebrow">Кабинет точки</span>
        <h1 className="text-2xl font-semibold tracking-tight">Подключите компьютер</h1>
        <p className="text-sm text-[color:var(--color-muted-foreground)]">
          Попросите руководителя открыть «Салоны → ваша точка → Подробнее → Компьютеры → Подключить компьютер» и введите код.
        </p>
        <label htmlFor="pc-code">Код из шести цифр</label>
        <input id="pc-code" className="input pc-activate__code" inputMode="numeric" autoFocus maxLength={6}
          value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} placeholder="000000" />
        <label htmlFor="pc-label">Название компьютера</label>
        <input id="pc-label" className="input" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60} />
        {error && <p className="pc-error">{error}</p>}
        <button type="submit" className="btn btn--primary" disabled={busy || code.length !== 6}>
          {busy ? 'Подключаю…' : 'Подключить'}
        </button>
      </form>
    </div>
  );
}

/* ── заказы с отметкой звонка ───────────────────────────────────── */
function CallButtons({ row, onMarked }) {
  const [busy, setBusy] = useState(null);
  const mark = async (result) => {
    setBusy(result);
    try {
      await api.post(`/point/orders/${row.order_id}/call`, { result });
      onMarked();
    } catch {
      /* не сохранилось — кнопка отпустится, можно нажать ещё раз */
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="pc-calls">
      {CALL_RESULTS.map(({ key, label, icon: Icon }) => (
        <button key={key} type="button" className="pc-call" onClick={(e) => { e.stopPropagation(); mark(key); }}
          disabled={!!busy} aria-label={`${label}: ${row.doc_num}`}>
          <Icon size={14} aria-hidden="true" /><span>{label}</span>
        </button>
      ))}
    </div>
  );
}

function CallState({ call }) {
  if (!call) return <span className="badge badge--warning">не звонили</span>;
  return (
    <span className={`badge ${call.result === 'reached' ? 'badge--success' : 'badge--neutral'}`}>
      {CALL_LABEL[call.result] || call.result} · {dayTime(call.at)}{call.count > 1 ? ` · ${call.count}×` : ''}
    </span>
  );
}

function OrdersTable({ rows, kind, onOpen, onMarked, empty }) {
  if (!rows.length) return <div className="app-card p-6 text-sm text-[color:var(--color-muted-foreground)]">{empty}</div>;
  return (
    <div className="app-card pc-table-wrap">
      <table className="pc-table">
        <thead>
          <tr>
            <th>Заказ</th><th>Изделия</th><th>Клиент</th>
            <th>{kind === 'due' ? 'Срок' : 'Готов'}</th>
            <th className="num">К оплате</th><th>Звонок</th><th aria-label="Отметить звонок" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.order_id} onClick={() => onOpen(r.order_id)} tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter') onOpen(r.order_id); }}>
              <td className="pc-num">{r.doc_num}{r.urgent && <span className="badge badge--error ml-1">срочно</span>}</td>
              <td>{r.items.length ? r.items.join(', ') : '—'}</td>
              <td>
                <div>{r.client || '—'}</div>
                {r.phone && <div className="pc-phone">{r.phone}</div>}
              </td>
              {kind === 'due' ? (
                <td>
                  <div>{day(r.due)}</div>
                  {r.overdue_days > 0
                    ? <span className="badge badge--error">просрочен {r.overdue_days} дн</span>
                    : <span className="badge badge--warning">сегодня</span>}
                  <div className="pc-muted">сейчас: {r.location || '—'}</div>
                </td>
              ) : (
                <td>
                  <div>{r.ready_since ? day(r.ready_since) : '—'}</div>
                  {r.ready_days != null && <div className="pc-muted">{r.ready_days} дн назад</div>}
                  {r.sms && <div className="pc-muted">СМС {day(r.sms.sent)}{r.sms.delivered ? ', доставлено' : ''}</div>}
                </td>
              )}
              <td className="num">{r.to_pay > 0 ? money(r.to_pay) : <span className="pc-muted">оплачен</span>}</td>
              <td><CallState call={r.call} /></td>
              <td><CallButtons row={r} onMarked={onMarked} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── разделы «Точка» ─────────────────────────────────────────────── */
function Accepted({ tick, onOpen }) {
  const { data, loading, error } = useSection('/point/accepted', true, tick);
  if (loading && !data) return <p className="pc-muted">Загрузка…</p>;
  if (error) return <p className="pc-error">{error}</p>;
  const rows = data || [];
  if (!rows.length) return <div className="app-card p-6 text-sm text-[color:var(--color-muted-foreground)]">Сегодня заказов на точке ещё не оформляли.</div>;
  return (
    <div className="app-card pc-table-wrap">
      <table className="pc-table">
        <thead><tr><th>Время</th><th>Заказ</th><th>Изделия</th><th>Клиент</th><th>Срок</th><th>Статус</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.order_id} onClick={() => onOpen(r.order_id)}>
              <td className="pc-num">{r.time}</td>
              <td className="pc-num">{r.doc_num}{r.urgent && <span className="badge badge--error ml-1">срочно</span>}</td>
              <td>{r.items.length ? r.items.join(', ') : '—'}</td>
              <td>{r.client || '—'}</td>
              <td>{r.due ? day(r.due) : '—'}</td>
              <td><span className="badge badge--neutral">{r.status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Schedule({ tick }) {
  const { data, loading, error } = useSection('/point/schedule', true, tick);
  if (loading && !data) return <p className="pc-muted">Загрузка…</p>;
  if (error) return <p className="pc-error">{error}</p>;
  return (
    <div className="pc-week">
      {(data || []).map((d, i) => (
        <div key={d.date} className={`app-card pc-day ${i === 0 ? 'is-today' : ''}`}>
          <span className="pc-muted">{i === 0 ? 'Сегодня' : weekday(d.date)}</span>
          <b>{d.employee || '—'}</b>
          {i === 0 && <span className="pc-muted">{weekday(d.date)}</span>}
        </div>
      ))}
      <p className="pc-hint" style={{ gridColumn: '1 / -1' }}>Если день пустой — в графике на него никто не поставлен или месяц ещё не заполнен.</p>
    </div>
  );
}

/* ── заметки смены ──────────────────────────────────────────────── */
const NAME_KEY = 'point_my_name';
function readName() { try { return window.localStorage.getItem(NAME_KEY) || ''; } catch { return ''; } }
function saveName(n) { try { window.localStorage.setItem(NAME_KEY, n.trim()); } catch { /* не запомним — не страшно */ } }
function isoDay(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function dueLabel(iso) {
  if (iso === isoDay(0)) return 'Сегодня';
  if (iso === isoDay(1)) return 'Завтра';
  if (iso === isoDay(2)) return 'Послезавтра';
  return dayShort(iso);
}
const QUICK_DAYS = [[0, 'Сегодня'], [1, 'Завтра'], [2, 'Послезавтра']];

function DuePicker({ value, onChange, idPrefix }) {
  const quick = QUICK_DAYS.find(([o]) => isoDay(o) === value);
  return (
    <div className="pc-due">
      <div className="pc-seg" role="group" aria-label="На какой день">
        {QUICK_DAYS.map(([o, label]) => (
          <button key={o} type="button" className={value === isoDay(o) ? 'is-on' : ''} onClick={() => onChange(isoDay(o))}>{label}</button>
        ))}
      </div>
      <input id={`${idPrefix}-date`} type="date" className={`input pc-date ${quick ? '' : 'is-on'}`} min={isoDay(0)} value={value}
        onChange={(e) => e.target.value && onChange(e.target.value)} aria-label="Другая дата" />
    </div>
  );
}

/** Быстрая заметка: текст, заказ (номер или бирка), дата. Enter — добавить. */
function NoteForm({ onAdded, fixedOrderId, people, idPrefix = 'note' }) {
  const [text, setText] = useState('');
  const [order, setOrder] = useState('');
  const [due, setDue] = useState(isoDay(1));
  const [by, setBy] = useState(readName);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async (e) => {
    e.preventDefault();
    if (text.trim().length < 2) return;
    setBusy(true); setErr('');
    try {
      await api.post('/point/notes', { text, due, by, order: fixedOrderId ? '' : order, order_id: fixedOrderId || null });
      if (by.trim()) saveName(by);
      setText(''); setOrder('');
      onAdded();
    } catch (e2) { setErr(errText(e2, 'Не удалось добавить.')); } finally { setBusy(false); }
  };
  return (
    <form className="pc-note-form" onSubmit={submit}>
      <div className="pc-note-form__main">
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} maxLength={500}
          placeholder={fixedOrderId ? 'Что по этому заказу передать смене' : 'Что передать: перезвонить, клиент придёт в 12, кончились пакеты…'}
          aria-label="Текст заметки" />
        {!fixedOrderId && (
          <input className="input pc-note-form__order" value={order} onChange={(e) => setOrder(e.target.value)} maxLength={40}
            placeholder="Заказ или бирка" aria-label="Заказ (необязательно)" />
        )}
      </div>
      <div className="pc-note-form__row">
        <DuePicker value={due} onChange={setDue} idPrefix={idPrefix} />
        <div className="pc-note-form__by">
          <NameInput id={`${idPrefix}-by`} value={by} onChange={setBy} people={people} placeholder="Кто пишет" />
        </div>
        <button type="submit" className="btn btn--primary" disabled={busy || text.trim().length < 2}>{busy ? '…' : 'Добавить'}</button>
      </div>
      {err && <p className="pc-error">{err}</p>}
    </form>
  );
}

function NoteRow({ n, onChanged, onOpenOrder, showDue }) {
  const [busy, setBusy] = useState(false);
  const [moving, setMoving] = useState(false);
  const patch = async (body) => {
    setBusy(true);
    try { await api.patch(`/point/notes/${n.id}`, { by: readName(), ...body }); onChanged(); } catch { /* останется как было */ } finally { setBusy(false); setMoving(false); }
  };
  const remove = async () => {
    setBusy(true);
    try { await api.delete(`/point/notes/${n.id}`); onChanged(); } catch { setBusy(false); }
  };
  const done = !!n.done;
  return (
    <li className={`pc-note ${done ? 'is-done' : ''}`}>
      <input type="checkbox" checked={done} disabled={busy} onChange={() => patch({ done: !done })}
        aria-label={done ? 'Вернуть в работу' : 'Сделано'} />
      <div className="pc-note__body">
        <div className="pc-note__text">{n.text}</div>
        <div className="pc-note__meta">
          {n.order && (
            <button type="button" className="pc-note__order" onClick={() => onOpenOrder(n.order.order_id)}>
              {n.order.doc_num}{n.order.client ? ` · ${n.order.client}` : ''}
            </button>
          )}
          {showDue && <span className="badge badge--neutral">{dueLabel(n.due)}</span>}
          <span>{n.by || 'без подписи'} · {dayTime(n.created_at)}</span>
          {done && <span>сделано{n.done.by ? ` · ${n.done.by}` : ''} · {dayTime(n.done.at)}</span>}
        </div>
      </div>
      {!done && (
        <div className="pc-note__actions">
          {moving ? (
            <input type="date" className="input pc-date" min={isoDay(0)} defaultValue={n.due} autoFocus aria-label="Новая дата"
              onChange={(e) => e.target.value && patch({ due: e.target.value })} onBlur={() => setMoving(false)} />
          ) : (
            <>
              {n.due <= isoDay(0) && <button type="button" className="pc-call" disabled={busy} onClick={() => patch({ due: isoDay(1) })}>на завтра</button>}
              <button type="button" className="pc-call" disabled={busy} onClick={() => setMoving(true)}>перенести</button>
            </>
          )}
          <button type="button" className="icon-button icon-button--ghost" disabled={busy} onClick={remove} aria-label="Удалить заметку"><Trash2 size={15} /></button>
        </div>
      )}
    </li>
  );
}

function groupNotes(notes) {
  const today = isoDay(0);
  const open = notes.filter((n) => !n.done).sort((a, b) => (a.due + a.created_at).localeCompare(b.due + b.created_at));
  const groups = [];
  const overdue = open.filter((n) => n.due < today);
  if (overdue.length) groups.push({ key: 'overdue', title: 'Не сделано вовремя', tone: 'error', items: overdue, showDue: true });
  const dates = [...new Set(open.filter((n) => n.due >= today).map((n) => n.due))];
  if (!dates.includes(today)) dates.unshift(today);
  dates.forEach((d) => groups.push({ key: d, title: dueLabel(d), sub: d === today || d === isoDay(1) || d === isoDay(2) ? dayShort(d) : '', items: open.filter((n) => n.due === d) }));
  const doneRecent = notes.filter((n) => n.done && n.done.at >= new Date(Date.now() - 7 * 864e5).toISOString())
    .sort((a, b) => b.done.at.localeCompare(a.done.at));
  return { groups, doneRecent };
}

function NotesBoard({ notes, reload, people, onOpenOrder }) {
  const [showDone, setShowDone] = useState(false);
  const { groups, doneRecent } = useMemo(() => groupNotes(notes), [notes]);
  return (
    <section className="app-card p-5 space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <StickyNote size={18} style={{ color: 'var(--color-primary)' }} aria-hidden="true" />
        <h3 className="pc-h3" style={{ margin: 0 }}>Что передать смене</h3>
      </div>
      <p className="pc-hint">Пишите в течение дня, как только вспомнили. Заметка всплывёт в тот день, на который поставлена, и уйдёт в журнал при сдаче смены.</p>
      <NoteForm onAdded={reload} people={people} />
      <div className="space-y-4">
        {groups.map((g) => (
          <div key={g.key} className="pc-note-group">
            <div className="pc-note-group__title">
              <b className={g.tone === 'error' ? 'pc-warn-text' : ''}>{g.title}</b>
              {g.sub && <span className="pc-muted">{g.sub}</span>}
              <span className={`badge ${g.tone === 'error' ? 'badge--error' : 'badge--neutral'}`}>{g.items.length}</span>
            </div>
            {g.items.length === 0
              ? <p className="pc-muted pc-note-empty">На сегодня заметок нет.</p>
              : <ul className="pc-notes">{g.items.map((n) => <NoteRow key={n.id} n={n} onChanged={reload} onOpenOrder={onOpenOrder} showDue={g.showDue} />)}</ul>}
          </div>
        ))}
        {doneRecent.length > 0 && (
          <div className="pc-note-group">
            <button type="button" className="pc-link" onClick={() => setShowDone((v) => !v)}>
              {showDone ? 'Скрыть сделанное' : `Сделано за неделю — ${doneRecent.length}`}
            </button>
            {showDone && <ul className="pc-notes">{doneRecent.map((n) => <NoteRow key={n.id} n={n} onChanged={reload} onOpenOrder={onOpenOrder} showDue />)}</ul>}
          </div>
        )}
      </div>
    </section>
  );
}

/** Заметки прямо в карточке заказа: что уже висит по заказу и быстрая новая. */
function OrderNotes({ orderId, notes, reload, people }) {
  const mine = notes.filter((n) => n.order?.order_id === orderId && !n.done);
  return (
    <div className="pc-order-notes">
      <div className="pc-note-group__title"><StickyNote size={15} aria-hidden="true" /><b>Заметка смене по заказу</b>
        {mine.length > 0 && <span className="badge badge--warning">{mine.length}</span>}</div>
      {mine.length > 0 && (
        <ul className="pc-notes">{mine.map((n) => <NoteRow key={n.id} n={n} onChanged={reload} onOpenOrder={() => {}} showDue />)}</ul>
      )}
      <NoteForm onAdded={reload} fixedOrderId={orderId} people={people} idPrefix="onote" />
    </div>
  );
}

/* ── касса и передача смены ─────────────────────────────────────── */
const CHECKLIST = [
  'Касса пересчитана',
  'Готовые заказы на полке сверены',
  'Накладные из цеха разобраны',
  'Ключи и сейф на месте',
  'Терминал и принтер бирок работают',
  'Зал и витрина в порядке',
];
const signed = (n) => `${n > 0 ? '+' : n < 0 ? '−' : ''}${money(Math.abs(n))}`;
function Diff({ counted, agbis }) {
  if (counted == null || agbis == null) return null;
  const diff = Math.round((counted - agbis) * 100) / 100;
  if (Math.abs(diff) < 1) return <span className="badge badge--success">сходится</span>;
  return <span className="badge badge--error">{diff > 0 ? 'излишек' : 'недостача'} {money(Math.abs(diff))}</span>;
}
function dayShort(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'short' });
}

function Cash({ tick }) {
  const { data, loading, error } = useSection('/point/cash', true, tick);
  const [mode, setMode] = useState('move');
  if (loading && !data) return <p className="pc-muted">Загрузка…</p>;
  if (error) return <p className="pc-error">{error}</p>;
  if (!data?.kassa_id) return <div className="app-card p-6 text-sm text-[color:var(--color-muted-foreground)]">Касса этой точки не настроена — сообщите руководителю.</div>;
  const today = data.days[0] || {};
  const rows = data.entries.filter((e) => mode === 'all' || e.kind === 'move');
  return (
    <div className="space-y-5">
      <div className="pc-kpis">
        <StatCard icon={<Wallet size={18} />} label="В кассе по Агбису" value={money(data.balance)} sub={data.kassa_name} />
        <StatCard icon={<Wallet size={18} />} label="Приход сегодня" value={money(today.income)} sub={`на начало дня ${money(today.opening)}`} />
        <StatCard icon={<Truck size={18} />} label="Перемещения сегодня" value={money(today.collection)} sub="ушло в «Основную»" />
        <StatCard icon={<Wallet size={18} />} label="Расход сегодня" value={money(today.expense)} sub="возвраты и прочее" />
      </div>

      <section className="space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          <h3 className="pc-h3">Проводки</h3>
          <div className="pc-seg" role="group" aria-label="Какие проводки показать">
            <button type="button" className={mode === 'move' ? 'is-on' : ''} onClick={() => setMode('move')}>Перемещения</button>
            <button type="button" className={mode === 'all' ? 'is-on' : ''} onClick={() => setMode('all')}>Все</button>
          </div>
        </div>
        {rows.length === 0
          ? <div className="app-card p-6 text-sm text-[color:var(--color-muted-foreground)]">Сегодня таких проводок нет.</div>
          : (
            <div className="app-card pc-table-wrap">
              <table className="pc-table" style={{ minWidth: '46rem' }}>
                <thead><tr><th>Время</th><th>Документ</th><th>Основание</th><th>Кто</th><th className="num">Сумма</th></tr></thead>
                <tbody>
                  {rows.map((e) => {
                    const amount = (e.debet || 0) - (e.kredit || 0);
                    return (
                      <tr key={e.id} style={{ cursor: 'default' }}>
                        <td className="pc-num">{e.time}</td>
                        <td className="pc-num">{e.doc_num}</td>
                        <td>
                          <div>{e.basis_text || e.basis_name}</div>
                          <div className="pc-muted">{e.transfer_text || e.basis_name}</div>
                        </td>
                        <td>{e.user_name}</td>
                        <td className={`num ${amount < 0 ? 'pc-neg' : 'pc-pos'}`}>{signed(amount)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
      </section>

    </div>
  );
}

function NameInput({ id, value, onChange, people, placeholder }) {
  return (
    <>
      <input id={id} className="input" list={`${id}-people`} value={value} onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder} maxLength={80} autoComplete="off" />
      <datalist id={`${id}-people`}>{people.map((n) => <option key={n} value={n} />)}</datalist>
    </>
  );
}
const toNum = (v) => (String(v).trim() === '' ? null : Number(String(v).replace(/\s/g, '').replace(',', '.')));

function Passed({ rec }) {
  const items = rec.passed || [];
  if (!items.length && !rec.notes) return null;
  return (
    <ul className="pc-passed">
      {items.map((n) => (
        <li key={n.id}>{n.doc_num && <b className="pc-num">{n.doc_num} </b>}{n.text}
          {n.due !== rec.at.slice(0, 10) && <span className="pc-muted"> · {dueLabel(n.due)}</span>}</li>
      ))}
      {rec.notes && <li style={{ whiteSpace: 'pre-wrap' }}>{rec.notes}</li>}
    </ul>
  );
}

function AcceptForm({ rec, people, onDone }) {
  const [by, setBy] = useState(readName);
  const [cash, setCash] = useState('');
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr('');
    try {
      await api.post(`/point/handover/${rec.id}/accept`, { by, cash_counted: toNum(cash), comment });
      saveName(by);
      onDone();
    } catch (e2) { setErr(errText(e2, 'Не удалось сохранить.')); } finally { setBusy(false); }
  };
  return (
    <form className="app-card p-5 space-y-3 pc-accept" onSubmit={submit}>
      <div className="flex items-center gap-2 flex-wrap">
        <b>Смену сдал(а) {rec.by} · {dayTime(rec.at)}</b>
        <span className="badge badge--warning">ждёт приёма</span>
      </div>
      <div className="pc-muted">
        В кассе насчитано {rec.cash_counted != null ? money(rec.cash_counted) : '—'}
        {rec.cash_agbis != null ? ` · по Агбису ${money(rec.cash_agbis)}` : ''}
        {' '}<Diff counted={rec.cash_counted} agbis={rec.cash_agbis} />
      </div>
      {((rec.passed || []).length > 0 || rec.notes) && <div className="pc-answer"><div className="pc-muted">Передано на смену</div><Passed rec={rec} /></div>}
      <div className="pc-form-grid">
        <label htmlFor="acc-by">Кто принимает<NameInput id="acc-by" value={by} onChange={setBy} people={people} placeholder="Фамилия Имя" /></label>
        <label htmlFor="acc-cash">Мой пересчёт кассы, ₽<input id="acc-cash" className="input" inputMode="decimal" value={cash} onChange={(e) => setCash(e.target.value)} placeholder="если пересчитали" /></label>
      </div>
      <label htmlFor="acc-comment" className="pc-field">Если что-то не сошлось — что именно
        <textarea id="acc-comment" className="input" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} maxLength={1000} />
      </label>
      {err && <p className="pc-error">{err}</p>}
      <button type="submit" className="btn btn--primary" disabled={busy || by.trim().length < 2}>{busy ? 'Сохраняю…' : 'Смену принял(а)'}</button>
    </form>
  );
}

function Handover({ tick, people, notes, reloadNotes, onOpenOrder }) {
  const [reload, setReload] = useState(0);
  const { data, loading, error } = useSection('/point/handover', true, tick + reload);
  const cashInfo = useSection('/point/cash', true, tick + reload);
  const [by, setBy] = useState(readName);
  const [cash, setCash] = useState('');
  const [checks, setChecks] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [saved, setSaved] = useState(false);

  const agbis = cashInfo.data?.balance;
  const passCount = notes.filter((n) => !n.done && n.due <= isoDay(1)).length;
  const pending = (data || []).find((r) => !r.accepted);
  const toggle = (item) => setChecks((c) => (c.includes(item) ? c.filter((x) => x !== item) : [...c, item]));
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr(''); setSaved(false);
    try {
      await api.post('/point/handover', { by, cash_counted: toNum(cash), checklist: checks });
      saveName(by);
      setCash(''); setChecks([]); setSaved(true);
      setReload((r) => r + 1);
    } catch (e2) { setErr(errText(e2, 'Не удалось сохранить.')); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5">
      {pending && <AcceptForm key={pending.id} rec={pending} people={people} onDone={() => setReload((r) => r + 1)} />}

      <NotesBoard notes={notes} reload={reloadNotes} people={people} onOpenOrder={onOpenOrder} />

      <form className="app-card p-5 space-y-4" onSubmit={submit}>
        <h3 className="pc-h3">Сдать смену</h3>
        <div className="pc-form-grid">
          <label htmlFor="ho-by">Кто сдаёт<NameInput id="ho-by" value={by} onChange={setBy} people={people} placeholder="Фамилия Имя" /></label>
          <label htmlFor="ho-cash">Пересчёт кассы, ₽
            <input id="ho-cash" className="input" inputMode="decimal" value={cash} onChange={(e) => setCash(e.target.value)} placeholder="0" />
          </label>
        </div>
        <div className="pc-muted">
          По Агбису сейчас: <b>{agbis != null ? money(agbis) : cashInfo.loading ? '…' : '—'}</b>
          {' '}<Diff counted={toNum(cash)} agbis={agbis} />
        </div>
        <fieldset className="pc-checks">
          <legend className="pc-muted">Проверено перед уходом</legend>
          {CHECKLIST.map((item) => (
            <label key={item} className="pc-check">
              <input type="checkbox" checked={checks.includes(item)} onChange={() => toggle(item)} />
              <span>{item}</span>
            </label>
          ))}
        </fieldset>
        <p className="pc-hint">
          {passCount
            ? `С передачей уйдут ${passCount} открытых заметок на сегодня и завтра — они в блоке «Что передать смене» выше.`
            : 'Открытых заметок на сегодня и завтра нет — если что-то нужно передать, добавьте выше.'}
        </p>
        {err && <p className="pc-error">{err}</p>}
        {saved && <p className="pc-ok">Записано. Следующий администратор увидит запись и подтвердит приём.</p>}
        <button type="submit" className="btn btn--primary" disabled={busy || by.trim().length < 2}>{busy ? 'Сохраняю…' : 'Смену сдал(а)'}</button>
      </form>

      <section className="space-y-2">
        <h3 className="pc-h3">Журнал</h3>
        {loading && !data && <p className="pc-muted">Загрузка…</p>}
        {error && <p className="pc-error">{error}</p>}
        {data && data.length === 0 && <div className="app-card p-6 text-sm text-[color:var(--color-muted-foreground)]">Записей пока нет.</div>}
        {data && data.length > 0 && (
          <div className="app-card pc-table-wrap">
            <table className="pc-table" style={{ minWidth: '52rem' }}>
              <thead><tr><th>Сдал(а)</th><th>Касса</th><th>Проверено</th><th>Передано</th><th>Принял(а)</th></tr></thead>
              <tbody>
                {data.map((r) => (
                  <tr key={r.id} style={{ cursor: 'default' }} className={r.accepted ? '' : 'is-pending'}>
                    <td style={{ whiteSpace: 'nowrap' }}><div><b>{r.by}</b></div><div className="pc-muted">{dayTime(r.at)}</div></td>
                    <td>
                      <div className="pc-num">{r.cash_counted != null ? money(r.cash_counted) : '—'}</div>
                      {r.cash_agbis != null && <div className="pc-muted">Агбис {money(r.cash_agbis)}</div>}
                      <Diff counted={r.cash_counted} agbis={r.cash_agbis} />
                    </td>
                    <td style={{ maxWidth: '15rem' }}><span className={`badge ${r.checklist.length === CHECKLIST.length ? 'badge--success' : 'badge--neutral'}`}>{r.checklist.length} из {CHECKLIST.length}</span>
                      {r.checklist.length < CHECKLIST.length && (
                        <div className="pc-muted">нет: {CHECKLIST.filter((x) => !r.checklist.includes(x)).join(', ').toLowerCase()}</div>
                      )}
                    </td>
                    <td style={{ minWidth: '16rem' }}>{(r.passed || []).length || r.notes ? <Passed rec={r} /> : <span className="pc-muted">—</span>}</td>
                    <td>
                      {r.accepted ? (
                        <>
                          <div><b>{r.accepted.by}</b></div>
                          <div className="pc-muted">{dayTime(r.accepted.at)}</div>
                          {r.accepted.cash_counted != null && (
                            <div className="pc-muted">пересчёт {money(r.accepted.cash_counted)}{' '}
                              <Diff counted={r.accepted.cash_counted} agbis={r.cash_counted ?? r.cash_agbis} />
                            </div>
                          )}
                          {r.accepted.comment && <div className="pc-warn-text">{r.accepted.comment}</div>}
                        </>
                      ) : <span className="badge badge--warning">не принята</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

/* ── раздел «Клиенты» ────────────────────────────────────────────── */
function Clients({ onOpenDoc }) {
  const [q, setQ] = useState('');
  const [list, setList] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [profile, setProfile] = useState(null);
  const [lk, setLk] = useState(null);

  const search = async (e) => {
    e?.preventDefault();
    if (q.trim().length < 2) return;
    setBusy(true); setErr(''); setProfile(null); setLk(null);
    try {
      const r = await api.get('/point/clients/search', { params: { q: q.trim() } });
      setList(r.data || []);
    } catch (e2) { setErr(errText(e2, 'Поиск не удался.')); } finally { setBusy(false); }
  };
  const open = async (c) => {
    setProfile({ loading: true, name: c.name }); setLk(null);
    try {
      const r = await api.get(`/point/clients/${c.contragent_id}`);
      setProfile(r.data);
    } catch (e2) { setProfile({ error: errText(e2, 'Не удалось открыть клиента.') }); }
  };
  const password = async () => {
    setLk({ loading: true });
    try {
      const r = await api.get('/point/clients-lk-password', { params: { phone: profile.phone } });
      setLk({ rows: r.data || [] });
    } catch (e2) { setLk({ error: errText(e2, 'Не удалось получить пароль.') }); }
  };

  return (
    <div className="pc-clients">
      <div className="space-y-3">
        <form className="flex gap-2" onSubmit={search}>
          <input className="input flex-1" placeholder="Фамилия, телефон или номер заказа" value={q}
            onChange={(e) => setQ(e.target.value)} aria-label="Поиск клиента" />
          <button type="submit" className="btn btn--primary" disabled={busy || q.trim().length < 2}>{busy ? '…' : 'Найти'}</button>
        </form>
        {err && <p className="pc-error">{err}</p>}
        {list && (list.length === 0
          ? <p className="pc-muted">Никого не нашли.</p>
          : (
            <div className="app-card pc-list">
              {list.map((c) => (
                <button key={c.contragent_id} type="button" className={`pc-list__row ${profile?.contragent_id === c.contragent_id ? 'is-on' : ''}`} onClick={() => open(c)}>
                  <b>{c.name || 'Без имени'}</b><span className="pc-phone">{c.phone || ''}</span>
                </button>
              ))}
            </div>
          ))}
      </div>
      <div>
        {!profile && <div className="app-card p-6 text-sm text-[color:var(--color-muted-foreground)]">Выберите клиента — здесь появится история его заказов.</div>}
        {profile?.loading && <p className="pc-muted">Загрузка…</p>}
        {profile?.error && <p className="pc-error">{profile.error}</p>}
        {profile && !profile.loading && !profile.error && (
          <div className="app-card p-5 space-y-4">
            <div>
              <h3 className="text-lg font-semibold">{profile.name}</h3>
              <div className="pc-phone">{profile.phone || 'телефон не указан'}</div>
              <div className="pc-muted mt-1">
                Заказов: {profile.order_count}{profile.first_order_date ? ` · с ${day(profile.first_order_date)}` : ''}
                {profile.last_order_date ? ` · последний ${day(profile.last_order_date)}` : ''}
              </div>
            </div>
            {profile.phone && (
              <div className="space-y-2">
                <button type="button" className="btn btn--secondary" onClick={password} disabled={lk?.loading}>
                  <KeyRound size={15} /> Пароль от личного кабинета
                </button>
                {lk?.error && <p className="pc-error">{lk.error}</p>}
                {lk?.rows && (lk.rows.length === 0
                  ? <p className="pc-muted">Личный кабинет по этому телефону не найден.</p>
                  : lk.rows.map((row, i) => (
                    <div key={i} className="pc-lk"><span className="pc-muted">{row.name || row.login || ''}</span><b>{row.password || 'пароль не восстанавливается — поможет сброс в ЛК'}</b></div>
                  )))}
              </div>
            )}
            <div>
              <div className="pc-h3 mb-2">Последние заказы</div>
              {(profile.orders || []).map((o) => (
                <button key={o.doc_num} type="button" className="pc-list__row" onClick={() => onOpenDoc(o.doc_num)}>
                  <b>{o.doc_num}</b><span className="pc-muted">{day(o.date)}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── раздел «База знаний» ────────────────────────────────────────── */
function Knowledge() {
  const { data, loading, error } = useSection('/point/kb', true, 0);
  const [doc, setDoc] = useState(null);
  const [q, setQ] = useState('');
  const [ask, setAsk] = useState(null);
  const [filter, setFilter] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    if (q.trim().length < 3) return;
    setAsk({ loading: true, q: q.trim() });
    try {
      const r = await api.post('/point/kb/ask', { question: q.trim() });
      setAsk({ q: q.trim(), answer: r.data.answer });
    } catch (e2) { setAsk({ q: q.trim(), error: errText(e2, 'Помощник сейчас недоступен.') }); }
  };
  const docs = (data || []).filter((d) => !filter || `${d.title} ${d.content}`.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="space-y-5">
      <form className="app-card p-5 space-y-3" onSubmit={submit}>
        <div className="flex items-center gap-2 font-semibold"><Sparkles size={16} style={{ color: 'var(--color-primary)' }} /> Спросить помощника</div>
        <div className="flex gap-2">
          <input className="input flex-1" value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Например: сколько стоит перекрасить замшевые сапоги в чёрный?" aria-label="Вопрос помощнику" />
          <button type="submit" className="btn btn--primary" disabled={ask?.loading || q.trim().length < 3}>{ask?.loading ? 'Думаю…' : 'Спросить'}</button>
        </div>
        {ask && !ask.loading && (
          <div className="pc-answer">
            <div className="pc-muted">Вопрос: {ask.q}</div>
            {ask.error ? <p className="pc-error">{ask.error}</p> : <p style={{ whiteSpace: 'pre-wrap' }}>{ask.answer}</p>}
          </div>
        )}
        <p className="pc-hint">Отвечает только по документам ниже. Если ответа в них нет — так и скажет.</p>
      </form>

      <div className="pc-kb">
        <div className="space-y-2">
          <input className="input w-full" placeholder="Поиск по документам" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Поиск по документам" />
          {loading && !data && <p className="pc-muted">Загрузка…</p>}
          {error && <p className="pc-error">{error}</p>}
          <div className="app-card pc-list">
            {docs.map((d) => (
              <button key={d.id} type="button" className={`pc-list__row ${doc?.id === d.id ? 'is-on' : ''}`} onClick={() => setDoc(d)}>
                <b>{d.title}</b><span className="pc-muted">{d.category}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="app-card p-5 pc-doc">
          {doc ? (
            <>
              <span className="ui-eyebrow">{doc.category}</span>
              <h3 className="text-xl font-semibold mt-2 mb-3">{doc.title}</h3>
              <div style={{ whiteSpace: 'pre-wrap' }}>{doc.content}</div>
            </>
          ) : <p className="text-sm text-[color:var(--color-muted-foreground)]">Выберите документ слева.</p>}
        </div>
      </div>
    </div>
  );
}

/* ── кабинет ─────────────────────────────────────────────────────── */
function Cabinet() {
  const [me, setMe] = useState(null);
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('today');
  const [tick, setTick] = useState(0);
  const [order, setOrder] = useState(null);
  const [notes, setNotes] = useState([]);
  const inputRef = useRef(null);
  useBackClose(!!order, () => setOrder(null));

  const load = useCallback((refresh = false) => {
    setLoading(true);
    setError('');
    api.get('/point/today', { params: refresh ? { refresh: 1 } : {} })
      .then((r) => setD(r.data))
      .catch((e) => setError(errText(e, 'Не удалось загрузить данные точки.')))
      .finally(() => setLoading(false));
  }, []);

  const loadNotes = useCallback(() => {
    api.get('/point/notes').then((r) => setNotes(r.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    api.get('/point/me').then((r) => setMe(r.data)).catch(() => {});
    load();
    loadNotes();
    // Экран висит на стойке весь день — обновляемся сами каждые 5 минут
    // (заметки — каждую минуту: их пишут с другого ПК той же точки).
    const t = window.setInterval(() => load(), 5 * 60 * 1000);
    const tn = window.setInterval(() => loadNotes(), 60 * 1000);
    return () => { window.clearInterval(t); window.clearInterval(tn); };
  }, [load, loadNotes]);

  // Ручной сканер печатает бирку как клавиатура: первая цифра возвращает
  // фокус в поле поиска, где бы ни был курсор.
  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey || !/^\d$/.test(e.key)) return;
      if (isEditable(document.activeElement) || document.documentElement.classList.contains('photo-open')) return;
      inputRef.current?.focus();
      inputRef.current?.select();
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, []);

  const lists = useMemo(() => {
    const ready = d?.ready || [];
    const due = d?.due || [];
    return {
      ready: ready.filter((r) => !r.stale),
      stale: ready.filter((r) => r.stale),
      toCall: ready.filter((r) => !r.stale && !r.call),
      due,
      dueToday: due.filter((r) => !(r.overdue_days > 0)),
      overdue: due.filter((r) => r.overdue_days > 0),
      notesNow: notes.filter((n) => !n.done && n.due <= isoDay(0)).length,
    };
  }, [d, notes]);
  const notesToday = notes.filter((n) => !n.done && n.due <= isoDay(0))
    .sort((a, b) => (a.due + a.created_at).localeCompare(b.due + b.created_at));
  const people = (d?.shift?.people || []).map((p) => p.name);

  const openDoc = async (docNum) => {
    try {
      const r = await api.get('/point/orders/find', { params: { q: docNum } });
      if (r.data.order_id) setOrder({ orderId: r.data.order_id });
    } catch { /* номер не нашёлся — ничего не открываем */ }
  };
  const refresh = () => { load(true); loadNotes(); setTick((t) => t + 1); };
  const shift = d?.shift;
  const [eyebrow, title, sub] = TITLES[tab];
  const openRow = (id) => setOrder({ orderId: id });

  return (
    <div className="app-shell pc-shell">
      <TopProgressBar active={loading} />
      <aside className="app-shell__sidebar is-open">
        <nav className="sidebar">
          <div className="sidebar__header">
            <div className="sidebar__badge">B</div>
            <div className="sidebar__title">
              <span className="sidebar__title-main">{me?.salon?.name || 'Точка'}</span>
              <span className="sidebar__title-sub">Кабинет точки{me?.device?.label ? ` · ${me.device.label}` : ''}</span>
            </div>
          </div>
          <div className="sidebar__sections">
            {SECTIONS.map((sec) => (
              <div key={sec.name} className="sidebar__section">
                <div className="sidebar__section-label">{sec.name}</div>
                <div className="sidebar__links">
                  {sec.items.map(({ key, label, icon: Icon, count }) => (
                    <button key={key} type="button" onClick={() => setTab(key)} aria-current={tab === key ? 'page' : undefined}
                      className={`sidebar__link ${tab === key ? 'is-active' : ''}`}>
                      <Icon size={16} strokeWidth={1.4} className="shrink-0" />
                      <span>{label}</span>
                      {count && d && count(lists) != null && <small className="pc-count">{count(lists)}</small>}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </nav>
      </aside>

      <div className="app-shell__main">
        <header className="app-shell__header">
          <div className="app-shell__brand pc-brand">
            <span>{me?.salon?.name || 'Кабинет точки'}</span>
            {shift && (shift.opened
              ? <span className="badge badge--success">Смена открыта · {shift.people.map((p) => `${p.name} ${hhmm(p.at)}`).join(', ')}</span>
              : <span className="badge badge--warning">Смену ещё не открыли в боте</span>)}
          </div>
          <div className="app-shell__user">
            {d?.generated_at && <span className="app-shell__user-name">данные на {hhmm(d.generated_at)}</span>}
            <button type="button" className="icon-button icon-button--ghost" onClick={refresh} disabled={loading} aria-label="Обновить">
              <RefreshCw size={18} className={loading ? 'emp-wip-spin' : ''} /><span>Обновить</span>
            </button>
          </div>
        </header>

        <main className="app-shell__content">
          <div className="space-y-5 max-w-6xl mx-auto pb-12">
            <div className="app-card pc-scan">
              <ScanBarcode size={20} aria-hidden="true" />
              <div className="pc-scan__field">
                <OrderSearch inputRef={inputRef} scanMode apiBase="/point" onOpen={(orderId, serviceId) => setOrder({ orderId, serviceId })} />
              </div>
            </div>

            <div>
              <span className="ui-eyebrow mb-3">{eyebrow}</span>
              <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)]">{title}</h2>
              <p className="text-sm text-[color:var(--color-muted-foreground)] mt-2 max-w-[70ch]">{sub}</p>
            </div>

            {['today', 'ready', 'due', 'stale'].includes(tab) && loading && !d && <p className="pc-muted">Загружаю заказы точки… первый раз это до 15 секунд.</p>}
            {['today', 'ready', 'due', 'stale'].includes(tab) && !loading && error && <p className="pc-error">{error}</p>}

            {d && tab === 'today' && (
              <>
                <div className="pc-kpis">
                  <StatCard icon={<Inbox size={18} />} label="Готово к выдаче" value={lists.ready.length}
                    sub={lists.toCall.length ? `${lists.toCall.length} ещё не звонили` : 'всем позвонили'} onClick={() => setTab('ready')} />
                  <StatCard icon={<AlarmClock size={18} />} label="Срок сегодня, не готово" value={lists.dueToday.length}
                    tone={lists.dueToday.length ? 'text-[color:var(--color-warning)]' : ''} sub="предупредить клиента" onClick={() => setTab('due')} />
                  <StatCard icon={<AlarmClock size={18} />} label="Просрочено" value={lists.overdue.length}
                    tone={lists.overdue.length ? 'text-[color:var(--color-danger)]' : ''}
                    sub={d.old_due_count ? `и ещё ${d.old_due_count} старше 60 дней` : 'за 60 дней'} onClick={() => setTab('due')} />
                  <StatCard icon={<Archive size={18} />} label="Долго лежат" value={lists.stale.length} sub="готовы больше 14 дней" onClick={() => setTab('stale')} />
                </div>
                {notesToday.length > 0 && (
                  <section className="app-card p-5 space-y-3">
                    <div className="pc-note-group__title">
                      <StickyNote size={16} style={{ color: 'var(--color-primary)' }} aria-hidden="true" />
                      <b>Заметки на сегодня</b><span className="badge badge--warning">{notesToday.length}</span>
                      <button type="button" className="pc-link" style={{ marginLeft: 'auto' }} onClick={() => setTab('handover')}>все заметки</button>
                    </div>
                    <ul className="pc-notes">
                      {notesToday.map((n) => <NoteRow key={n.id} n={n} onChanged={loadNotes} onOpenOrder={openRow} showDue={n.due < isoDay(0)} />)}
                    </ul>
                  </section>
                )}
                <h3 className="pc-h3">Позвонить сейчас <span className="badge badge--neutral">{lists.toCall.length}</span></h3>
                <p className="pc-hint">Готовые заказы без отметки звонка. Отметьте результат — строка уйдёт из списка.</p>
                <OrdersTable rows={lists.toCall.slice(0, 15)} kind="ready" onOpen={openRow} onMarked={() => load()}
                  empty="Всем клиентам с готовыми заказами уже позвонили." />
                {lists.dueToday.length > 0 && (
                  <>
                    <h3 className="pc-h3">Срок сегодня, а изделие не готово <span className="badge badge--warning">{lists.dueToday.length}</span></h3>
                    <OrdersTable rows={lists.dueToday} kind="due" onOpen={openRow} onMarked={() => load()} empty="" />
                  </>
                )}
              </>
            )}
            {d && tab === 'ready' && <OrdersTable rows={lists.ready} kind="ready" onOpen={openRow} onMarked={() => load()} empty="Готовых заказов на точке нет." />}
            {d && tab === 'due' && (
              <>
                {d.old_due_count > 0 && <p className="pc-hint">Просроченных больше чем на 60 дней ещё {d.old_due_count} — в список не входят.</p>}
                <OrdersTable rows={lists.due} kind="due" onOpen={openRow} onMarked={() => load()} empty="Просроченных и сегодняшних сроков нет." />
              </>
            )}
            {d && tab === 'stale' && <OrdersTable rows={lists.stale} kind="ready" onOpen={openRow} onMarked={() => load()} empty="Таких заказов нет." />}
            {tab === 'handover' && <Handover tick={tick} people={people} notes={notes} reloadNotes={loadNotes} onOpenOrder={openRow} />}
            {tab === 'cash' && <Cash tick={tick} />}
            {tab === 'accepted' && <Accepted tick={tick} onOpen={openRow} />}
            {tab === 'schedule' && <Schedule tick={tick} />}
            {tab === 'clients' && <Clients onOpenDoc={openDoc} />}
            {tab === 'kb' && <Knowledge />}
          </div>
        </main>
      </div>

      {order && (
        <div className="pc-drawer" role="dialog" aria-modal="true" aria-label="Карточка заказа">
          <div className="pc-drawer__backdrop" onClick={() => setOrder(null)} />
          <div className="pc-drawer__panel">
            <button type="button" className="icon-button pc-drawer__close" onClick={() => setOrder(null)} aria-label="Закрыть">
              <X size={18} />
            </button>
            <OrderNotes orderId={order.orderId} notes={notes} reload={loadNotes} people={people} />
            <OrderView key={`${order.orderId}-${order.serviceId || ''}`} orderId={order.orderId}
              highlightServiceId={order.serviceId || null} apiBase="/point" />
          </div>
        </div>
      )}
    </div>
  );
}

export default function PointCabinet() {
  const [hasToken, setHasToken] = useState(() => !!readToken());

  useEffect(() => {
    const onUnauth = () => {
      try { window.localStorage.removeItem(POINT_TOKEN_KEY); } catch { /* уже нет */ }
      setHasToken(false);
    };
    window.addEventListener('point-unauthorized', onUnauth);
    return () => window.removeEventListener('point-unauthorized', onUnauth);
  }, []);

  return hasToken ? <Cabinet /> : <Activate onDone={() => setHasToken(true)} />;
}
