import { useState, useEffect, useCallback } from 'react';
import { Search, ArrowRight, Trash2, AlertTriangle, Info } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';

const MONTHS = [
  'ЯНВАРЬ','ФЕВРАЛЬ','МАРТ','АПРЕЛЬ','МАЙ','ИЮНЬ',
  'ИЮЛЬ','АВГУСТ','СЕНТЯБРЬ','ОКТЯБРЬ','НОЯБРЬ','ДЕКАБРЬ',
];

const CATEGORIES = ['repair', 'cosmetics', 'shoes'];

const CATEGORY_LABELS = {
  repair: 'Ремонт / Химчистка',
  cosmetics: 'Косметика',
  shoes: 'Обувь',
};

function fmt(v) {
  if (!v && v !== 0) return '—';
  return Number(v).toLocaleString('ru');
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('ru', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function isToday(iso) {
  if (!iso) return false;
  const d = new Date(iso);
  return !Number.isNaN(d.getTime()) && d.toDateString() === new Date().toDateString();
}

export default function SaleTransfers() {
  const { toast } = useToast();
  const now = new Date();
  const [year, setYear]   = useState(now.getFullYear());
  const [month, setMonth] = useState(MONTHS[now.getMonth()]);

  const [docNum, setDocNum]       = useState('');
  const [looking, setLooking]     = useState(false);
  const [order, setOrder]         = useState(null);   // breakdown from /order-lookup
  // {category: { amount, toCategory, toCode }}
  const [rowState, setRowState]   = useState({});
  const [submitting, setSubmitting] = useState(false);

  const [employees, setEmployees] = useState([]);     // [{code, name}]
  const [transfers, setTransfers] = useState([]);

  // Живые часы для телеметрии ленты переносов и распознавания «только
  // что случившегося» переноса — реальное время, а не декоративная
  // анимация, см. transfer-fui-* ниже. Отдельное имя от `now` выше
  // (снимок при монтировании для инициализации year/month).
  const [clockNow, setClockNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setClockNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const loadMonthData = useCallback(async () => {
    try {
      const [calc, list] = await Promise.all([
        api.get('/payroll/calculate', { params: { month, year } }),
        api.get('/payroll/sale-transfers', { params: { month, year } }),
      ]);
      const emps = (calc.data.rows || [])
        .map(r => ({ code: r.employee_code, name: r.employee_name }))
        .sort((a, b) => (a.name || '').localeCompare(b.name || '', 'ru'));
      setEmployees(emps);
      setTransfers(list.data || []);
    } catch (e) {
      toast('Ошибка загрузки данных месяца', 'error');
    }
  }, [month, year, toast]);

  useEffect(() => { loadMonthData(); }, [loadMonthData]);

  async function lookup() {
    const num = docNum.trim();
    if (!num) return;
    setLooking(true);
    setOrder(null);
    setRowState({});
    try {
      const res = await api.get('/payroll/order-lookup', { params: { doc_num: num } });
      setOrder(res.data);
      const rows = categoryRows(res.data);
      setRowState(Object.fromEntries(rows.map(r => (
        [r.key, { amount: r.amount, toCategory: r.key, toCode: '' }]
      ))));
    } catch (e) {
      if (e.response?.status === 404) toast('Заказ не найден', 'error');
      else toast('Ошибка поиска заказа', 'error');
    } finally {
      setLooking(false);
    }
  }

  function categoryRows(o) {
    if (!o) return [];
    return [
      { key: 'repair',    amount: o.repair },
      { key: 'cosmetics', amount: o.cosmetics },
      { key: 'shoes',     amount: o.shoes_total },
    ].filter(r => r.amount && r.amount > 0);
  }

  function updateRow(category, patch) {
    setRowState(s => ({ ...s, [category]: { ...s[category], ...patch } }));
  }

  async function transfer(category) {
    const row = rowState[category];
    const toCode = row?.toCode;
    const toCategory = row?.toCategory || category;
    const amount = Number(row?.amount) || 0;
    if (!toCode) { toast('Выберите сотрудника', 'error'); return; }
    if (!amount || amount <= 0) { toast('Укажите сумму', 'error'); return; }
    if (toCode === order.seller_code && toCategory === category) {
      toast('Нет изменений — тот же сотрудник и та же категория', 'error');
      return;
    }
    const toEmp = employees.find(e => e.code === toCode);
    setSubmitting(true);
    try {
      await api.post('/payroll/sale-transfers', {
        month, year,
        doc_num: order.doc_num,
        from_category: category,
        to_category: toCategory,
        amount,
        from_code: order.seller_code,
        from_name: order.seller_name,
        to_code: toCode,
        to_name: toEmp?.name || '',
        order_date: order.order_date,
        shoes_orders: category === 'shoes' ? (order.shoes_orders || []) : [],
      });
      toast('Продажа перенесена', 'success');
      await loadMonthData();
    } catch (e) {
      const detail = e.response?.data?.detail;
      if (detail === 'transfer_exists') toast('Этот заказ уже перенесён в эту категорию/этому сотруднику', 'error');
      else if (detail === 'no_op') toast('Нет изменений — тот же сотрудник и та же категория', 'error');
      else toast('Ошибка переноса', 'error');
    } finally {
      setSubmitting(false);
    }
  }

  async function removeTransfer(id) {
    if (!window.confirm('Отменить этот перенос?')) return;
    try {
      await api.delete(`/payroll/sale-transfers/${id}`);
      toast('Перенос отменён', 'success');
      await loadMonthData();
    } catch {
      toast('Ошибка отмены', 'error');
    }
  }

  function prevMonth() {
    const idx = MONTHS.indexOf(month);
    if (idx === 0) { setMonth(MONTHS[11]); setYear(y => y - 1); }
    else setMonth(MONTHS[idx - 1]);
  }
  function nextMonth() {
    const idx = MONTHS.indexOf(month);
    if (idx === 11) { setMonth(MONTHS[0]); setYear(y => y + 1); }
    else setMonth(MONTHS[idx + 1]);
  }

  const rows = categoryRows(order);

  // Телеметрия ленты переносов: реальные агрегаты по уже загруженному
  // transfers за выбранный месяц — сколько сегодня, сколько всего,
  // на какую сумму.
  const transfersToday = transfers.filter((t) => isToday(t.created_at)).length;
  const transfersAmountTotal = transfers.reduce((s, t) => s + Number(t.amount || 0), 0);

  // Самый свежий перенос и признак «случился в пределах последнего
  // часа» — тикает вместе с `now`, поэтому маркер сам гаснет через час,
  // без перезагрузки страницы.
  const latestTransfer = transfers.reduce((acc, t) => {
    if (!t.created_at) return acc;
    const d = new Date(t.created_at);
    if (Number.isNaN(d.getTime())) return acc;
    if (!acc || d > acc.date) return { id: t.id, date: d };
    return acc;
  }, null);
  const justHappened = Boolean(
    latestTransfer && clockNow.getTime() - latestTransfer.date.getTime() < 60 * 60 * 1000
  );

  return (
    <div className="p-4 sm:p-6 space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="min-w-0">
          <span className="ui-eyebrow mb-3">{month ? `Месяц · ${month}` : 'Месяц не выбран'}</span>
          <h1 className="text-xl sm:text-2xl font-bold">Перемещение продажи</h1>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">
            Перенос суммы продажи между сотрудниками и/или категориями (например, продажу
            ошибочно провели как ремонт вместо косметики). База Агбис (Firebird) не меняется —
            корректировка учитывается только в расчёте зарплаты и боте.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button onClick={prevMonth} className="btn btn-secondary w-9 h-9 flex items-center justify-center text-lg leading-none">‹</button>
          <span className="min-w-[140px] sm:min-w-[160px] text-center font-semibold text-sm sm:text-base px-1">
            {month} {year}
          </span>
          <button onClick={nextMonth} className="btn btn-secondary w-9 h-9 flex items-center justify-center text-lg leading-none">›</button>
        </div>
      </div>

      <div className="rounded-xl bg-blue-50 border border-blue-200 text-sm text-blue-800 px-4 py-3 flex items-start gap-2">
        <Info size={15} className="flex-shrink-0 text-blue-500 mt-0.5" />
        <span>Перенос применяется к выбранному месяцу: из исходной категории/сотрудника сумма вычитается, в целевую категорию/сотруднику — прибавляется. Комиссия считается по ставке целевой категории. Это может изменить выполнение плана и ставку комиссии у обоих.</span>
      </div>

      {/* Lookup */}
      <div className="app-card p-4 space-y-3">
        <label className="text-sm font-medium">Номер заказа</label>
        <div className="flex gap-2">
          <input
            className="input flex-1"
            value={docNum}
            onChange={e => setDocNum(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && lookup()}
            placeholder="например, 123456"
          />
          <button onClick={lookup} disabled={looking || !docNum.trim()}
            className="btn btn--primary flex items-center gap-2 disabled:opacity-50">
            <Search size={16} className={looking ? 'animate-pulse' : ''} />
            {looking ? 'Поиск…' : 'Найти'}
          </button>
        </div>

        {order && (
          <div className="rounded-lg border border-[color:var(--color-border)] p-3 space-y-3">
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
              <div><span className="text-[color:var(--color-muted-foreground)]">Заказ:</span> <b>{order.doc_num}</b></div>
              {order.order_date && <div><span className="text-[color:var(--color-muted-foreground)]">Дата:</span> {order.order_date}</div>}
              <div><span className="text-[color:var(--color-muted-foreground)]">Текущий продавец:</span> <b>{order.seller_name || order.seller_code || '—'}</b></div>
            </div>

            {rows.length === 0 ? (
              <div className="flex items-center gap-2 text-sm text-amber-600">
                <AlertTriangle size={15} /> В заказе нет сумм по комиссионным категориям.
              </div>
            ) : (
              <div className="space-y-3">
                {rows.map(({ key, amount }) => {
                  const row = rowState[key] || { amount, toCategory: key, toCode: '' };
                  return (
                    <div key={key} className="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-2 py-2 border-t border-[color:var(--color-border)] first:border-t-0">
                      <div className="min-w-[150px]">
                        <div className="text-sm font-medium">{CATEGORY_LABELS[key]}</div>
                        <div className="text-sm text-[color:var(--color-muted-foreground)]">из {fmt(amount)} ₽</div>
                      </div>
                      <input
                        type="number"
                        className="input text-sm w-full sm:w-28"
                        value={row.amount}
                        min={0}
                        onChange={e => updateRow(key, { amount: e.target.value })}
                        title="Сумма к переносу"
                      />
                      <ArrowRight size={16} className="text-[color:var(--color-muted-foreground)] hidden sm:inline self-center" />
                      <select
                        className="input text-sm w-full sm:w-auto sm:min-w-[150px]"
                        value={row.toCategory}
                        onChange={e => updateRow(key, { toCategory: e.target.value })}
                        title="В какую категорию"
                      >
                        {CATEGORIES.map(c => <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>)}
                      </select>
                      <select
                        className="input text-sm w-full sm:w-auto sm:flex-1 sm:min-w-[160px]"
                        value={row.toCode}
                        onChange={e => updateRow(key, { toCode: e.target.value })}
                      >
                        <option value="">Кому перенести…</option>
                        {employees.map(e => (
                          <option key={e.code} value={e.code}>
                            {e.name} ({e.code}){e.code === order.seller_code ? ' — тот же сотрудник' : ''}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={() => transfer(key)}
                        disabled={submitting || !row.toCode}
                        className="btn btn--primary text-sm disabled:opacity-50 w-full sm:w-auto"
                      >
                        Перенести
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Existing transfers */}
      <div className="transfer-fui-readout">
        <span>ПЕРЕМЕЩЕНИЙ СЕГОДНЯ: <b>{transfersToday}</b></span>
        <span className="sep">·</span>
        <span>ВСЕГО ЗА {month}: <b>{transfers.length}</b></span>
        <span className="sep">·</span>
        <span>СУММА ЗА ПЕРИОД: <b>{fmt(transfersAmountTotal)} ₽</b></span>
        <span className="sep">·</span>
        <span>
          {clockNow.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          <span className="transfer-fui-cursor">_</span>
        </span>
      </div>
      <div className="app-card overflow-hidden">
        <div className="px-4 py-3 border-b border-[color:var(--color-border)] font-semibold text-sm">
          Переносы за {month} {year}
        </div>
        {transfers.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-[color:var(--color-muted-foreground)] italic">
            Пока нет переносов
          </div>
        ) : (
          <ResponsiveTable
            data={transfers}
            keyFn={(t) => t.id}
            emptyText="Пока нет переносов"
            columns={[
              {
                label: 'Когда',
                render: (t) => (
                  <span className="whitespace-nowrap text-xs text-[color:var(--color-muted-foreground)] inline-flex items-center gap-1.5">
                    {justHappened && latestTransfer?.id === t.id && (
                      <span className="transfer-fui-radar" title="Только что"><i /><i /><i /><b /></span>
                    )}
                    {fmtDateTime(t.created_at)}
                  </span>
                ),
              },
              {
                label: 'Заказ',
                key: 'doc_num',
                primary: true,
                render: (t) => <span className="font-mono text-xs">{t.doc_num}</span>,
              },
              {
                label: 'Маршрут',
                render: (t) => {
                  const live = isToday(t.created_at);
                  return (
                    <div className="transfer-fui-route">
                      <div className="transfer-fui-route__node">
                        <span className="transfer-fui-route__cat">{CATEGORY_LABELS[t.from_category] || t.from_category}</span>
                        <span className="transfer-fui-route__who" title={t.from_name || t.from_code || ''}>
                          {t.from_name || t.from_code || '—'}
                        </span>
                      </div>
                      <div className={`transfer-fui-route__connector${live ? ' transfer-fui-route__connector--live' : ''}`}>
                        <span className="transfer-fui-route__dot" />
                      </div>
                      <div className="transfer-fui-route__node">
                        <span className="transfer-fui-route__cat">{CATEGORY_LABELS[t.to_category] || t.to_category}</span>
                        <span className="transfer-fui-route__who" title={t.to_name || t.to_code || ''}>
                          {t.to_name || t.to_code || '—'}
                        </span>
                      </div>
                    </div>
                  );
                },
              },
              {
                label: 'Сумма',
                headerClass: 'text-right',
                cellClass: 'text-right whitespace-nowrap',
                render: (t) => <span className="tabular-nums font-medium">{fmt(t.amount)} ₽</span>,
              },
              {
                label: 'Кто перенёс',
                mobileHide: true,
                render: (t) => (
                  <span className="text-[color:var(--color-muted-foreground)]">{t.author || '—'}</span>
                ),
              },
              {
                label: 'Действия',
                isAction: true,
                render: (t) => (
                  <button onClick={() => removeTransfer(t.id)}
                    className="text-red-400 hover:text-red-600" title="Отменить">
                    <Trash2 size={15} />
                  </button>
                ),
              },
            ]}
          />
        )}
      </div>
    </div>
  );
}
