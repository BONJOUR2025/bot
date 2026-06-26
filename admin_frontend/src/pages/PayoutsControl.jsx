import { useEffect, useState } from 'react';
import api from '../api';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';

const warningDescriptions = {
  limit_exceeded: 'Сумма выплат за месяц превышает лимит',
  pending_too_long: 'Заявка в ожидании более 48 часов',
  frequent_request: 'Между выплатами прошло менее 3 дней',
  changed_bank_data: 'Реквизиты отличаются от последних подтверждённых',
  manual_created: 'Заявка создана вручную администратором',
  inactive_employee: 'Сотрудник помечен как неактивный',
};

const STATUS_OPTIONS = ['Ожидает', 'Одобрено', 'Отклонено', 'Выплачено'];

export default function PayoutsControl() {
  const [list, setList] = useState([]);
  const [filters, setFilters] = useState({
    type: '',
    status: '',
    method: '',
    from: '',
    to: '',
    warnings: [],
  });

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const params = {
        type: filters.type || undefined,
        status: filters.status || undefined,
        method: filters.method || undefined,
        date_from: filters.from || undefined,
        date_to: filters.to || undefined,
      };
      const res = await api.get('payouts/control', { params });
      setList(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  const filtered = list.filter((i) =>
    filters.warnings.length
      ? filters.warnings.every((w) => i.warnings.includes(w))
      : true
  );

  function toggleWarning(w) {
    setFilters((prev) => {
      const warnings = prev.warnings.includes(w)
        ? prev.warnings.filter((x) => x !== w)
        : [...prev.warnings, w];
      return { ...prev, warnings };
    });
  }

  function rowColor(ws) {
    if (ws.includes('limit_exceeded') || ws.includes('inactive_employee'))
      return 'bg-red-50';
    if (ws.includes('pending_too_long') || ws.includes('changed_bank_data'))
      return 'bg-orange-50';
    if (ws.includes('manual_created')) return 'bg-blue-50';
    return '';
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <h2 className="text-2xl font-semibold tracking-tight text-gray-800">
        Контроль выплат
      </h2>
      <div className="flex flex-wrap gap-2 items-end">
        <select
          className="input text-sm"
          value={filters.type}
          onChange={(e) => setFilters({ ...filters, type: e.target.value })}
        >
          <option value="">Все типы</option>
          <option value="advance">Аванс</option>
          <option value="final">Финальная</option>
          <option value="compensation">Компенсация</option>
        </select>
        <select
          className="input text-sm"
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        >
          <option value="">Все статусы</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          className="input text-sm"
          value={filters.method}
          onChange={(e) => setFilters({ ...filters, method: e.target.value })}
        >
          <option value="">Все способы</option>
          <option value="card">На карту</option>
          <option value="cash">Наличными</option>
          <option value="account">На счёт</option>
        </select>
        <div className="flex flex-col sm:flex-row sm:flex-wrap gap-2 w-full sm:w-auto">
          <input
            type="date"
            className="input text-sm w-full sm:w-auto"
            value={filters.from}
            onChange={(e) => setFilters({ ...filters, from: e.target.value })}
          />
          <input
            type="date"
            className="input text-sm w-full sm:w-auto"
            value={filters.to}
            onChange={(e) => setFilters({ ...filters, to: e.target.value })}
          />
        </div>
        <button className="btn" onClick={load}>
          Применить
        </button>
        <div className="flex flex-wrap gap-2 border border-gray-300 rounded p-2 bg-gray-50 text-xs w-full sm:w-auto">
          {Object.keys(warningDescriptions).map((w) => (
            <label key={w} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={filters.warnings.includes(w)}
                onChange={() => toggleWarning(w)}
              />
              {warningDescriptions[w]}
            </label>
          ))}
        </div>
      </div>
      <ResponsiveTable
        data={filtered}
        keyFn={(p) => p.id}
        rowClass={(p) => rowColor(p.warnings)}
        emptyText="Нет данных"
        columns={[
          { label: 'ФИО', key: 'name', primary: true },
          { label: 'Тип', key: 'type' },
          { label: 'Способ', key: 'method' },
          {
            label: 'Сумма',
            headerClass: 'text-right',
            cellClass: 'text-right whitespace-nowrap',
            render: (p) => (
              <span className="text-[color:var(--color-primary)] font-medium tabular-nums">
                {Number(p.amount || 0).toLocaleString('ru-RU')} ₽
              </span>
            ),
          },
          { label: 'Статус', key: 'status' },
          {
            label: 'Дата',
            render: (p) => <span className="text-xs">{p.date}</span>,
          },
          {
            label: '⚠️ Предупреждения',
            render: (p) => (
              <div className="flex flex-wrap gap-1">
                {p.warnings.map((w) => (
                  <span
                    key={w}
                    title={warningDescriptions[w]}
                    className="inline-block bg-gray-200 px-1 rounded text-xs"
                  >
                    {w}
                  </span>
                ))}
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}

