import { useCallback, useEffect, useMemo, useState } from 'react';
import { MessageSquare, RefreshCw } from 'lucide-react';
import api from '../../api.js';
import { PhotoViewer } from '../../components/OrderPhotos.jsx';
import { money, serviceTitle, workshopPhotoPath } from './masterFormat.js';
import { OrderSearch, OrderView } from './WorkshopOrder.jsx';

/** Цех — приложение старшего мастера (GET /api/workshop/overview).
 *
 *  Отвечает на один вопрос: что в цехе требует внимания прямо сейчас.
 *  Только чтение Агбиса. Заработка мастеров здесь нет намеренно — старший
 *  мастер видит объём работы (штуки и стоимость услуг), а не чужую зарплату.
 *
 *  Вкладки: «Сейчас» (горит, зависло, никто не взял), «Мастера», «Сканы»
 *  (ошибки, из-за которых мастер теряет процент или отчёт врёт), «Ученики»,
 *  «Условия» (комментарии приёмщика к тому, что сейчас в работе). */

const TABS = [
  { key: 'now', label: 'Сейчас' },
  { key: 'advice', label: 'Кому дать' },
  { key: 'masters', label: 'Мастера' },
  { key: 'scans', label: 'Сканы' },
  { key: 'apprentices', label: 'Ученики' },
  { key: 'notes', label: 'Условия' },
];
const TAB_KEY = 'workshop.tab';
const STALE_DAYS = 7;
const PREVIEW = 6;

function hhmm(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function dayShort(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function dueBadge(it) {
  if (it.due_state === 'overdue') {
    return { cls: 'badge--error', label: it.overdue_days > 0 ? `Просрочен на ${it.overdue_days} дн` : `Просрочен с ${hhmm(it.due)}` };
  }
  if (it.due_state === 'today') return { cls: 'badge--warning', label: `Сегодня до ${hhmm(it.due)}` };
  if (it.due_state === 'tomorrow') return { cls: 'badge--info', label: `Завтра до ${hhmm(it.due)}` };
  return null;
}

// Время от входа до выхода — это не трудозатраты, а сколько изделие провело
// у мастера, вместе с ночами. Поэтому в часах и днях, а не в минутах.
function spanText(minutes) {
  if (minutes == null) return '—';
  if (minutes < 60) return `${minutes} мин`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.round(hours)} ч`;
  return `${(hours / 24).toFixed(1).replace('.', ',')} дн`;
}

function readTab() {
  try {
    const t = window.localStorage.getItem(TAB_KEY);
    return TABS.some((x) => x.key === t) ? t : 'now';
  } catch {
    return 'now';
  }
}

function errorText(err) {
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  if (status === 403) return 'Раздел «Цех» открыт только старшему мастеру. Доступ выдаёт руководитель.';
  if ((status === 503 || status === 504) && typeof detail === 'string') return detail;
  return 'Не удалось загрузить данные. Попробуйте ещё раз.';
}

/** Миниатюры изделия: нажатие открывает снимок во весь экран. */
function Thumbs({ photos, onPhoto }) {
  if (!photos?.length || !onPhoto) return null;
  return (
    <div className="ws-thumbs">
      {photos.map((p, i) => (
        <button key={p.id} type="button" className="emp-wip-photo" onClick={() => onPhoto(photos, i)}
          aria-label={`Фото ${i + 1}`}>
          {p.thumb ? <img src={p.thumb} alt="" /> : <span>фото</span>}
        </button>
      ))}
    </div>
  );
}

function Item({ it, extra, onOpenDoc, onPhoto }) {
  const due = dueBadge(it);
  const body = (
    <>
      <div className="emp-payout-item__top">
        <span className="emp-payout-item__amount">{it.doc_num}</span>
        <span className="emp-wip-badges">
          {due && <span className={`badge ${due.cls}`}>{due.label}</span>}
          {extra}
        </span>
      </div>
      <div className="emp-payout-item__details">
        <span>{serviceTitle(it.name)}</span>
        <span>{money(it.kredit)}</span>
      </div>
      {it.master && <div className="ws-sub">{it.master}{it.days > 0 ? ` · в работе ${it.days} дн` : ''}</div>}
    </>
  );
  return (
    <div className={`emp-payout-item${it.due_state === 'overdue' ? ' emp-wip-item--overdue' : ''}${it.due_state === 'today' ? ' emp-wip-item--today' : ''}`}>
      {onOpenDoc
        ? <button type="button" className="ws-advice__open" onClick={() => onOpenDoc(it.doc_num)}>{body}</button>
        : body}
      <Thumbs photos={it.photos} onPhoto={onPhoto} />
    </div>
  );
}

function Section({ title, count, children, empty }) {
  return (
    <section className="ws-section">
      <h3 className="ws-section__title">
        {title}{count != null && <span className="ws-count">{count}</span>}
      </h3>
      {count === 0 ? <p className="emp-page__empty">{empty}</p> : children}
    </section>
  );
}

function Limited({ items, render, step = PREVIEW }) {
  const [shown, setShown] = useState(step);
  return (
    <>
      <div className="emp-list">{items.slice(0, shown).map(render)}</div>
      {items.length > shown && (
        <button type="button" className="ws-more" onClick={() => setShown((n) => n + step * 3)}>
          Показать ещё {Math.min(items.length - shown, step * 3)} из {items.length - shown}
        </button>
      )}
    </>
  );
}

function NowTab({ d, onOpenDoc, onPhoto }) {
  const burning = d.wip.filter((it) => ['overdue', 'today', 'tomorrow'].includes(it.due_state));
  const stale = d.wip.filter((it) => (it.days || 0) >= STALE_DAYS && !['overdue', 'today'].includes(it.due_state))
    .sort((a, b) => (b.days || 0) - (a.days || 0));
  const queueByPoint = useMemo(() => {
    const groups = {};
    for (const q of d.queue || []) (groups[q.point] ||= []).push(q);
    return groups;
  }, [d.queue]);
  const total = d.wip.reduce((s, it) => s + (Number(it.kredit) || 0), 0);
  const overdue = d.wip.filter((it) => it.due_state === 'overdue').length;
  const today = d.wip.filter((it) => it.due_state === 'today').length;

  return (
    <>
      <div className="emp-earn-tiles ws-tiles">
        <div className="emp-earn-tile"><span>В работе</span><b>{d.wip.length}</b><small>{money(total)}</small></div>
        <div className={`emp-earn-tile${overdue ? ' ws-tile--bad' : ''}`}><span>Просрочено</span><b>{overdue}</b><small>по сроку выдачи</small></div>
        <div className={`emp-earn-tile${today ? ' ws-tile--warn' : ''}`}><span>Сдать сегодня</span><b>{today}</b><small>ещё не просрочено</small></div>
        <div className="emp-earn-tile"><span>Никто не взял</span><b>{d.queue ? d.queue.length : '—'}</b><small>без скана входа</small></div>
      </div>

      <Section title="Горит" count={burning.length} empty="Ничего не горит: просроченных и на сегодня-завтра нет.">
        <Limited items={burning} render={(it) => <Item key={it.service_id} it={it} onOpenDoc={onOpenDoc} />} />
      </Section>

      <Section
        title="Никто не взял"
        count={d.queue ? d.queue.length : null}
        empty="Всё, что лежит в местах ремонта, уже у мастеров."
      >
        {!d.queue && <p className="emp-page__error">Очередь сейчас не получена — Агбис не ответил.</p>}
        <p className="ws-hint">Заказ в исполнении, изделие лежит в месте ремонта, а скана входа нет ни у кого.</p>
        {Object.entries(queueByPoint).map(([point, items]) => (
          <div key={point} className="ws-group">
            <h4 className="ws-group__title">{point} <span className="ws-count">{items.length}</span></h4>
            <Limited
              items={items}
              step={4}
              render={(q) => (
                <Item
                  key={q.service_id}
                  it={q}
                  onOpenDoc={onOpenDoc}
                  onPhoto={onPhoto}
                  extra={q.waiting_days != null && <span className="badge badge--neutral">ждёт {q.waiting_days} дн</span>}
                />
              )}
            />
          </div>
        ))}
      </Section>

      <Section title={`Зависли ${STALE_DAYS}+ дней`} count={stale.length} empty="Зависших нет.">
        <Limited items={stale} render={(it) => <Item key={it.service_id} it={it} onOpenDoc={onOpenDoc} />} />
      </Section>
    </>
  );
}

function MastersTab({ d, onOpenDoc }) {
  const [open, setOpen] = useState(null);
  return (
    <div className="emp-list">
      {d.masters.map((m) => {
        const theirs = d.wip.filter((it) => it.master_uid === m.master_uid);
        const isOpen = open === m.master_uid;
        return (
          <div key={m.master_uid} className="emp-payout-item ws-master">
            <button type="button" className="ws-master__head" onClick={() => setOpen(isOpen ? null : m.master_uid)}
              aria-expanded={isOpen}>
              <span className="ws-master__name">
                {m.name}
                {m.position && <small>{m.position}</small>}
              </span>
              {m.on_shift == null ? null : m.on_shift
                ? <span className="badge badge--success">на смене с {hhmm(m.shift_from)}</span>
                : <span className="badge badge--neutral">не отмечался</span>}
            </button>
            <dl className="ws-stats">
              <div><dt>В работе</dt><dd>{m.wip}{m.overdue > 0 && <em className="ws-bad"> · {m.overdue} проср.</em>}</dd></div>
              <div><dt>Сегодня</dt><dd>{m.today}</dd></div>
              <div><dt>7 дней</dt><dd>{m.week}</dd></div>
              <div><dt>Месяц</dt><dd>{m.month}<small>{money(m.month_sum)}</small></dd></div>
              <div><dt title="Медиана от входа до выхода, без услуг короче 15 минут">Время у мастера</dt><dd>{spanText(m.median_min)}</dd></div>
              <div><dt>Ошибки сканов</dt><dd className={m.issues ? 'ws-bad' : ''}>{m.issues}{m.fast > 0 && <small>быстрых {m.fast}</small>}</dd></div>
            </dl>
            {isOpen && (
              <div className="ws-master__wip">
                {theirs.length === 0 ? <p className="emp-page__empty">В работе ничего нет.</p>
                  : <div className="emp-list">{theirs.map((it) => <Item key={it.service_id} it={{ ...it, master: null }} onOpenDoc={onOpenDoc} />)}</div>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

const ISSUE_KINDS = [
  { key: 'no_out', label: 'Вход без выхода', hint: 'Заказ уже готов или выдан, а выхода нет — процент мастеру не начислится.' },
  { key: 'no_in', label: 'Выход без входа', hint: 'Работа засчитана без скана входа — время работы неизвестно.' },
  { key: 'mismatch', label: 'Разные мастера', hint: 'Вход сканировал один мастер, выход — другой: процент получит тот, кто сканировал выход.' },
  { key: 'multi', label: 'Повторные сканы', hint: 'Несколько входов или выходов по одной бирке.' },
];

function ScansTab({ d }) {
  const monthStart = useMemo(() => {
    const n = new Date();
    return new Date(n.getFullYear(), n.getMonth(), 1);
  }, []);
  const [period, setPeriod] = useState('month');
  const [kind, setKind] = useState('no_out');
  const inPeriod = d.scan_issues.filter((i) => {
    const t = new Date(i.when);
    return period === 'month' ? t >= monthStart : t < monthStart;
  });
  const counts = Object.fromEntries(ISSUE_KINDS.map((k) => [k.key, inPeriod.filter((i) => i.kind === k.key).length]));
  const list = inPeriod.filter((i) => i.kind === kind);
  const current = ISSUE_KINDS.find((k) => k.key === kind);

  return (
    <>
      <div className="ws-toolbar">
        <div className="emp-earn-periods" role="group" aria-label="Период">
          <button type="button" aria-pressed={period === 'month'} onClick={() => setPeriod('month')}>Этот месяц</button>
          <button type="button" aria-pressed={period === 'prev'} onClick={() => setPeriod('prev')}>Прошлый</button>
        </div>
      </div>
      <div className="ws-chips">
        {ISSUE_KINDS.map((k) => (
          <button key={k.key} type="button" className={`ui-chip ${kind === k.key ? 'is-active' : ''}`}
            aria-pressed={kind === k.key} onClick={() => setKind(k.key)}>
            {k.label}<span className="rf-chip__n">{counts[k.key]}</span>
          </button>
        ))}
      </div>
      <p className="ws-hint">{current.hint}</p>
      {list.length === 0 ? <p className="emp-page__empty">За этот период таких нет.</p> : (
        <Limited
          items={list}
          render={(i) => (
            <div key={`${i.kind}-${i.service_id}`} className="emp-payout-item">
              <div className="emp-payout-item__top">
                <span className="emp-payout-item__amount">{i.doc_num}</span>
                <span className="emp-wip-badges"><span className="badge badge--neutral">{dayShort(i.when)}</span></span>
              </div>
              <div className="emp-payout-item__details">
                <span>{serviceTitle(i.name)}</span>
                <span>{money(i.kredit)}</span>
              </div>
              <div className="ws-sub"><b>{i.master || 'мастер не указан'}</b>{i.kind === 'no_out' ? ` · ${i.label.toLowerCase()}` : ''}</div>
              {i.detail && <div className="ws-sub">{i.detail}</div>}
            </div>
          )}
        />
      )}
      {d.fast_scans_month > 0 && (
        <p className="ws-hint">
          Ещё {d.fast_scans_month} сканов за месяц — вход и выход меньше чем за 3 минуты. Отдельным списком их
          не показываем, по мастерам они видны во вкладке «Мастера» («быстрых»).
        </p>
      )}
    </>
  );
}

function ApprenticesTab({ d, onChanged }) {
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState('');
  if (!d.apprentices) return <p className="emp-page__error">Список учеников сейчас не получен.</p>;
  if (d.apprentices.length === 0) return <p className="emp-page__empty">Учеников нет.</p>;
  const todayIso = new Date().toLocaleDateString('sv-SE');

  const markToday = async (a) => {
    setBusy(a.employee_id);
    setErr('');
    try {
      await api.post(`/workshop/apprentices/${a.employee_id}/attendance`, { date: todayIso });
      onChanged();
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Не удалось отметить.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      {err && <p className="emp-page__error">{err}</p>}
      <div className="emp-list">
        {d.apprentices.map((a) => (
          <div key={a.employee_id} className="emp-payout-item">
            <div className="emp-payout-item__top">
              <span className="emp-payout-item__amount ws-name">{a.name}</span>
              <span className="emp-wip-badges">
                {a.today ? <span className="badge badge--success">сегодня в цеху</span>
                  : <span className="badge badge--neutral">сегодня нет отметки</span>}
              </span>
            </div>
            <div className="emp-payout-item__details">
              <span>Дней обучения в этом месяце</span>
              <span>{a.days_count}</span>
            </div>
            {!a.today && (
              <button type="button" className="ws-mark" disabled={busy === a.employee_id} onClick={() => markToday(a)}>
                {busy === a.employee_id ? 'Отмечаю…' : 'Был сегодня, но без пропуска — отметить'}
              </button>
            )}
          </div>
        ))}
      </div>
      <p className="ws-hint">Дни считаются по турникету. Ручная отметка — для дня, когда ученик был, но не прошёл через турникет.</p>
    </>
  );
}

function NotesTab({ d }) {
  const withNotes = d.wip.filter((it) => (it.comments || []).length > 0);
  if (withNotes.length === 0) return <p className="emp-page__empty">В том, что сейчас в работе, комментариев приёмщика нет.</p>;
  return (
    <>
      <p className="ws-hint">Комментарии приёмщика к тому, что сейчас в работе, — отсюда чаще всего и берутся переделки.</p>
      <Limited
        items={withNotes}
        render={(it) => (
          <div key={it.service_id}>
            <Item it={it} />
            <div className="emp-wip-notes">
              {it.comments.map((c, ci) => (
                <div key={ci} className="emp-wip-note">
                  <MessageSquare size={14} aria-hidden="true" />
                  <span>{c.label && <em>{c.label}: </em>}{c.text}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      />
    </>
  );
}

function AdviceTab({ d, onOpenDoc, onPhoto }) {
  const a = d.advice;
  if (!a) return <p className="emp-page__error">Совет сейчас не собран — Агбис не ответил. Обновите через минуту.</p>;
  return (
    <>
      <p className="ws-hint">
        Ремонт обуви, который лежит в цехе и который никто не взял: заказ принят на Бестужевской, привезён
        по накладной или это курьерский заказ, числящийся в цехе. Одна пара — одному мастеру. Сначала самые срочные; каждому достаётся тот, у кого меньше
        всего работы в днях (сколько в работе ÷ сколько сдаёт за день) из тех, кто делал такую работу
        {a.only_on_shift ? ' и сегодня на смене' : ''}. Советуем только мастеров по ремонту: химчистка и
        индивидуальный пошив — другая работа и другие люди.
      </p>
      <div className="ws-loads">
        {a.masters.filter((m) => !a.only_on_shift || m.on_shift).map((m) => (
          <div key={m.master_uid} className="ws-load">
            <b>{m.name.split(' ').slice(0, 2).join(' ')}</b>
            {m.position && <span className="ws-load__pos">{m.position}</span>}
            <span>в работе {m.wip} · ~{m.per_day}/день</span>
            <span>очередь {String(m.backlog_days).replace('.', ',')} дн{m.planned ? ` · +${m.planned} по совету` : ''}</span>
          </div>
        ))}
      </div>
      <Section title="Кому дать" count={a.queue.length} empty="Весь ремонт обуви в цехе уже у мастеров.">
        <Limited
          items={a.queue}
          render={(q) => (
            <div key={q.item_id} className="emp-payout-item ws-advice">
              <button type="button" className="ws-advice__open" onClick={() => onOpenDoc(q.doc_num)}>
                <div className="emp-payout-item__top">
                  <span className="emp-payout-item__amount">{q.doc_num}</span>
                  <span className="emp-wip-badges">
                    {dueBadge(q) && <span className={`badge ${dueBadge(q).cls}`}>{dueBadge(q).label}</span>}
                    {q.urgent && <span className="badge badge--error">Срочно</span>}
                  </span>
                </div>
                <div className="emp-payout-item__details">
                  <span>{serviceTitle(q.main)}{q.services.length > 1 ? ` + ещё ${q.services.length - 1}` : ''}</span>
                  <span>{money(q.kredit)}</span>
                </div>
                <div className="ws-sub">{q.how}{q.waiting_days != null ? ` · ждёт ${q.waiting_days} дн` : ''}</div>
              </button>
              <Thumbs photos={q.photos} onPhoto={onPhoto} />
              {q.recommended ? (
                <div className="ws-advice__rec">
                  <span>Дать: <b>{q.recommended.name}</b></span>
                  <small>{q.recommended.reason}</small>
                  {q.alternatives.length > 0 && (
                    <small>Или: {q.alternatives.map((x) => `${x.name.split(' ').slice(0, 2).join(' ')} (очередь ${String(x.backlog_days).replace('.', ',')} дн)`).join(', ')}</small>
                  )}
                </div>
              ) : <p className="ws-sub">Некому посоветовать: нет мастеров с опытом ремонта обуви на смене.</p>}
            </div>
          )}
        />
      </Section>
    </>
  );
}

export default function EmployeeWorkshop() {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState(readTab);
  // Открытая карточка заказа: поверх вкладок, «Назад» возвращает к цеху.
  const [orderId, setOrderId] = useState(null);
  const [openError, setOpenError] = useState('');
  // Снимок изделия во весь экран — прямо из списка, не заходя в карточку.
  const [viewer, setViewer] = useState(null);
  const openPhoto = useCallback((photos, index) => setViewer({ photos, index }), []);

  const openDoc = useCallback((docNum) => {
    setOpenError('');
    api.get('/workshop/orders/find', { params: { q: docNum } })
      .then((r) => { if (r.data.order_id) setOrderId(r.data.order_id); })
      .catch(() => setOpenError(`Заказ ${docNum} не открылся — попробуйте найти его поиском.`));
  }, []);

  const load = useCallback((refresh = false) => {
    setLoading(true);
    setError('');
    api.get('/workshop/overview', refresh ? { params: { refresh: 1 } } : undefined)
      .then((res) => setD(res.data))
      .catch((err) => setError(errorText(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const pickTab = (key) => {
    setTab(key);
    try { window.localStorage.setItem(TAB_KEY, key); } catch { /* вкладка просто не запомнится */ }
  };

  if (orderId) {
    return (
      <div className="emp-page">
        <OrderView orderId={orderId} onBack={() => setOrderId(null)} />
      </div>
    );
  }

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">Цех</h2>
        <button type="button" className="icon-button" onClick={() => load(true)} disabled={loading} aria-label="Обновить">
          <RefreshCw size={18} className={loading ? 'emp-wip-spin' : ''} />
        </button>
      </div>
      <OrderSearch onOpen={setOrderId} />
      {openError && <p className="emp-page__error">{openError}</p>}
      <div className="ws-tabs" role="tablist" aria-label="Разделы цеха">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key}
            className={tab === t.key ? 'is-active' : ''} onClick={() => pickTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {loading && !d && <p className="emp-page__loading">Загрузка…</p>}
      {!loading && error && <p className="emp-page__error">{error}</p>}
      {d && (
        <div style={loading ? { opacity: 0.6 } : undefined} aria-busy={loading}>
          <p className="ws-updated">Обновлено в {hhmm(d.generated_at)}</p>
          {tab === 'now' && <NowTab d={d} onOpenDoc={openDoc} onPhoto={openPhoto} />}
          {tab === 'advice' && <AdviceTab d={d} onOpenDoc={openDoc} onPhoto={openPhoto} />}
          {tab === 'masters' && <MastersTab d={d} onOpenDoc={openDoc} />}
          {tab === 'scans' && <ScansTab d={d} />}
          {tab === 'apprentices' && <ApprenticesTab d={d} onChanged={() => load(true)} />}
          {tab === 'notes' && <NotesTab d={d} />}
        </div>
      )}
      {viewer && (
        <PhotoViewer
          photos={viewer.photos}
          index={viewer.index}
          onIndex={(index) => setViewer((v) => (v ? { ...v, index } : v))}
          onClose={() => setViewer(null)}
          pathFor={workshopPhotoPath}
        />
      )}
    </div>
  );
}
