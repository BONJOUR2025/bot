import { useState } from 'react';
import { RefreshCw, Landmark, AlertTriangle, Phone } from 'lucide-react';
import api from '../api';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';

function toLocalDateStr(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}
const TODAY = toLocalDateStr(new Date());

function quickRange(key) {
  const n = new Date(); const y = n.getFullYear(), m = n.getMonth();
  if (key === 'month') return [toLocalDateStr(new Date(y, m, 1)), TODAY];
  if (key === 'prev')  return [toLocalDateStr(new Date(y, m-1, 1)), toLocalDateStr(new Date(y, m, 0))];
  if (key === 'q')     return [toLocalDateStr(new Date(y, Math.floor(m/3)*3, 1)), TODAY];
  if (key === 'year')  return [toLocalDateStr(new Date(y, 0, 1)), TODAY];
  return [TODAY, TODAY];
}

const fmtRub = (v) => v == null ? '—' : Math.round(v).toLocaleString('ru-RU') + ' ₽';

const PAY_STATUS_LABELS = {
  1: { label: 'Не оплачен', className: 'bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400' },
  2: { label: 'Оплачен частично', className: 'bg-amber-50 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400' },
  3: { label: 'Оплачен (расхождение)', className: 'bg-[color:var(--color-muted)] text-[color:var(--color-muted-foreground)]' },
};

function KpiStat({ label, value, accent, icon }) {
  return (
    <div className="app-card p-4" style={{ borderLeft: `3px solid ${accent}` }}>
      <div className="flex gap-3">
        {icon && <div className="mt-0.5 shrink-0" style={{ color: accent }}>{icon}</div>}
        <div className="min-w-0 flex-1">
          <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)] font-medium">{label}</div>
          <div className="text-xl sm:text-2xl font-bold tabular-nums mt-0.5 leading-tight" style={{ color: accent }}>{value}</div>
        </div>
      </div>
    </div>
  );
}

export default function Receivables() {
  const now = new Date();
  const monthStart = toLocalDateStr(new Date(now.getFullYear(), now.getMonth(), 1));

  const [dateFrom, setDateFrom] = useState(monthStart);
  const [dateTo,   setDateTo]   = useState(TODAY);
  const [data,     setData]     = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [loaded,   setLoaded]   = useState(false);
  const [error,    setError]    = useState(null);

  async function load() {
    setLoading(true); setError(null);
    try {
      const params = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo)   params.date_to   = dateTo;
      const res = await api.get('/sales/receivables', { params });
      setData(res.data); setLoaded(true);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки');
    } finally { setLoading(false); }
  }

  return (
    <div className="space-y-5">
      <TopProgressBar active={loading} />

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Landmark size={22} className="text-[color:var(--color-primary)]" /> Дебиторка
          </h2>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">
            Заказы, созданные за период, с неполной оплатой на текущий момент (Агбис)
          </p>
        </div>
        <button onClick={load} disabled={loading}
          className="btn btn--primary btn--sm flex items-center gap-1.5">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          {loaded ? 'Обновить' : 'Загрузить'}
        </button>
      </div>

      <div className="app-card p-4 space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {[['month','Этот месяц'],['prev','Прошлый мес.'],['q','Квартал'],['year','Год']].map(([k, l]) => (
            <button key={k} onClick={() => { const [f,t] = quickRange(k); setDateFrom(f); setDateTo(t); }}
              className="px-3 py-1 rounded-full text-xs border border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)] transition-colors">
              {l}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Дата от</label>
            <input type="date" className="input w-full" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Дата до</label>
            <input type="date" className="input w-full" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4 text-red-700 dark:text-red-300 text-sm">{error}</div>
      )}

      {!loaded && !loading && (
        <div className="app-card p-14 text-center">
          <Landmark size={44} className="mx-auto text-[color:var(--color-muted-foreground)] opacity-25 mb-3" />
          <p className="text-[color:var(--color-muted-foreground)]">Выберите период и нажмите <strong>Загрузить</strong></p>
        </div>
      )}

      {loading && <SkeletonTable rows={6} />}

      {loaded && !loading && data && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <KpiStat label="Не погашено всего" value={fmtRub(data.total_amount)} accent="#c9502a" icon={<AlertTriangle size={18} />} />
            <KpiStat label="Заказов с долгом" value={data.total_count.toLocaleString('ru-RU')} accent="#ffb347" icon={<Landmark size={18} />} />
          </div>

          <div className="app-card overflow-hidden">
            <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
              <h3 className="font-semibold">Список заказов</h3>
              <p className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">Сортировка — от старых к новым (самые давние долги наверху)</p>
            </div>
            <div className="p-3">
              <ResponsiveTable
                data={data.orders}
                keyFn={(o) => o.order_id}
                emptyText="Долгов за выбранный период нет"
                columns={[
                  { label: '№ заказа', primary: true, render: (o) => (
                    <div>
                      <div className="font-medium">{o.doc_num}</div>
                      <div className="text-xs text-[color:var(--color-muted-foreground)]">{o.date}</div>
                    </div>
                  )},
                  { label: 'Клиент', render: (o) => (
                    <div className="min-w-0">
                      <div className="truncate">{o.client_name || '—'}</div>
                      {o.client_phone && (
                        <div className="text-xs text-[color:var(--color-muted-foreground)] flex items-center gap-1">
                          <Phone size={10} /> {o.client_phone}
                        </div>
                      )}
                    </div>
                  )},
                  { label: 'Статус', render: (o) => {
                    const s = PAY_STATUS_LABELS[o.pay_status_id] || PAY_STATUS_LABELS[1];
                    return <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${s.className}`}>{s.label}</span>;
                  }},
                  { label: 'Просрочка', headerClass: 'text-right', cellClass: 'text-right tabular-nums', render: (o) => `${o.days_overdue} дн.` },
                  { label: 'Долг', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold text-red-500', render: (o) => fmtRub(o.amount) },
                ]}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
