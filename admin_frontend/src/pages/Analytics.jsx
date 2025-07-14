import { useEffect, useState } from 'react';
import api from '../api';

export default function Analytics() {
  const [data, setData] = useState(null);
  const [details, setDetails] = useState(null);
  const [showDetails, setShowDetails] = useState(false);
  const [period, setPeriod] = useState('');

  async function load(refresh = false) {
    try {
      const url = refresh ? 'analytics/sales/refresh' : 'analytics/sales';
      const res = await api.get(url);
      setData(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function loadDetails() {
    try {
      const query = period ? `?period=${encodeURIComponent(period)}` : '';
      const res = await api.get(`analytics/sales/details${query}`);
      setDetails(res.data);
      setShowDetails(true);
    } catch (err) {
      console.error(err);
    }
  }

  useEffect(() => {
    load();
    window.refreshPage = load;
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Аналитика продаж</h1>
      <button className="bg-blue-600 text-white px-3 py-2 rounded" onClick={() => load(true)}>Обновить</button>
      <button className="bg-indigo-600 text-white px-3 py-2 rounded ml-2" onClick={loadDetails}>Аналитика продаж</button>
      {data && (
        <div className="grid grid-cols-2 gap-4 bg-white p-4 rounded shadow">
          <div>
            <div className="text-gray-500">Сумма ремонта</div>
            <div className="font-bold">{data.repair_sum} ₽</div>
          </div>
          <div>
            <div className="text-gray-500">Количество услуг</div>
            <div className="font-bold">{data.repair_count}</div>
          </div>
          <div>
            <div className="text-gray-500">Сумма косметики</div>
            <div className="font-bold">{data.cosmetics_sum} ₽</div>
          </div>
          <div>
            <div className="text-gray-500">Товаров продано</div>
            <div className="font-bold">{data.cosmetics_count}</div>
          </div>
          <div className="col-span-2 text-sm text-gray-500">
            Обновлено: {new Date(data.updated_at).toLocaleString('ru-RU')}
          </div>
        </div>
      )}
      {showDetails && details && (
        <div className="space-y-2 bg-white p-4 rounded shadow">
          <div className="flex items-center gap-2">
            <input
              className="border p-2 flex-grow"
              placeholder="Период"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            />
            <button className="bg-blue-600 text-white px-3 py-2 rounded" onClick={loadDetails}>
              Фильтр
            </button>
          </div>
          <div className="text-sm text-gray-600">
            Всего записей: {details.count} | Средняя стоимость: {details.avg.toFixed(2)} ₽
          </div>
          <div className="overflow-auto max-h-96">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="p-2 text-left">Период</th>
                  <th className="p-2 text-left">Номер заказа</th>
                  <th className="p-2 text-left">Сотрудник</th>
                  <th className="p-2 text-left">Наименование</th>
                  <th className="p-2 text-left">Стоимость</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {details.items.map((it, idx) => (
                  <tr key={idx}>
                    <td className="p-2">{it.period}</td>
                    <td className="p-2">{it.order_number}</td>
                    <td className="p-2">{it.employee}</td>
                    <td className="p-2">{it.item}</td>
                    <td className="p-2">{it.cost}</td>
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
