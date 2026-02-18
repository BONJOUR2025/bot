import { useEffect, useState, useMemo } from 'react';
import { Download, Search, X } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import Skeleton from '../components/ui/Skeleton.jsx';

const fmt = (v) => {
  if (!v || v === 0) return '—';
  return Number(v).toLocaleString('ru-RU');
};

const fmtMoney = (v) => {
  if (!v || v === 0) return '—';
  return `${Number(v).toLocaleString('ru-RU')} ₽`;
};

function SummaryBar({ rows }) {
  const total = rows.reduce((s, r) => s + (r.final_amount || 0), 0);
  const totalFund = rows.reduce((s, r) => s + (r.salary_total || 0), 0);
  const totalAdvance = rows.reduce((s, r) => s + (r.advance || 0), 0);
  const totalDeduction = rows.reduce((s, r) => s + (r.deduction || 0), 0);
  const avg = rows.length ? total / rows.length : 0;

  const stats = [
    { label: 'Сотрудников', value: rows.length, accent: false },
    { label: 'Фонд оплаты', value: fmtMoney(totalFund), accent: false },
    { label: 'Удержания', value: fmtMoney(totalDeduction), accent: true },
    { label: 'Авансы', value: fmtMoney(totalAdvance), accent: false },
    { label: 'К выплате', value: fmtMoney(total), accent: false },
    { label: 'Средняя ЗП', value: fmtMoney(Math.round(avg)), accent: false },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {stats.map((s) => (
        <div key={s.label} className="app-card p-4 text-center">
          <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">{s.label}</div>
          <div
            className={`text-base font-semibold ${
              s.accent ? 'text-[color:var(--color-danger)]' : 'text-[color:var(--color-text-primary)]'
            }`}
          >
            {s.value}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Payroll() {
  const { toast } = useToast();
  const [months, setMonths] = useState([]);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingMonths, setLoadingMonths] = useState(true);
  const [query, setQuery] = useState('');

  useEffect(() => {
    loadMonths();
  }, []);

  useEffect(() => {
    if (selectedMonth) loadSalary(selectedMonth);
    else setRows([]);
  }, [selectedMonth]);

  async function loadMonths() {
    setLoadingMonths(true);
    try {
      const res = await api.get('salary/months');
      const list = res.data || [];
      setMonths(list);
      if (list.length > 0) setSelectedMonth(list[0]);
    } catch (err) {
      console.error(err);
      toast('Ошибка загрузки месяцев', 'error');
    } finally {
      setLoadingMonths(false);
    }
  }

  async function loadSalary(month) {
    setLoading(true);
    try {
      const res = await api.get('salary/', { params: { month } });
      setRows(res.data || []);
    } catch (err) {
      console.error(err);
      toast('Ошибка загрузки данных', 'error');
    } finally {
      setLoading(false);
    }
  }

  function exportPdf() {
    if (!selectedMonth) return;
    window.open(`/api/salary/report?month=${selectedMonth}`, '_blank');
  }

  const filtered = useMemo(() => {
    if (!query.trim()) return rows;
    const q = query.toLowerCase();
    return rows.filter((r) => r.name?.toLowerCase().includes(q));
  }, [rows, query]);

  const columns = [
    { key: 'name', label: 'ФИО', render: (r) => r.name, sticky: true },
    { key: 'shifts_main', label: 'Осн.', render: (r) => fmt(r.shifts_main) },
    { key: 'shifts_extra', label: 'Доп.', render: (r) => fmt(r.shifts_extra) },
    { key: 'shifts_total', label: 'Смен', render: (r) => fmt(r.shifts_total) },
    { key: 'salary_fixed', label: 'Оклад', render: (r) => fmtMoney(r.salary_fixed) },
    { key: 'salary_repair', label: 'Ремонт', render: (r) => fmtMoney(r.salary_repair) },
    { key: 'salary_cosmetics', label: 'Косметика', render: (r) => fmtMoney(r.salary_cosmetics) },
    { key: 'salary_shoes', label: 'Обувь', render: (r) => fmtMoney(r.salary_shoes) },
    { key: 'salary_accessories', label: 'Аксес.', render: (r) => fmtMoney(r.salary_accessories) },
    { key: 'salary_keys', label: 'Ключи', render: (r) => fmtMoney(r.salary_keys) },
    { key: 'salary_slippers', label: 'Тапки', render: (r) => fmtMoney(r.salary_slippers) },
    { key: 'salary_workshop', label: 'Цех', render: (r) => fmtMoney(r.salary_workshop) },
    { key: 'salary_bonus', label: 'Бонус', render: (r) => fmtMoney(r.salary_bonus) },
    { key: 'salary_total', label: 'Итого', render: (r) => fmtMoney(r.salary_total), highlight: true },
    { key: 'deduction', label: 'Удерж.', render: (r) => fmtMoney(r.deduction), danger: true },
    { key: 'advance', label: 'Аванс', render: (r) => fmtMoney(r.advance) },
    { key: 'final_amount', label: 'К выплате', render: (r) => fmtMoney(r.final_amount), highlight: true },
    { key: 'comment', label: 'Коммент.', render: (r) => r.comment || '—' },
  ];

  return (
    <div className="space-y-6 max-w-full">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-semibold tracking-tight flex-1">Расчёт зарплаты</h2>
        <button
          onClick={exportPdf}
          disabled={!selectedMonth || loading}
          className="btn btn--primary flex items-center gap-2 disabled:opacity-50"
        >
          <Download size={16} />
          PDF отчёт
        </button>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        {loadingMonths ? (
          <Skeleton style={{ width: 160, height: 38, borderRadius: 8 }} />
        ) : (
          <select
            className="input"
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
            style={{ minWidth: 160 }}
          >
            <option value="">Выберите месяц</option>
            {months.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        )}

        <div className="relative flex-1" style={{ minWidth: 200 }}>
          <Search
            size={15}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)]"
          />
          <input
            className="input pl-9 w-full"
            placeholder="Поиск по ФИО…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-text-primary)]"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Summary */}
      {!loading && rows.length > 0 && <SummaryBar rows={filtered} />}

      {/* Table */}
      {!selectedMonth && !loadingMonths ? (
        <div className="app-card p-10 text-center text-[color:var(--color-muted-foreground)]">
          Выберите месяц для просмотра данных
        </div>
      ) : loading ? (
        <div className="app-card p-4">
          <SkeletonTable rows={8} cols={10} />
        </div>
      ) : filtered.length === 0 ? (
        <div className="app-card p-10 text-center text-[color:var(--color-muted-foreground)]">
          {query ? 'Сотрудник не найден' : 'Нет данных за этот месяц'}
        </div>
      ) : (
        <div className="overflow-auto rounded-xl border border-[color:var(--color-border)] shadow-sm">
          <table className="min-w-max w-full text-sm divide-y divide-[color:var(--color-border)] bg-[color:var(--color-table-bg)] text-[color:var(--color-table-text)]">
            <thead>
              <tr className="bg-[color:var(--color-table-header)]">
                {columns.map((col) => (
                  <th
                    key={col.key}
                    className={`px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide whitespace-nowrap
                      ${col.sticky ? 'sticky left-0 z-10 bg-[color:var(--color-table-header)]' : ''}
                      ${col.highlight ? 'text-[color:var(--color-primary)]' : 'text-[color:var(--color-muted-foreground)]'}
                      ${col.danger ? 'text-[color:var(--color-danger)]' : ''}
                    `}
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--color-border)]">
              {filtered.map((row, i) => (
                <tr
                  key={row.employee_id || row.name}
                  className={`transition-colors hover:bg-[color:var(--color-table-row-hover)] ${
                    i % 2 === 0 ? '' : 'bg-[color:var(--color-table-row-alt)]'
                  }`}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={`px-3 py-2.5 whitespace-nowrap
                        ${col.sticky ? 'sticky left-0 bg-[color:var(--color-table-bg)] font-medium' : ''}
                        ${col.highlight ? 'font-semibold text-[color:var(--color-primary)]' : ''}
                        ${col.danger ? 'text-[color:var(--color-danger)]' : ''}
                        ${col.key === 'comment' ? 'max-w-[160px] truncate whitespace-nowrap' : ''}
                      `}
                      title={col.key === 'comment' ? col.render(row) : undefined}
                    >
                      {col.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="bg-[color:var(--color-table-header)] font-semibold">
                <td className="px-3 py-2.5 sticky left-0 bg-[color:var(--color-table-header)]">
                  Итого: {filtered.length}
                </td>
                {columns.slice(1, -1).map((col) => {
                  const numericKeys = [
                    'salary_fixed','salary_repair','salary_cosmetics','salary_shoes',
                    'salary_accessories','salary_keys','salary_slippers','salary_workshop',
                    'salary_bonus','salary_total','deduction','advance','final_amount',
                  ];
                  if (numericKeys.includes(col.key)) {
                    const sum = filtered.reduce((s, r) => s + (r[col.key] || 0), 0);
                    return (
                      <td
                        key={col.key}
                        className={`px-3 py-2.5 whitespace-nowrap
                          ${col.highlight ? 'text-[color:var(--color-primary)]' : ''}
                          ${col.danger ? 'text-[color:var(--color-danger)]' : ''}
                        `}
                      >
                        {sum ? fmtMoney(sum) : '—'}
                      </td>
                    );
                  }
                  return <td key={col.key} className="px-3 py-2.5">—</td>;
                })}
                <td className="px-3 py-2.5" />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
