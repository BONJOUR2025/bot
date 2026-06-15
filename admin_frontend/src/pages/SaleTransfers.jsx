import { useState, useEffect, useCallback } from 'react';
import { Search, ArrowRight, Trash2, AlertTriangle, Info } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

const MONTHS = [
  'ЯНВАРЬ','ФЕВРАЛЬ','МАРТ','АПРЕЛЬ','МАЙ','ИЮНЬ',
  'ИЮЛЬ','АВГУСТ','СЕНТЯБРЬ','ОКТЯБРЬ','НОЯБРЬ','ДЕКАБРЬ',
];

const CATEGORY_LABELS = {
  repair: 'Ремонт / Химчистка',
  cosmetics: 'Косметика',
  shoes: 'Обувь',
};

function fmt(v) {
  if (!v && v !== 0) return '—';
  return Number(v).toLocaleString('ru');
}

export default function SaleTransfers() {
  const { toast } = useToast();
  const now = new Date();
  const [year, setYear]   = useState(now.getFullYear());
  const [month, setMonth] = useState(MONTHS[now.getMonth()]);

  const [docNum, setDocNum]       = useState('');
  const [looking, setLooking]     = useState(false);
  const [order, setOrder]         = useState(null);   // breakdown from /order-lookup
  const [targets, setTargets]     = useState({});     // {category: to_code}
  const [submitting, setSubmitting] = useState(false);

  const [employees, setEmployees] = useState([]);     // [{code, name}]
  const [transfers, setTransfers] = useState([]);

  const loadMonthData = useCallback(async () => {
    try {
      const [calc, list] = await Promise.all([
        api.get('/payroll/calculate', { params: { month, year } }),
        api.get('/payroll/sale-transfers', { params: { month, year } }),
      ]);
      const emps = (calc.data.rows || []).map(r => ({
        code: r.employee_code, name: r.employee_name,
      }));
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
    setTargets({});
    try {
      const res = await api.get('/payroll/order-lookup', { params: { doc_num: num } });
      setOrder(res.data);
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

  async function transfer(category, amount) {
    const toCode = targets[category];
    if (!toCode) { toast('Выберите сотрудника', 'error'); return; }
    if (toCode === order.seller_code) { toast('Это тот же сотрудник', 'error'); return; }
    const toEmp = employees.find(e => e.code === toCode);
    setSubmitting(true);
    try {
      await api.post('/payroll/sale-transfers', {
        month, year,
        doc_num: order.doc_num,
        category,
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
      if (detail === 'transfer_exists') toast('Этот заказ уже перенесён в этой категории', 'error');
      else if (detail === 'same_employee') toast('Нельзя перенести самому себе', 'error');
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

  return (
    <div className="p-4 sm:p-6 space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold">Перемещение продажи</h1>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">
            Перенос продажи с одного сотрудника на другого. База Агбис (Firebird) не меняется —
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
        <span>Перенос применяется к выбранному месяцу: у текущего продавца сумма вычитается, новому — прибавляется. Это может изменить выполнение плана и ставку комиссии у обоих.</span>
      </div>

      {/* Lookup */}
      <div className="card p-4 space-y-3">
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
            className="btn btn-primary flex items-center gap-2 disabled:opacity-50">
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
              <div className="space-y-2">
                {rows.map(({ key, amount }) => (
                  <div key={key} className="flex flex-wrap items-center gap-2 py-2 border-t border-[color:var(--color-border)] first:border-t-0">
                    <div className="min-w-[150px]">
                      <div className="text-sm font-medium">{CATEGORY_LABELS[key]}</div>
                      <div className="text-sm text-[color:var(--color-muted-foreground)]">{fmt(amount)} ₽</div>
                    </div>
                    <ArrowRight size={16} className="text-[color:var(--color-muted-foreground)]" />
                    <select
                      className="input text-sm flex-1 min-w-[160px]"
                      value={targets[key] || ''}
                      onChange={e => setTargets(t => ({ ...t, [key]: e.target.value }))}
                    >
                      <option value="">Кому перенести…</option>
                      {employees
                        .filter(e => e.code !== order.seller_code)
                        .map(e => <option key={e.code} value={e.code}>{e.name} ({e.code})</option>)}
                    </select>
                    <button
                      onClick={() => transfer(key, amount)}
                      disabled={submitting || !targets[key]}
                      className="btn btn-primary text-sm disabled:opacity-50"
                    >
                      Перенести
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Existing transfers */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b border-[color:var(--color-border)] font-semibold text-sm">
          Переносы за {month} {year}
        </div>
        {transfers.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-[color:var(--color-muted-foreground)] italic">
            Пока нет переносов
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[color:var(--color-border)] bg-[color:var(--color-muted)]/30 text-xs text-[color:var(--color-muted-foreground)]">
                <th className="text-left px-4 py-2">Заказ</th>
                <th className="text-left px-3 py-2">Категория</th>
                <th className="text-right px-3 py-2">Сумма</th>
                <th className="text-left px-3 py-2">От кого</th>
                <th className="text-left px-3 py-2">Кому</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--color-border)]">
              {transfers.map(t => (
                <tr key={t.id}>
                  <td className="px-4 py-2 font-mono text-xs">{t.doc_num}</td>
                  <td className="px-3 py-2">{CATEGORY_LABELS[t.category] || t.category}</td>
                  <td className="px-3 py-2 text-right">{fmt(t.amount)} ₽</td>
                  <td className="px-3 py-2">{t.from_name || t.from_code}</td>
                  <td className="px-3 py-2">{t.to_name || t.to_code}</td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => removeTransfer(t.id)}
                      className="text-red-400 hover:text-red-600" title="Отменить">
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
