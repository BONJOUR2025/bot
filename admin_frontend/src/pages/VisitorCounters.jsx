import { useEffect, useState } from 'react';
import { Users } from 'lucide-react';
import api from '../api';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

function daysAgoStr(days) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

export default function VisitorCounters() {
  const [summary, setSummary] = useState([]);
  const [salons, setSalons] = useState([]);
  const [filters, setFilters] = useState({ from: daysAgoStr(6), to: todayStr(), salon_id: '' });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSalons();
  }, []);

  useEffect(() => {
    load();
  }, [filters]);

  async function loadSalons() {
    try {
      const res = await api.get('salons/');
      setSalons(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function load() {
    setLoading(true);
    try {
      const params = {
        date_from: filters.from || undefined,
        date_to: filters.to || undefined,
        salon_id: filters.salon_id || undefined,
      };
      const res = await api.get('visitor-events/summary', { params });
      setSummary(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  const totals = summary.reduce(
    (acc, row) => ({
      in: acc.in + row.in_count,
      out: acc.out + row.out_count,
    }),
    { in: 0, out: 0 }
  );

  const columns = [
    { label: 'Дата', key: 'date', primary: true },
    { label: 'Салон', render: (row) => row.salon_name || row.salon_id },
    { label: 'Вошло', render: (row) => row.in_count },
    { label: 'Вышло', render: (row) => row.out_count },
    { label: 'Сейчас в зале', render: (row) => row.net },
  ];

  return (
    <div className="space-y-6">
      <h2 className="flex items-center gap-2 text-2xl font-semibold">
        <Users size={24} /> Счётчик посетителей
      </h2>

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1">С даты</label>
          <input
            type="date"
            className="input"
            value={filters.from}
            onChange={(e) => setFilters((f) => ({ ...f, from: e.target.value }))}
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">По дату</label>
          <input
            type="date"
            className="input"
            value={filters.to}
            onChange={(e) => setFilters((f) => ({ ...f, to: e.target.value }))}
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Салон</label>
          <select
            className="input"
            value={filters.salon_id}
            onChange={(e) => setFilters((f) => ({ ...f, salon_id: e.target.value }))}
          >
            <option value="">Все салоны</option>
            {salons.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex gap-4 text-sm text-gray-600">
        <span>Всего вошло: <strong className="text-gray-900">{totals.in}</strong></span>
        <span>Всего вышло: <strong className="text-gray-900">{totals.out}</strong></span>
      </div>

      {loading ? (
        <p className="text-gray-500">Загрузка…</p>
      ) : (
        <ResponsiveTable
          columns={columns}
          data={summary}
          keyFn={(row) => `${row.date}-${row.salon_id}`}
          emptyText="Нет данных за выбранный период"
        />
      )}
    </div>
  );
}
