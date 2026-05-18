import { useEffect, useState } from 'react';
import api from '../api';
import { useViewport } from '../providers/ViewportProvider.jsx';

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
  const { isMobile } = useViewport();
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
          className="border border-gray-300 p-2 rounded text-sm"
          value={filters.type}
          onChange={(e) => setFilters({ ...filters, type: e.target.value })}
        >
          <option value="">Все типы</option>
          <option value="advance">Аванс</option>
          <option value="final">Финальная</option>
          <option value="compensation">Компенсация</option>
        </select>
        <select
          className="border border-gray-300 p-2 rounded text-sm"
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
          className="border border-gray-300 p-2 rounded text-sm"
          value={filters.method}
          onChange={(e) => setFilters({ ...filters, method: e.target.value })}
        >
          <option value="">Все способы</option>
          <option value="card">На карту</option>
          <option value="cash">Наличными</option>
          <option value="account">На счёт</option>
        </select>
        <input
          type="date"
          className="border border-gray-300 p-2 rounded text-sm"
          value={filters.from}
          onChange={(e) => setFilters({ ...filters, from: e.target.value })}
        />
        <input
          type="date"
          className="border border-gray-300 p-2 rounded text-sm"
          value={filters.to}
          onChange={(e) => setFilters({ ...filters, to: e.target.value })}
        />
        <button className="btn" onClick={load}>
          Применить
        </button>
        <div className="flex flex-wrap gap-2 border border-gray-300 rounded p-2 bg-gray-50 text-xs">
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
      {isMobile ? (
        <div className="space-y-3">
          {filtered.map((p) => (
            <div key={p.id} className={`border rounded-xl bg-white shadow-sm overflow-hidden ${rowColor(p.warnings)}`}>
              <div className="px-4 py-3 border-b bg-gray-50 text-sm font-medium">{p.name}</div>
              <div className="px-4 py-2 space-y-1.5 text-sm">
                <div className="flex justify-between"><span className="text-gray-500">Сумма</span><span className="text-blue-800 font-medium">{p.amount} ₽</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Тип</span><span>{p.type}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Статус</span><span>{p.status}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Дата</span><span className="text-xs">{p.date}</span></div>
                {p.warnings.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1">
                    {p.warnings.map((w) => (
                      <span key={w} title={warningDescriptions[w]} className="inline-block bg-gray-200 px-1 rounded text-xs">{w}</span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="border rounded-xl bg-white shadow-sm p-4 text-center text-gray-500 italic">Нет данных</div>
          )}
        </div>
      ) : (
        <div className="overflow-auto border rounded shadow">
          <table className="min-w-[1100px] divide-y divide-gray-200 bg-white text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2 text-left">ФИО</th>
                <th className="px-4 py-2 text-left">Тип</th>
                <th className="px-4 py-2 text-left">Способ</th>
                <th className="px-4 py-2 text-left">Сумма</th>
                <th className="px-4 py-2 text-left">Статус</th>
                <th className="px-4 py-2 text-left">Дата</th>
                <th className="px-4 py-2 text-left">⚠️ Предупреждения</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((p) => (
                <tr key={p.id} className={rowColor(p.warnings)}>
                  <td className="px-4 py-2">{p.name}</td>
                  <td className="px-4 py-2">{p.type}</td>
                  <td className="px-4 py-2">{p.method}</td>
                  <td className="px-4 py-2 text-blue-800 font-medium">
                    {p.amount} ₽
                  </td>
                  <td className="px-4 py-2">{p.status}</td>
                  <td className="px-4 py-2 text-xs">{p.date}</td>
                  <td className="px-4 py-2 space-x-1">
                    {p.warnings.map((w) => (
                      <span
                        key={w}
                        title={warningDescriptions[w]}
                        className="inline-block bg-gray-200 px-1 rounded text-xs mr-1"
                      >
                        {w}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan="7" className="px-4 py-3 text-center text-gray-500 italic">
                    Нет данных
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}





