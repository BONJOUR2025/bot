import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, MessageSquare, ScanLine, Search, X } from 'lucide-react';
import api from '../../api.js';
import { PhotoViewer } from '../../components/OrderPhotos.jsx';
import WebScanner, { canScanInBrowser } from './WebScanner.jsx';
import { money, serviceTitle } from './masterFormat.js';

/** Поиск заказа (номер или бирка) и карточка заказа для старшего мастера,
 *  плюс отметка входа или выхода за мастера — когда приложение мастера её
 *  не даёт поставить (GET /workshop/orders/*, POST /workshop/scan/*). */

const workshopPhotoPath = (p) => `/workshop/photos/${p.id}/full?md5=${encodeURIComponent(p.md5)}`;

function when(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—'
    : d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function day(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function detail(err, fallback) {
  const d = err?.response?.data?.detail;
  return typeof d === 'string' ? d : fallback;
}

/** Строка поиска с кнопкой камеры: номер «37441-7», «37441» или бирка. */
export function OrderSearch({ onOpen }) {
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [choices, setChoices] = useState(null);
  const [camera, setCamera] = useState(false);
  const appScanner = typeof window !== 'undefined' && typeof window.BonjourApp?.scanBarcode === 'function';
  const canCamera = appScanner || canScanInBrowser();

  const search = useCallback(async (value) => {
    const text = String(value || '').trim();
    if (!text) return;
    setBusy(true);
    setError('');
    setChoices(null);
    try {
      const res = await api.get('/workshop/orders/find', { params: { q: text } });
      if (res.data.order_id) onOpen(res.data.order_id);
      else setChoices(res.data.choices || []);
    } catch (e) {
      setError(detail(e, 'Не удалось найти заказ.'));
    } finally {
      setBusy(false);
    }
  }, [onOpen]);

  useEffect(() => {
    const onScan = (event) => {
      const { value, cancelled } = event.detail || {};
      if (cancelled || !value) return;
      setQ(value);
      search(value);
    };
    window.addEventListener('bonjour-scan', onScan);
    return () => window.removeEventListener('bonjour-scan', onScan);
  }, [search]);

  const openCamera = () => {
    if (appScanner) window.BonjourApp.scanBarcode();
    else setCamera(true);
  };

  return (
    <div className="wo-search">
      {camera && <WebScanner onClose={() => setCamera(false)} />}
      <form className="wo-search__row" onSubmit={(e) => { e.preventDefault(); search(q); }}>
        <div className="wo-search__field">
          <Search size={16} aria-hidden="true" />
          <input
            className="input"
            inputMode="search"
            placeholder="Заказ 37441-7 или бирка"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Номер заказа или бирки"
          />
        </div>
        {canCamera && (
          <button type="button" className="icon-button" onClick={openCamera} aria-label="Сканировать бирку">
            <ScanLine size={18} />
          </button>
        )}
        <button type="submit" className="btn btn--primary" disabled={busy || !q.trim()}>
          {busy ? '…' : 'Найти'}
        </button>
      </form>
      {error && <p className="emp-page__error">{error}</p>}
      {choices && (
        <div className="wo-choices">
          <p className="ws-hint">С этим номером несколько заказов:</p>
          {choices.map((c) => (
            <button key={c.order_id} type="button" className="wo-choice" onClick={() => { setChoices(null); onOpen(c.order_id); }}>
              <b>{c.doc_num}</b>
              <span>{day(c.date)} · {c.accepted_at} · {c.status}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function LeadScanDialog({ service, action, masters, onClose, onDone }) {
  const lastIn = [...service.scans].reverse().find((s) => s.kind === 'in');
  const initial = action === 'out' && lastIn && masters.some((m) => m.master_uid === lastIn.master_uid)
    ? lastIn.master_uid : '';
  const [uid, setUid] = useState(initial);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!uid) { setPreview(null); return; }
    let alive = true;
    setError('');
    api.post('/workshop/scan/preview', { barcode: service.barcode, action, master_uid: Number(uid) })
      .then((r) => alive && setPreview(r.data))
      .catch((e) => alive && setError(detail(e, 'Не удалось проверить отметку.')));
    return () => { alive = false; };
  }, [uid, action, service.barcode]);

  const confirm = async () => {
    setBusy(true);
    setError('');
    try {
      const r = await api.post('/workshop/scan/confirm', { barcode: service.barcode, action, master_uid: Number(uid) });
      setResult(r.data);
      if (r.data.written?.length) onDone();
    } catch (e) {
      setError(detail(e, 'Не удалось поставить отметку.'));
    } finally {
      setBusy(false);
    }
  };

  const title = action === 'in' ? 'Вход за мастера' : 'Выход за мастера';
  const stepText = (preview?.steps || []).map((s) => (s === 'in' ? 'вход' : 'выход')).join(', затем ');

  return (
    <div className="modal-backdrop" role="dialog" aria-label={title} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-card wo-dialog">
        <div className="wo-dialog__head">
          <h3>{title}</h3>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Закрыть"><X size={18} /></button>
        </div>
        <p className="ws-sub"><b>{serviceTitle(service.name)}</b> · {money(service.kredit)}</p>

        {result ? (
          <div className="wo-result">
            {result.dry_run && <p className="ws-hint">Запись в Агбис сейчас выключена — это была проба, ничего не записано.</p>}
            {result.written?.length > 0 && (
              <p className="wo-ok">Записано в Агбис: {result.written.map((w) => (w.action === 'in' ? 'вход' : 'выход')).join(' и ')} за {result.master}.</p>
            )}
            {result.failed && <p className="emp-page__error">Не записано ({result.failed.action === 'in' ? 'вход' : 'выход'}): {result.failed.reason}</p>}
            {!result.allowed && result.blockers?.map((b) => <p key={b} className="emp-page__error">{b}</p>)}
            <button type="button" className="btn btn--primary" onClick={onClose}>Готово</button>
          </div>
        ) : (
          <>
            <label className="wo-label">
              За какого мастера
              <select className="input" value={uid} onChange={(e) => setUid(e.target.value)}>
                <option value="">— выберите мастера —</option>
                {masters.map((m) => <option key={m.master_uid} value={m.master_uid}>{m.name}</option>)}
              </select>
            </label>
            {error && <p className="emp-page__error">{error}</p>}
            {preview && (
              <div className="wo-check">
                {preview.blockers.map((b) => <p key={b} className="wo-block">✕ {b}</p>)}
                {preview.warnings.map((w) => <p key={w} className="wo-warn">! {w}</p>)}
                {preview.allowed && <p className="ws-hint">Будет поставлено: {stepText} — за {preview.master}. В истории Агбиса останется, что отметку поставил старший мастер.</p>}
                {preview.dry_run && <p className="ws-hint">Запись в Агбис сейчас выключена: получится только проба.</p>}
              </div>
            )}
            <div className="wo-dialog__actions">
              <button type="button" className="btn btn-secondary" onClick={onClose}>Отмена</button>
              <button type="button" className="btn btn--primary" disabled={!preview?.allowed || busy} onClick={confirm}>
                {busy ? 'Записываю…' : `Поставить ${action === 'in' ? 'вход' : 'выход'}`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/** Карточка заказа. */
export function OrderView({ orderId, onBack }) {
  const [o, setO] = useState(null);
  const [error, setError] = useState('');
  const [viewer, setViewer] = useState(null);
  const [masters, setMasters] = useState([]);
  const [dialog, setDialog] = useState(null);

  const load = useCallback(() => {
    setError('');
    api.get(`/workshop/orders/${orderId}`)
      .then((r) => setO(r.data))
      .catch((e) => setError(detail(e, 'Не удалось загрузить заказ.')));
  }, [orderId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get('/workshop/masters').then((r) => setMasters(r.data || [])).catch(() => setMasters([]));
  }, []);

  const due = o?.due_state === 'overdue' ? 'badge--error' : o?.due_state === 'today' ? 'badge--warning' : 'badge--neutral';

  return (
    <div className="wo">
      <button type="button" className="wo-back" onClick={onBack}><ArrowLeft size={16} /> Назад к цеху</button>
      {error && <p className="emp-page__error">{error}</p>}
      {!o && !error && <p className="emp-page__loading">Загрузка…</p>}
      {o && (
        <>
          <section className="emp-payout-item wo-head">
            <div className="emp-payout-item__top">
              <span className="emp-payout-item__amount">{o.doc_num}</span>
              <span className="emp-wip-badges">
                {o.urgent && <span className="badge badge--error">Срочный</span>}
                <span className="badge badge--neutral">{o.status}</span>
              </span>
            </div>
            <dl className="wo-facts">
              <div><dt>Принят</dt><dd>{when(o.accepted)} · {o.accepted_at}</dd></div>
              <div><dt>Срок выдачи</dt><dd>{o.due ? <span className={`badge ${due}`}>{when(o.due)}</span> : '—'}</dd></div>
              <div><dt>Где сейчас</dt><dd>{o.location || '—'}</dd></div>
              <div><dt>Сумма услуг</dt><dd>{money(o.kredit)}</dd></div>
            </dl>
            {o.note && <p className="ws-sub">Примечание: {o.note}</p>}
            {o.defects && <p className="ws-sub">Дефекты: {o.defects}</p>}
          </section>

          {o.items.map((it) => (
            <section key={it.item_id} className="wo-item">
              <h3 className="ws-section__title">{it.name}{it.location && <span className="ws-count">{it.location}</span>}</h3>
              {it.note && <p className="ws-sub">{it.note}</p>}
              {it.photos.length > 0 && (
                <div className="wo-photos">
                  {it.photos.map((p, i) => (
                    <button key={p.id} type="button" className="emp-wip-photo" onClick={() => setViewer({ photos: it.photos, index: i })}
                      aria-label={`Фото ${i + 1}`}>
                      {p.thumb ? <img src={p.thumb} alt="" /> : <span>фото</span>}
                    </button>
                  ))}
                </div>
              )}
              <div className="emp-list">
                {it.services.map((s) => (
                  <div key={s.service_id} className="emp-payout-item">
                    <div className="emp-payout-item__top">
                      <span className="wo-svc">{serviceTitle(s.name)}</span>
                      <span className="emp-wip-badges"><span className="badge badge--neutral">{s.status}</span></span>
                    </div>
                    <div className="emp-payout-item__details">
                      <span>{s.category}{s.post ? ` · ${s.post}` : ''}</span>
                      <span>{money(s.kredit)}</span>
                    </div>
                    {s.scans.length > 0 && (
                      <ul className="wo-scans">
                        {s.scans.map((x, i) => (
                          <li key={i}><b>{x.kind === 'in' ? 'Вход' : x.kind === 'out' ? 'Выход' : x.post}</b> · {x.master || '—'} · {when(x.date)}</li>
                        ))}
                      </ul>
                    )}
                    {s.comments.map((c, ci) => (
                      <div key={ci} className="emp-wip-note">
                        <MessageSquare size={14} aria-hidden="true" />
                        <span>{c.label && <em>{c.label}: </em>}{c.text}</span>
                      </div>
                    ))}
                    {s.moves.length > 0 && (
                      <p className="ws-sub">Накладные: {s.moves.map((m) => `${day(m.date)} ${m.from} → ${m.to} (${m.status})`).join('; ')}</p>
                    )}
                    {s.barcode && s.workshop_work && s.status_id !== 7 && (
                      <div className="wo-lead">
                        <button type="button" className="ui-chip" onClick={() => setDialog({ service: s, action: 'in' })}>Вход за мастера</button>
                        <button type="button" className="ui-chip" onClick={() => setDialog({ service: s, action: 'out' })}>Выход за мастера</button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          ))}
        </>
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
      {dialog && (
        <LeadScanDialog
          service={dialog.service}
          action={dialog.action}
          masters={masters}
          onClose={() => setDialog(null)}
          onDone={load}
        />
      )}
    </div>
  );
}
