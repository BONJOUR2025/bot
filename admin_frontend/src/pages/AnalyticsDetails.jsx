import { useState } from 'react';
import api from '../api';

const LEADER_OPTIONS = [
  { value: 'cosmetics_avg', label: 'По косметике (среднее в день)' },
  { value: 'cosmetics_total', label: 'По косметике (общая сумма)' },
  { value: 'repair_avg', label: 'По ремонту (среднее в день)' },
  { value: 'repair_total', label: 'По ремонту (общая сумма)' },
  { value: 'shoes_sum', label: 'По обуви (общая сумма)' },
  { value: 'shoes_count', label: 'По обуви (количество)' },
  { value: 'revenue_total', label: 'По совокупной выручке' },
];

export default function AnalyticsDetails() {
  const [period, setPeriod] = useState({ from: '', to: '' });
  const [items, setItems] = useState([]);
  const [leaderField, setLeaderField] = useState('revenue_total');

  async function load() {
    try {
      const params = {
        date_from: period.from || undefined,
        date_to: period.to || undefined,
      };
      const res = await api.get('analytics/detailed', { params });
      setItems(res.data.items || []);
    } catch (err) {
      console.error(err);
    }
  }

  const leaders = [...items]
    .sort((a, b) => Number(b[leaderField]) - Number(a[leaderField]))
    .slice(0, 3);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Подробная аналитика</h1>
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="date"
          className="border p-2"
          value={period.from}
          onChange={(e) => setPeriod({ ...period, from: e.target.value })}
        />
        <input
          type="date"
          className="border p-2"
          value={period.to}
          onChange={(e) => setPeriod({ ...period, to: e.target.value })}
        />
        <button onClick={load} className="btn">
          Показать
        </button>
      </div>

      <div className="overflow-auto">
        <table className="min-w-full text-sm bg-white rounded shadow">
          <thead className="bg-gray-50">
            <tr>
              <th className="p-2 text-left">Сотрудник</th>
              <th className="p-2 text-left">Кол-во смен</th>
              <th className="p-2 text-left">Косметика ср/день</th>
              <th className="p-2 text-left">Косметика всего</th>
              <th className="p-2 text-left">Ремонт ср/день</th>
              <th className="p-2 text-left">Ремонт всего</th>
              <th className="p-2 text-left">Пар обуви</th>
              <th className="p-2 text-left">Обувь сумма</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {items.map((it, idx) => (
              <tr key={idx}>
                <td className="p-2">{it.employee}</td>
                <td className="p-2">{it.shifts}</td>
                <td className="p-2">{it.cosmetics_avg.toFixed(2)}</td>
                <td className="p-2">{it.cosmetics_total}</td>
                <td className="p-2">{it.repair_avg.toFixed(2)}</td>
                <td className="p-2">{it.repair_total}</td>
                <td className="p-2">{it.shoes_count}</td>
                <td className="p-2">{it.shoes_sum}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-white p-4 rounded shadow space-y-2 max-w-sm">
        <select
          className="border p-2 w-full"
          value={leaderField}
          onChange={(e) => setLeaderField(e.target.value)}
        >
          {LEADER_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="p-2 text-left">Сотрудник</th>
              <th className="p-2 text-left">Значение</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {leaders.map((l, idx) => (
              <tr key={idx}>
                <td className="p-2">{l.employee}</td>
                <td className="p-2">{l[leaderField]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

