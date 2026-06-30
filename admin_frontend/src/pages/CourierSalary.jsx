import { useEffect, useMemo, useState, useCallback } from 'react';
import { Truck, RefreshCw, Wallet, Banknote, Trash2, CheckCircle2, Gauge, Save, RotateCw } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

const COURIER_MATCH = 'курьер';
const MONTHS_RU = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
const fmtMoney = (v) => (v === null || v === undefined ? '—' : `${Number(v).toLocaleString('ru-RU')} ₽`);
const fmtKm = (v) => (v === null || v === undefined ? '—' : `${Number(v).toLocaleString('ru-RU')} км`);
const lastDay = (ym) => { const [y, m] = ym.split('-').map(Number); return new Date(y, m, 0).getDate(); };

function recentMonths(n = 12) {
  const out = [];
  const d = new Date();
  for (let i = 0; i < n; i++) {
    const y = d.getFullYear(), m = d.getMonth();
    out.push({ value: `${y}-${String(m + 1).padStart(2, '0')}`, label: `${MONTHS_RU[m]} ${y}` });
    d.setMonth(m - 1);
  }
  return out;
}

const TONE = {
  success: 'text-[color:var(--color-success)]', primary: 'text-[color:var(--color-primary)]',
  danger: 'text-[color:var(--color-danger)]', muted: 'text-[color:var(--color-muted-foreground)]',
};

function Term({ op, label, value, tone, strong }) {
  return (
    <div className="inline-flex items-center gap-2 whitespace-nowrap">
      {op && <span className="text-[color:var(--color-muted-foreground)] text-base font-medium select-none">{op}</span>}
      <div>
        <div className="text-[10px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">{label}</div>
        <div className={`tabular-nums font-semibold ${strong ? 'text-lg' : 'text-base'} ${tone || ''}`}>{fmtMoney(value)}</div>
      </div>
    </div>
  );
}

export default function CourierSalary() {
  const { toast } = useToast();
  const months = useMemo(() => recentMonths(12), []);
  const [employees, setEmployees] = useState([]);
  const [courierId, setCourierId] = useState('');
  const [period, setPeriod] = useState(months[0].value);

  const [plan, setPlan] = useState(null);
  const [planDraft, setPlanDraft] = useState({ oklad: 0, starline_device_id: '' });
  const [advances, setAdvances] = useState(null);
  const [incentives, setIncentives] = useState({ bonuses: 0, penalties: 0 });
  const [mileage, setMileage] = useState(null);
  const [mileageDraft, setMileageDraft] = useState({ odometer_start: '', odometer_end: '' });
  const [track, setTrack] = useState(null);
  const [polling, setPolling] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [accruing, setAccruing] = useState(false);
  const [payingId, setPayingId] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [starline, setStarline] = useState(null);
  const [accruals, setAccruals] = useState([]);
  const [tick, setTick] = useState(0);

  const couriers = useMemo(
    () => employees.filter((e) => (e.position || '').toLowerCase().includes(COURIER_MATCH)),
    [employees]);
  const courier = useMemo(() => couriers.find((e) => String(e.id) === String(courierId)), [couriers, courierId]);
  const dateFrom = `${period}-01`;
  const dateTo = `${period}-${String(lastDay(period)).padStart(2, '0')}`;
  const periodLabel = months.find((m) => m.value === period)?.label || period;

  useEffect(() => {
    api.get('employees/', { params: { archived: false } })
      .then((r) => setEmployees((r.data || []).filter((e) => e.status !== 'inactive')))
      .catch(() => {});
    api.get('courier-salary/starline/status').then((r) => setStarline(r.data)).catch(() => setStarline(null));
  }, []);

  const load = useCallback(async () => {
    if (!courierId) { setResult(null); setPlan(null); setMileage(null); setAdvances(null); return; }
    setLoading(true);
    try {
      const [pl, adv, inc, mil] = await Promise.all([
        api.get('courier-salary/plan', { params: { employee_code: courierId, period } }).then((r) => r.data),
        api.get('courier-salary/advances', { params: { employee_id: courierId } }).then((r) => r.data).catch(() => ({ total: 0 })),
        api.get('incentives/', { params: { employee_id: courierId, date_from: dateFrom, date_to: dateTo } }).then((r) => r.data).catch(() => []),
        api.get('courier-salary/mileage', { params: { employee_code: courierId, period } }).then((r) => r.data).catch(() => null),
      ]);
      const bonuses = (inc || []).filter((i) => i.type === 'bonus').reduce((s, i) => s + (Number(i.amount) || 0), 0);
      const penalties = (inc || []).filter((i) => i.type === 'penalty').reduce((s, i) => s + (Number(i.amount) || 0), 0);
      setPlan(pl); setPlanDraft({ oklad: pl.oklad || 0, starline_device_id: pl.starline_device_id || '' });
      setAdvances(adv); setIncentives({ bonuses, penalties });
      setMileage(mil); setMileageDraft({ odometer_start: mil?.odometer_start ?? '', odometer_end: mil?.odometer_end ?? '' });
      api.get('courier-salary/track/status', { params: { employee_code: courierId, period } }).then((r) => setTrack(r.data)).catch(() => setTrack(null));
      const res = await api.post('courier-salary/calc', {
        oklad: pl.oklad, advances: adv?.total || 0, bonuses, penalties,
      }).then((r) => r.data);
      setResult(res);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [courierId, period, dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (courierId) api.get('courier-salary/accruals', { params: { employee_code: courierId, limit: 50 } }).then((r) => setAccruals(r.data || [])).catch(() => {}); else setAccruals([]); }, [courierId, tick]);

  async function savePlan() {
    try {
      await api.put('courier-salary/plan', { employee_code: String(courierId), period, oklad: Number(planDraft.oklad) || 0, starline_device_id: planDraft.starline_device_id || '' });
      toast('Оклад сохранён', 'success'); load();
    } catch { toast('Ошибка сохранения', 'error'); }
  }

  async function saveMileage() {
    try {
      const r = await api.put('courier-salary/mileage', {
        employee_code: String(courierId), period,
        odometer_start: mileageDraft.odometer_start === '' ? null : Number(mileageDraft.odometer_start),
        odometer_end: mileageDraft.odometer_end === '' ? null : Number(mileageDraft.odometer_end),
      });
      setMileage(r.data); toast('Пробег сохранён', 'success');
    } catch { toast('Ошибка сохранения', 'error'); }
  }

  async function pollNow() {
    setPolling(true);
    try {
      await api.post('courier-salary/track/poll');
      const r = await api.get('courier-salary/track/status', { params: { employee_code: courierId, period } });
      setTrack(r.data);
      toast('Точка снята', 'success');
    } catch { toast('Не удалось опросить StarLine', 'error'); }
    finally { setPolling(false); }
  }

  async function syncMileage() {
    setSyncing(true);
    try {
      const r = await api.post('courier-salary/mileage/sync', null, { params: { employee_code: courierId, period } });
      setMileage(r.data); setMileageDraft({ odometer_start: r.data?.odometer_start ?? '', odometer_end: r.data?.odometer_end ?? '' });
      toast('Пробег обновлён из StarLine', 'success');
    } catch (e) { toast(e?.response?.data?.detail || 'StarLine недоступен', 'error'); }
    finally { setSyncing(false); }
  }

  async function accrue() {
    if (!courierId || !plan) return;
    setAccruing(true);
    try {
      await api.post('courier-salary/accrue', {
        oklad: plan.oklad, advances: advances?.total || 0, bonuses: incentives.bonuses, penalties: incentives.penalties,
        employee_code: String(courierId), employee_name: courier?.full_name || courier?.name || '',
        user_id: String(courierId), period, date_from: dateFrom, date_to: dateTo, mileage_km: mileage?.km ?? null,
      });
      toast('Начисление сохранено', 'success'); setTick((t) => t + 1);
    } catch { toast('Ошибка начисления', 'error'); }
    finally { setAccruing(false); }
  }

  async function createPayout(a) {
    if (!window.confirm(`Создать выплату «Зарплата» на ${fmtMoney(a.result?.to_pay || 0)} (наличными)?`)) return;
    setPayingId(a.id);
    try { await api.post(`courier-salary/accruals/${a.id}/payout`); toast('Выплата создана', 'success'); setTick((t) => t + 1); }
    catch (e) { toast(e?.response?.data?.detail || 'Ошибка создания выплаты', 'error'); }
    finally { setPayingId(null); }
  }

  async function deleteAccrual(id) {
    if (!window.confirm('Удалить начисление?')) return;
    try { await api.delete(`courier-salary/accruals/${id}`); setTick((t) => t + 1); }
    catch { toast('Ошибка удаления', 'error'); }
  }

  const kept = result ? (result.advances + result.penalties) : 0;

  return (
    <div className="space-y-5 max-w-4xl mx-auto pb-12">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)] flex items-center gap-2"><Truck size={24} /> Зарплата курьера</h2>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">Оклад, авансы и премии/штрафы · пробег авто из StarLine</p>
        </div>
        <span className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full ${starline?.configured ? 'bg-[color:var(--color-success-muted)] text-[color:var(--color-success)]' : 'bg-[color:var(--color-bg-secondary)] text-[color:var(--color-muted-foreground)]'}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${starline?.configured ? 'bg-[color:var(--color-success)]' : 'bg-[color:var(--color-muted-foreground)]'}`} /> StarLine {starline?.configured ? 'подключён' : 'не настроен'}
        </span>
      </div>

      {/* Selectors */}
      <div className="app-card p-3 flex flex-col sm:flex-row sm:items-end gap-3">
        <label className="block sm:flex-1">
          <span className="block text-xs font-medium uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-1">Курьер</span>
          <select className="input w-full" value={courierId} onChange={(e) => setCourierId(e.target.value)}>
            <option value="">— выберите —</option>
            {couriers.map((e) => <option key={e.id} value={e.id}>{e.full_name || e.name}</option>)}
          </select>
        </label>
        <label className="block sm:w-48">
          <span className="block text-xs font-medium uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-1">Период</span>
          <select className="input w-full" value={period} onChange={(e) => setPeriod(e.target.value)}>
            {months.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </label>
        <button className="btn btn--secondary flex items-center justify-center gap-1.5" onClick={load} disabled={!courierId || loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Обновить
        </button>
      </div>

      {couriers.length === 0 && (
        <div className="app-card p-4 text-sm text-[color:var(--color-muted-foreground)]">Нет сотрудников с должностью, содержащей «курьер».</div>
      )}

      {!courierId ? (
        <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]"><Truck size={28} className="mx-auto mb-2 opacity-60" /> Выберите курьера и период.</div>
      ) : result ? (
        <>
          {/* Hero: payout */}
          <section className="app-card overflow-hidden">
            <div className="p-5 sm:p-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-5">
              <div className="min-w-0">
                <div className="text-xs uppercase tracking-wide text-[color:var(--color-muted-foreground)]">К выплате · {courier?.full_name || courier?.name} · {periodLabel}</div>
                <div className="mt-1 text-4xl font-bold tabular-nums text-[color:var(--color-primary)] whitespace-nowrap">{fmtMoney(result.to_pay)}</div>
                <div className="mt-1 text-sm text-[color:var(--color-muted-foreground)]">Начислено {fmtMoney(result.gross)}{kept ? <> · удержано <span className="text-[color:var(--color-danger)]">{fmtMoney(kept)}</span></> : null}</div>
              </div>
              <div className="shrink-0 sm:text-right">
                <button className="btn btn--primary flex items-center gap-2 w-full sm:w-auto justify-center" onClick={accrue} disabled={accruing}>
                  <Wallet size={16} /> {accruing ? 'Начисляю…' : 'Начислить ЗП'}
                </button>
                <div className="mt-1.5 text-[11px] text-[color:var(--color-muted-foreground)]">Фиксирует расчёт в журнале ниже. Выплату создадите там же.</div>
              </div>
            </div>
            <div className="px-5 sm:px-6 py-4 border-t border-[color:var(--color-border)] flex flex-wrap items-center gap-x-4 gap-y-3">
              <Term label="Оклад" value={result.oklad} />
              <Term op="+" label="Премии" value={result.bonuses} tone={result.bonuses ? TONE.success : ''} />
              <Term op="−" label="Авансы" value={result.advances} tone={result.advances ? TONE.danger : ''} />
              <Term op="−" label="Штрафы" value={result.penalties} tone={result.penalties ? TONE.danger : ''} />
              <Term op="=" label="К выплате" value={result.to_pay} tone={TONE.primary} strong />
            </div>
          </section>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Plan: oklad + device */}
            <div className="app-card p-4 space-y-3">
              <h3 className="font-semibold">Оклад и устройство</h3>
              <label className="block">
                <span className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Оклад за месяц, ₽</span>
                <input type="number" className="input w-full" value={planDraft.oklad} onChange={(e) => setPlanDraft((d) => ({ ...d, oklad: e.target.value }))} />
              </label>
              <label className="block">
                <span className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">StarLine device_id <span className="opacity-70">(для авто-пробега)</span></span>
                <input className="input w-full" value={planDraft.starline_device_id} placeholder="например 1234567" onChange={(e) => setPlanDraft((d) => ({ ...d, starline_device_id: e.target.value }))} />
              </label>
              <button className="btn btn--secondary btn--sm flex items-center gap-1.5" onClick={savePlan}><Save size={14} /> Сохранить</button>
            </div>

            {/* Mileage */}
            <div className="app-card p-4 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-semibold flex items-center gap-2"><Gauge size={16} /> Пробег авто</h3>
                <div className="text-right">
                  <div className="text-xl font-bold tabular-nums text-[color:var(--color-primary)]">{fmtKm(mileage?.km)}</div>
                  <div className="text-[10px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">за период</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <label className="block">
                  <span className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Одометр начало</span>
                  <input type="number" className="input w-full" value={mileageDraft.odometer_start} onChange={(e) => setMileageDraft((d) => ({ ...d, odometer_start: e.target.value }))} />
                </label>
                <label className="block">
                  <span className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Одометр конец</span>
                  <input type="number" className="input w-full" value={mileageDraft.odometer_end} onChange={(e) => setMileageDraft((d) => ({ ...d, odometer_end: e.target.value }))} />
                </label>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button className="btn btn--secondary btn--sm flex items-center gap-1.5" onClick={saveMileage}><Save size={14} /> Сохранить</button>
                <button className="btn btn--secondary btn--sm flex items-center gap-1.5" onClick={syncMileage} disabled={syncing || !starline?.configured} title={starline?.configured ? 'Подтянуть текущий одометр из StarLine' : 'StarLine не настроен'}>
                  <RotateCw size={14} className={syncing ? 'animate-spin' : ''} /> Из StarLine
                </button>
                {mileage?.updated_at && (
                  <span className="text-[11px] text-[color:var(--color-muted-foreground)]">{mileage.source === 'starline-track' ? 'StarLine (GPS-трек)' : mileage.source === 'starline' ? 'StarLine (одометр)' : 'вручную'} · {mileage.updated_at.slice(0, 16).replace('T', ' ')}</span>
                )}
              </div>
              {starline?.configured && (
                <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-[color:var(--color-border)] text-[11px] text-[color:var(--color-muted-foreground)]">
                  <span>Авто-трек: <span className="font-medium text-[color:var(--color-text)]">{track?.points ?? 0}</span> точек{track?.km != null ? <> · по треку <span className="font-medium text-[color:var(--color-text)]">{fmtKm(track.km)}</span></> : ''}</span>
                  <button className="ml-auto inline-flex items-center gap-1 hover:text-[color:var(--color-primary)]" onClick={pollNow} disabled={polling}>
                    <RotateCw size={12} className={polling ? 'animate-spin' : ''} /> опросить сейчас
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Journal */}
          <div className="app-card overflow-hidden">
            <div className="px-5 py-3 border-b border-[color:var(--color-border)] font-semibold">Журнал начислений <span className="text-xs font-normal text-[color:var(--color-muted-foreground)]">{courier ? courier.full_name || courier.name : ''} · {accruals.length}</span></div>
            {accruals.length === 0 ? (
              <div className="px-5 py-10 text-center text-sm text-[color:var(--color-muted-foreground)]">Начислений пока нет.</div>
            ) : (
              <ul className="divide-y divide-[color:var(--color-border)]">
                {accruals.map((a) => (
                  <li key={a.id} className="px-5 py-3 text-sm flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
                    <div className="min-w-0">
                      <div className="font-medium">{a.period} <span className="text-xs text-[color:var(--color-muted-foreground)]">· {a.created_at?.slice(0, 16).replace('T', ' ')}</span></div>
                      <div className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">
                        <span className="text-[color:var(--color-success)]">+ начислено</span> оклад {fmtMoney(a.result?.oklad)}{a.result?.bonuses ? ` · премии ${fmtMoney(a.result?.bonuses)}` : ''}
                        <span className="text-[color:var(--color-danger)]"> · − списано</span> авансы {fmtMoney(a.result?.advances)}{a.result?.penalties ? ` · штрафы ${fmtMoney(a.result?.penalties)}` : ''}
                        {a.mileage_km != null ? <> · пробег {fmtKm(a.mileage_km)}</> : null}
                      </div>
                    </div>
                    <div className="flex items-center justify-between gap-3 shrink-0 border-t border-[color:var(--color-border)] pt-2 sm:border-0 sm:pt-0 sm:justify-end">
                      <div className="sm:text-right">
                        <div className="font-semibold tabular-nums text-[color:var(--color-primary)] whitespace-nowrap">{fmtMoney(a.result?.to_pay)}</div>
                        <div className="text-[10px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">к выплате</div>
                      </div>
                      {a.payout_id ? (
                        <span className="inline-flex items-center gap-1 text-xs text-[color:var(--color-success)] shrink-0" title={`Выплата #${a.payout_id}`}><CheckCircle2 size={14} /> выплата</span>
                      ) : (
                        <button onClick={() => createPayout(a)} disabled={payingId === a.id || !(a.result?.to_pay > 0)} className="btn btn--secondary btn--sm flex items-center gap-1.5 shrink-0"><Banknote size={14} /> {payingId === a.id ? '…' : 'Выплата'}</button>
                      )}
                      <button onClick={() => deleteAccrual(a.id)} className="text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-danger)] shrink-0" title="Удалить"><Trash2 size={15} /></button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      ) : loading ? (
        <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]">Загрузка…</div>
      ) : null}
    </div>
  );
}
