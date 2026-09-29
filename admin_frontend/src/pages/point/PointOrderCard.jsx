import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle, CheckCircle2, ChevronDown, CircleDashed, Clock, MessageSquare, Phone, Wallet, XCircle,
} from 'lucide-react';
import api from '../../api.js';
import { PhotoViewer } from '../../components/OrderPhotos.jsx';
import { money, serviceTitle } from '../employee/masterFormat.js';

/** Карточка заказа для стойки (кабинет точки).
 *
 *  Отвечает сверху вниз на вопросы администратора: готов ли заказ и где
 *  лежит → кому отдать → сколько взять → что в заказе. Язык — человеческий,
 *  без терминов Агбиса («Исполненный», «Вход/Выход», папки услуг). Оплата,
 *  звонки, СМС и заметки — в раскрывающихся разделах, открыты только те,
 *  где есть что-то важное. Карточка цеха (старший мастер) — отдельная,
 *  WorkshopOrder.jsx, её это не касается. */

const photoPath = (p) => `/point/photos/${p.id}/full?md5=${encodeURIComponent(p.md5)}`;
const CALL_TEXT = { reached: 'дозвонились', no_answer: 'не ответил', message: 'написали в мессенджер' };

function when(iso, withTime = true) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('ru-RU', withTime
    ? { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }
    : { day: 'numeric', month: 'short', year: d.getFullYear() === new Date().getFullYear() ? undefined : 'numeric' });
}
function phoneText(p) {
  const d = String(p || '').replace(/\D/g, '');
  if (d.length === 11 && (d[0] === '7' || d[0] === '8')) {
    return `+7 ${d.slice(1, 4)} ${d.slice(4, 7)}-${d.slice(7, 9)}-${d.slice(9)}`;
  }
  return p || '';
}
function plural(n, one, few, many) {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

/** Где заказ в жизни, одной фразой — по статусу заказа Агбиса. */
function orderState(o) {
  switch (o.status_id) {
    case 4: return { tone: 'ready', title: 'Готов к выдаче', icon: CheckCircle2 };
    case 5: return { tone: 'done', title: 'Выдан клиенту', icon: CheckCircle2 };
    case 6: return { tone: 'done', title: 'Закрыт', icon: CheckCircle2 };
    case 7: return { tone: 'cancel', title: 'Отменён', icon: XCircle };
    default:
      return o.due_state === 'overdue'
        ? { tone: 'late', title: 'В работе — срок прошёл', icon: AlertTriangle }
        : { tone: 'work', title: 'В работе', icon: CircleDashed };
  }
}

/** Услуга по-человечески: готова / у мастера / ждёт мастера / отменена. */
function serviceState(s) {
  const outs = s.scans.filter((x) => x.kind === 'out');
  const ins = s.scans.filter((x) => x.kind === 'in');
  const who = (list) => list[list.length - 1]?.master;
  if (s.status_id === 7) return { tone: 'cancel', label: 'отменена', icon: XCircle };
  if (s.status_id === 5) return { tone: 'done', label: 'выдана', icon: CheckCircle2, who: who(outs) };
  if (s.status_id === 4 || s.status_id === 6 || outs.length) {
    return { tone: 'ready', label: 'готово', icon: CheckCircle2, who: who(outs) };
  }
  if (ins.length) return { tone: 'work', label: 'у мастера', icon: Clock, who: who(ins) };
  return { tone: 'wait', label: 'ещё не начата', icon: CircleDashed };
}

function Section({ title, icon: Icon, badge, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className={`poc-sec ${open ? 'is-open' : ''}`}>
      <button type="button" className="poc-sec__head" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        {Icon && <Icon size={16} aria-hidden="true" />}
        <span>{title}</span>
        {badge}
        <ChevronDown size={16} className="poc-sec__chev" aria-hidden="true" />
      </button>
      {open && <div className="poc-sec__body">{children}</div>}
    </section>
  );
}

export default function PointOrderCard({ orderId, highlightServiceId = null, notesSlot = null, openNotesCount = 0 }) {
  const [o, setO] = useState(null);
  const [error, setError] = useState('');
  const [viewer, setViewer] = useState(null);
  const hitRef = useRef(null);

  const load = useCallback(() => {
    setError('');
    api.get(`/point/orders/${orderId}`)
      .then((r) => setO(r.data))
      .catch((e) => {
        const d = e?.response?.data?.detail;
        setError(typeof d === 'string' ? d : 'Не удалось загрузить заказ.');
      });
  }, [orderId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (o && hitRef.current) hitRef.current.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [o]);

  if (error) return <p className="pc-error">{error}</p>;
  if (!o) return <p className="pc-muted">Загрузка заказа…</p>;

  const x = o.extras || {};
  const pay = x.payment;
  const state = orderState(o);
  const StateIcon = state.icon;
  const services = o.items.flatMap((it) => it.services);
  const active = services.filter((s) => s.status_id !== 7);
  const readyCount = active.filter((s) => ['ready', 'done'].includes(serviceState(s).tone)).length;
  const hist = x.client_history;
  const contacts = (x.calls?.length || 0) + (x.smses?.length || 0);

  return (
    <div className="poc">
      {/* ── что с заказом ── */}
      <header className={`poc-head poc-tone--${state.tone}`}>
        <div className="poc-head__top">
          <span className="poc-num">{o.doc_num}</span>
          {o.urgent && <span className="badge badge--error">Срочный</span>}
        </div>
        <div className="poc-state">
          <StateIcon size={22} aria-hidden="true" />
          <div>
            <b>{state.title}</b>
            <span>
              {o.status_id === 4 || o.status_id < 4 ? `Лежит: ${o.location || '—'}` : ''}
              {o.status_id < 4 && active.length > 0 ? ` · готово ${readyCount} из ${active.length}` : ''}
            </span>
          </div>
        </div>
      </header>

      {/* ── три главных ответа: кому, сколько, когда ── */}
      <div className="poc-keys">
        <div className="poc-key">
          <span className="poc-key__label">Клиент</span>
          {x.client ? (
            <>
              <b className="poc-key__value">{x.client.name || 'Без имени'}</b>
              {x.client.phone && <span className="poc-key__phone"><Phone size={13} aria-hidden="true" /> {phoneText(x.client.phone)}</span>}
              {hist && (
                <span className="poc-key__sub">
                  {hist.orders > 1 ? `постоянный · ${hist.orders} ${plural(hist.orders, 'заказ', 'заказа', 'заказов')}` : 'первый заказ'}
                </span>
              )}
            </>
          ) : <span className="poc-key__sub">не указан</span>}
        </div>
        <div className={`poc-key ${pay && pay.to_pay > 0 ? 'poc-key--due' : pay ? 'poc-key--ok' : ''}`}>
          <span className="poc-key__label">{pay && pay.to_pay > 0 ? 'Взять при выдаче' : 'Оплата'}</span>
          {pay ? (
            <>
              <b className="poc-key__value poc-key__money">{pay.to_pay > 0 ? money(pay.to_pay) : 'Оплачен'}</b>
              <span className="poc-key__sub">
                {pay.to_pay > 0 ? `из ${money(pay.total)} · внесено ${money(pay.paid)}` : `полностью, ${money(pay.total)}`}
              </span>
            </>
          ) : <span className="poc-key__sub">{money(o.kredit)}</span>}
        </div>
        <div className={`poc-key ${o.due_state === 'overdue' && o.status_id < 4 ? 'poc-key--due' : ''}`}>
          <span className="poc-key__label">Срок выдачи</span>
          <b className="poc-key__value">{o.due ? when(o.due) : '—'}</b>
          <span className="poc-key__sub">
            {o.status_id < 4 && o.due_state === 'overdue' ? `прошёл ${o.overdue_days || 0} дн назад`
              : o.due_state === 'today' ? 'сегодня' : o.due_state === 'tomorrow' ? 'завтра' : ''}
          </span>
        </div>
      </div>

      {/* ── важное при выдаче ── */}
      {(o.note || o.defects) && (
        <div className="poc-warn">
          <AlertTriangle size={16} aria-hidden="true" />
          <div>
            {o.note && <p><b>Примечание:</b> {o.note}</p>}
            {o.defects && <p><b>Дефекты при приёме:</b> {o.defects}</p>}
          </div>
        </div>
      )}

      {/* ── что в заказе ── */}
      <div className="poc-items">
        {o.items.map((it) => {
          const thumbs = it.photos.filter((p) => p.thumb).slice(0, 6);
          const more = it.photos.length - thumbs.length;
          return (
            <section key={it.item_id} className="poc-item" ref={it.item_id === highlightServiceId ? hitRef : undefined}>
              <div className="poc-item__head">
                <h3>{it.name}</h3>
                {it.item_id === highlightServiceId && <span className="badge badge--info">эта бирка</span>}
                {it.location && it.location !== o.location && <span className="poc-muted">лежит: {it.location}</span>}
              </div>
              {it.note && <p className="poc-item__note">{it.note}</p>}
              {it.photos.length > 0 && (
                <div className="poc-photos">
                  {thumbs.map((p, i) => (
                    <button key={p.id} type="button" onClick={() => setViewer({ photos: it.photos, index: i })} aria-label={`Фото ${i + 1}`}>
                      <img src={p.thumb} alt="" />
                    </button>
                  ))}
                  {more > 0 && (
                    <button type="button" className="poc-photos__more" onClick={() => setViewer({ photos: it.photos, index: thumbs.length })}>
                      +{more}
                    </button>
                  )}
                </div>
              )}
              <ul className="poc-services">
                {it.services.map((s) => {
                  const st = serviceState(s);
                  const Icon = st.icon;
                  const hit = s.service_id === highlightServiceId;
                  return (
                    <li key={s.service_id} ref={hit ? hitRef : undefined} className={`poc-svc poc-tone--${st.tone} ${hit ? 'is-hit' : ''}`}>
                      <Icon size={16} className="poc-svc__icon" aria-hidden="true" />
                      <div className="poc-svc__main">
                        <span className="poc-svc__name">{serviceTitle(s.name)}</span>
                        <span className="poc-svc__state">{st.label}{st.who ? ` · ${st.who}` : ''}{hit ? ' · эта бирка' : ''}</span>
                        {s.comments.map((c, i) => (
                          <span key={i} className="poc-svc__comment"><MessageSquare size={12} aria-hidden="true" /> {c.label ? `${c.label}: ` : ''}{c.text}</span>
                        ))}
                      </div>
                      <span className="poc-svc__price">{money(s.kredit)}</span>
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </div>

      {/* ── подробности по запросу ── */}
      {notesSlot && (
        <Section title="Заметки смене" icon={MessageSquare} defaultOpen={openNotesCount > 0}
          badge={openNotesCount > 0 ? <span className="badge badge--warning">{openNotesCount}</span> : null}>
          {notesSlot}
        </Section>
      )}
      {pay && (
        <Section title="Оплата и платежи" icon={Wallet}
          badge={x.payments?.length ? <span className="badge badge--neutral">{x.payments.length}</span> : null}>
          <dl className="poc-pay">
            <div><dt>Сумма заказа</dt><dd>{money(pay.total)}</dd></div>
            <div><dt>Внесено</dt><dd>{money(pay.paid)}</dd></div>
            <div className={pay.to_pay > 0 ? 'is-due' : 'is-ok'}><dt>{pay.to_pay > 0 ? 'К доплате' : 'Остаток'}</dt><dd>{pay.to_pay > 0 ? money(pay.to_pay) : 'нет'}</dd></div>
          </dl>
          {x.payments?.length ? (
            <ul className="poc-list">
              {x.payments.map((p, i) => (
                <li key={i}>
                  <b>{p.refund ? '−' : ''}{money(Math.abs(p.amount))}</b>
                  <span>{p.refund ? 'возврат' : p.kind}</span>
                  <span className="poc-muted">{when(p.at)}</span>
                </li>
              ))}
            </ul>
          ) : <p className="poc-muted">Платежей не было.</p>}
        </Section>
      )}
      <Section title="Звонки и СМС" icon={Phone}
        badge={contacts ? <span className="badge badge--neutral">{contacts}</span> : null}>
        {x.calls?.length ? (
          <ul className="poc-list">
            {x.calls.map((c, i) => (
              <li key={`c${i}`}><b>{CALL_TEXT[c.result] || c.result}</b><span className="poc-muted">{when(c.at)}</span>{c.note && <span>{c.note}</span>}</li>
            ))}
          </ul>
        ) : <p className="poc-muted">Звонков не отмечали.</p>}
        {x.smses?.length ? (
          <ul className="poc-list">
            {x.smses.map((m, i) => (
              <li key={`s${i}`}>
                <b>СМС</b><span className="poc-muted">{when(m.sent)} · {m.delivered ? 'доставлено' : 'не доставлено'}</span>
                {m.text && <span className="poc-list__text">{m.text}</span>}
              </li>
            ))}
          </ul>
        ) : <p className="poc-muted">СМС по заказу не отправлялись.</p>}
      </Section>
      <Section title="О заказе" icon={Clock}>
        <dl className="poc-pay">
          <div><dt>Принят</dt><dd>{when(o.accepted)} · {o.accepted_at || '—'}</dd></div>
          {x.accepted_by && <div><dt>Принял</dt><dd>{x.accepted_by}</dd></div>}
          <div><dt>Статус в Агбисе</dt><dd>{o.status}</dd></div>
          {hist?.previous && <div><dt>Прошлый заказ клиента</dt><dd>{hist.previous.doc_num} · {when(hist.previous.date, false)}</dd></div>}
          {hist?.first && hist.orders > 1 && <div><dt>Клиент с нами с</dt><dd>{when(hist.first, false)}</dd></div>}
        </dl>
      </Section>

      {viewer && (
        <PhotoViewer photos={viewer.photos} index={viewer.index}
          onIndex={(index) => setViewer((v) => (v ? { ...v, index } : v))}
          onClose={() => setViewer(null)} pathFor={photoPath} />
      )}
    </div>
  );
}
