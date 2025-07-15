import { useEffect, useState } from 'react';
import api from '../api';

export default function Analytics() {
  const [data, setData] = useState(null);
  const [details, setDetails] = useState(null);
  const [showDetails, setShowDetails] = useState(false);
  const [filters, setFilters] = useState({
    from: '',
    to: '',
    code: '',
    name: '',
    doc: '',
  });

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
      const params = {
        date_from: filters.from || undefined,
        date_to: filters.to || undefined,
        code_substr: filters.code || undefined,
        name_substr: filters.name || undefined,
        doc_num_substr: filters.doc || undefined,
      };
      const res = await api.get('analytics/sales/details', { params });
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
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="date"
              className="border p-2"
              value={filters.from}
              onChange={(e) => setFilters({ ...filters, from: e.target.value })}
            />
            <input
              type="date"
              className="border p-2"
              value={filters.to}
              onChange={(e) => setFilters({ ...filters, to: e.target.value })}
            />
            <input
              className="border p-2"
              placeholder="Код"
              value={filters.code}
              onChange={(e) => setFilters({ ...filters, code: e.target.value })}
            />
            <input
              className="border p-2 flex-grow"
              placeholder="Название"
              value={filters.name}
              onChange={(e) => setFilters({ ...filters, name: e.target.value })}
            />
            <input
              className="border p-2"
              placeholder="№ заказа"
              value={filters.doc}
              onChange={(e) => setFilters({ ...filters, doc: e.target.value })}
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
                  <th className="p-2 text-left">Дата</th>
                  <th className="p-2 text-left">№ док.</th>
                  <th className="p-2 text-left">Creator</th>
                  <th className="p-2 text-left">Описание</th>
                  <th className="p-2 text-left">Код товара</th>
                  <th className="p-2 text-left">Наименование</th>
                  <th className="p-2 text-left">Сумма</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {details.items.map((raw, idx) => {
                  const it = {
                    doc_date: raw.doc_date || raw.period,
                    doc_num: raw.doc_num || raw.doc_number || raw.order_number,
                    creator_id: raw.creator_id || raw.employee,
                    description: raw.description || raw.item,
                    item_code: raw.item_code || '',
                    item_name: raw.item_name || raw.item,
                    kredit: raw.kredit ?? raw.cost,
                  };
                  return (
                    <tr key={idx}>
                      <td className="p-2">{it.doc_date}</td>
                      <td className="p-2">{it.doc_num}</td>
                      <td className="p-2">{it.creator_id}</td>
                      <td className="p-2">{it.description}</td>
                      <td className="p-2">{it.item_code}</td>
                      <td className="p-2">{it.item_name}</td>
                      <td className="p-2">{it.kredit}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
