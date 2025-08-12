import { useState } from 'react';
import api from '../api';

const SALONS = [
  { code: 'mercury', label: 'Меркурий' },
  { code: 'okhta', label: 'Охта-Молл' },
  { code: 'ozerki', label: 'Озерки' },
  { code: 'passage', label: 'Пассаж' },
  { code: 'akpark', label: 'Академ Парк' },
];

export default function AnalyticsSalons() {
  const [selected, setSelected] = useState(null);
  const [rows, setRows] = useState([]);

  async function load(code) {
    try {
      const res = await api.get('analytics/salons', { params: { salon: code } });
      setRows(res.data.items || []);
    } catch (err) {
      console.error(err);
    }
  }

  function selectSalon(code) {
    setSelected(code);
    load(code);
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Аналитика по салонам</h1>
      {!selected && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {SALONS.map((s) => (
            <button
              key={s.code}
              className="p-4 bg-white rounded shadow hover:bg-muted/20 transition"
              onClick={() => selectSalon(s.code)}
            >
              {s.label}
            </button>
          ))}
        </div>
      )}
      {selected && (
        <div className="space-y-4">
          <button className="btn" onClick={() => setSelected(null)}>
            Назад
          </button>
          <div className="overflow-auto">
            <table className="min-w-full text-sm bg-white rounded shadow">
              <thead className="bg-gray-50">
                <tr>
                  <th className="p-2 text-left">Дата</th>
                  <th className="p-2 text-left">Количество посетителей</th>
                  <th className="p-2 text-left">Выручка</th>
                  <th className="p-2 text-left">Количество сделок</th>
                  <th className="p-2 text-left">RPV</th>
                  <th className="p-2 text-left">Администратор</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {rows.map((row, idx) => (
                  <tr key={idx}>
                    <td className="p-2">{row.date}</td>
                    <td className="p-2">{row.visitors}</td>
                    <td className="p-2">{row.revenue}</td>
                    <td className="p-2">{row.deals}</td>
                    <td className="p-2">{row.rpv}</td>
                    <td className="p-2">{row.admin}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
