import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MessageCircle, Phone, PhoneOff, RefreshCw, ScanBarcode, X } from 'lucide-react';
import api, { POINT_TOKEN_KEY } from '../api.js';
import { OrderSearch, OrderView } from './employee/WorkshopOrder.jsx';
import useBackClose from '../hooks/useBackClose.js';

/** Кабинет точки — открыт весь день на рабочем ПК салона (/admin/point).
 *
 *  Вход не по логину: ПК подключают один раз кодом из «Салонов», дальше
 *  браузер помнит ключ точки. Экран отвечает на вопросы смены: кто сегодня на
 *  точке, что готово к выдаче и кому ещё не позвонили, у кого срок сегодня, а
 *  изделие не готово, что давно лежит. Сканер бирок — сверху на любой вкладке:
 *  ручной сканер печатает бирку в поле и сразу открывает заказ. */

const TABS = [
  { key: 'today', label: 'Сегодня' },
  { key: 'ready', label: 'Выдача' },
  { key: 'due', label: 'Сроки' },
  { key: 'stale', label: 'Долго лежат' },
];
const CALL_RESULTS = [
  { key: 'reached', label: 'Дозвонилась', icon: Phone },
  { key: 'no_answer', label: 'Не ответил', icon: PhoneOff },
  { key: 'message', label: 'Написала', icon: MessageCircle },
];
const CALL_LABEL = { reached: 'дозвонилась', no_answer: 'не ответил', message: 'написала' };

function readToken() {
  try { return window.localStorage.getItem(POINT_TOKEN_KEY); } catch { return null; }
}

function money(n) {
  return `${Math.round(Number(n) || 0).toLocaleString('ru-RU')} ₽`;
}

function day(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
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
      <form className="pc-activate__card" onSubmit={submit}>
        <span className="pc-logo">B</span>
        <h1>Кабинет точки</h1>
        <p>Этот компьютер ещё не подключён. Попросите руководителя открыть «Салоны → ваша точка → Подключить компьютер» и введите код.</p>
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

/* ── строка заказа с отметкой звонка ────────────────────────────── */
function CallButtons({ row, onMarked }) {
  const [busy, setBusy] = useState(null);
  const mark = async (result) => {
    setBusy(result);
    try {
      await api.post(`/point/orders/${row.order_id}/call`, { result });
      onMarked();
    } catch {
      /* отметка не сохранилась — кнопка просто отпустится */
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="pc-calls">
      {CALL_RESULTS.map(({ key, label, icon: Icon }) => (
        <button key={key} type="button" className="pc-call" onClick={(e) => { e.stopPropagation(); mark(key); }}
          disabled={!!busy} title={label} aria-label={`${label}: ${row.doc_num}`}>
          <Icon size={14} aria-hidden="true" /><span>{label}</span>
        </button>
      ))}
    </div>
  );
}

function CallState({ call }) {
  if (!call) return <span className="pc-tag pc-tag--warn">не звонили</span>;
  return (
    <span className={`pc-tag ${call.result === 'reached' ? 'pc-tag--ok' : ''}`}>
      {CALL_LABEL[call.result] || call.result} · {dayTime(call.at)}
      {call.count > 1 ? ` · ${call.count}×` : ''}
    </span>
  );
}

function OrdersTable({ rows, kind, onOpen, onMarked, empty }) {
  if (!rows.length) return <p className="pc-empty">{empty}</p>;
  return (
    <div className="pc-table-wrap">
      <table className="pc-table">
        <thead>
          <tr>
            <th>Заказ</th>
            <th>Изделия</th>
            <th>Клиент</th>
            {kind === 'due' ? <th>Срок</th> : <th>Готов</th>}
            <th className="num">К оплате</th>
            <th>Звонок</th>
            <th aria-label="Отметить звонок" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.order_id} onClick={() => onOpen(r.order_id)} tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter') onOpen(r.order_id); }}>
              <td className="pc-num">{r.doc_num}{r.urgent && <span className="pc-tag pc-tag--bad">срочно</span>}</td>
              <td>{r.items.length ? r.items.join(', ') : '—'}</td>
              <td>
                <div>{r.client || '—'}</div>
                {r.phone && <div className="pc-phone">{r.phone}</div>}
              </td>
              {kind === 'due' ? (
                <td>
                  <div>{day(r.due)}</div>
                  {r.overdue_days > 0
                    ? <span className="pc-tag pc-tag--bad">просрочен {r.overdue_days} дн</span>
                    : <span className="pc-tag pc-tag--warn">сегодня</span>}
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

/* ── кабинет ─────────────────────────────────────────────────────── */
function Cabinet() {
  const [me, setMe] = useState(null);
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('today');
  const [order, setOrder] = useState(null);
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

  useEffect(() => {
    api.get('/point/me').then((r) => setMe(r.data)).catch(() => {});
    load();
    // Экран висит на стойке весь день — обновляемся сами каждые 5 минут.
    const t = window.setInterval(() => load(), 5 * 60 * 1000);
    return () => window.clearInterval(t);
  }, [load]);

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
    return {
      ready: ready.filter((r) => !r.stale),
      stale: ready.filter((r) => r.stale),
      toCall: ready.filter((r) => !r.stale && !r.call),
      due: d?.due || [],
      dueToday: (d?.due || []).filter((r) => !(r.overdue_days > 0)),
      overdue: (d?.due || []).filter((r) => r.overdue_days > 0),
    };
  }, [d]);

  const counts = { today: null, ready: lists.ready.length, due: lists.due.length, stale: lists.stale.length };
  const shift = d?.shift;

  return (
    <div className="pc">
      <header className="pc-bar">
        <span className="pc-logo">B</span>
        <div className="pc-bar__title">
          <b>{me?.salon?.name || 'Кабинет точки'}</b>
          {me?.device?.label && <span className="pc-muted">{me.device.label}</span>}
        </div>
        {shift && (shift.opened
          ? <span className="pc-tag pc-tag--ok">Смена открыта · {shift.people.map((p) => `${p.name} ${hhmm(p.at)}`).join(', ')}</span>
          : <span className="pc-tag pc-tag--warn">Смену ещё не открыли в боте</span>)}
        <div className="pc-bar__right">
          {d?.generated_at && <span className="pc-muted">данные на {hhmm(d.generated_at)}</span>}
          <button type="button" className="btn btn--secondary" onClick={() => load(true)} disabled={loading}>
            <RefreshCw size={15} className={loading ? 'emp-wip-spin' : ''} /> Обновить
          </button>
        </div>
      </header>

      <div className="pc-body">
        <nav className="pc-nav" aria-label="Разделы">
          {TABS.map((t) => (
            <button key={t.key} type="button" className={tab === t.key ? 'is-on' : ''} aria-pressed={tab === t.key}
              onClick={() => setTab(t.key)}>
              <span>{t.label}</span>
              {counts[t.key] != null && <small>{counts[t.key]}</small>}
            </button>
          ))}
        </nav>

        <main className="pc-main">
          <section className="pc-scan">
            <ScanBarcode size={20} aria-hidden="true" />
            <div className="pc-scan__field">
              <OrderSearch inputRef={inputRef} scanMode apiBase="/point" onOpen={(orderId, serviceId) => setOrder({ orderId, serviceId })} />
            </div>
          </section>

          {loading && !d && <p className="pc-muted">Загружаю заказы точки… первый раз это до 15 секунд.</p>}
          {!loading && error && <p className="pc-error">{error}</p>}

          {d && tab === 'today' && (
            <>
              <div className="pc-kpis">
                <button type="button" className="pc-kpi" onClick={() => setTab('ready')}>
                  <span>Готово к выдаче</span><b>{lists.ready.length}</b>
                  <small>{lists.toCall.length ? `${lists.toCall.length} ещё не звонили` : 'всем позвонили'}</small>
                </button>
                <button type="button" className={`pc-kpi ${lists.dueToday.length ? 'pc-kpi--warn' : ''}`} onClick={() => setTab('due')}>
                  <span>Срок сегодня, не готово</span><b>{lists.dueToday.length}</b><small>предупредить клиента</small>
                </button>
                <button type="button" className={`pc-kpi ${lists.overdue.length ? 'pc-kpi--bad' : ''}`} onClick={() => setTab('due')}>
                  <span>Просрочено</span><b>{lists.overdue.length}</b>
                  <small>{d.old_due_count ? `и ещё ${d.old_due_count} старше 60 дней` : 'за последние 60 дней'}</small>
                </button>
                <button type="button" className="pc-kpi" onClick={() => setTab('stale')}>
                  <span>Долго лежат</span><b>{lists.stale.length}</b><small>готовы больше 14 дней</small>
                </button>
              </div>

              <h2 className="pc-h2">Позвонить сейчас <small>{lists.toCall.length}</small></h2>
              <p className="pc-hint">Готовые заказы, по которым ещё нет отметки звонка. Отметьте результат — строка уйдёт из списка.</p>
              <OrdersTable rows={lists.toCall.slice(0, 15)} kind="ready" onOpen={(id) => setOrder({ orderId: id })}
                onMarked={() => load()} empty="Всем клиентам с готовыми заказами уже позвонили." />

              {lists.dueToday.length > 0 && (
                <>
                  <h2 className="pc-h2">Срок сегодня, а изделие не готово <small>{lists.dueToday.length}</small></h2>
                  <OrdersTable rows={lists.dueToday} kind="due" onOpen={(id) => setOrder({ orderId: id })}
                    onMarked={() => load()} empty="" />
                </>
              )}
            </>
          )}

          {d && tab === 'ready' && (
            <>
              <h2 className="pc-h2">Готово к выдаче <small>{lists.ready.length}</small></h2>
              <p className="pc-hint">Сначала те, кому ещё не звонили.</p>
              <OrdersTable rows={lists.ready} kind="ready" onOpen={(id) => setOrder({ orderId: id })}
                onMarked={() => load()} empty="Готовых заказов на точке нет." />
            </>
          )}
          {d && tab === 'due' && (
            <>
              <h2 className="pc-h2">Сроки: сегодня и просроченные <small>{lists.due.length}</small></h2>
              <p className="pc-hint">Заказ не готов, а срок выдачи сегодня или уже прошёл. Предупредите клиента до того, как он приедет.
                {d.old_due_count ? ` Старше 60 дней — ещё ${d.old_due_count}, в список не входят.` : ''}</p>
              <OrdersTable rows={lists.due} kind="due" onOpen={(id) => setOrder({ orderId: id })}
                onMarked={() => load()} empty="Просроченных и сегодняшних сроков нет." />
            </>
          )}
          {d && tab === 'stale' && (
            <>
              <h2 className="pc-h2">Долго лежат <small>{lists.stale.length}</small></h2>
              <p className="pc-hint">Готовы больше 14 дней назад и до сих пор не выданы. Напомните клиенту.</p>
              <OrdersTable rows={lists.stale} kind="ready" onOpen={(id) => setOrder({ orderId: id })}
                onMarked={() => load()} empty="Таких заказов нет." />
            </>
          )}
        </main>
      </div>

      {order && (
        <div className="pc-drawer" role="dialog" aria-modal="true" aria-label="Карточка заказа">
          <div className="pc-drawer__backdrop" onClick={() => setOrder(null)} />
          <div className="pc-drawer__panel">
            <button type="button" className="icon-button pc-drawer__close" onClick={() => setOrder(null)} aria-label="Закрыть">
              <X size={18} />
            </button>
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
