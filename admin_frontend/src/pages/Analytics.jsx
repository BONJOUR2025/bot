import { useEffect, useState } from 'react';
import api from '../api';

const EMPLOYEE_MAP = {
  '0102': 'Вера 0102',
  '2602': 'Анастасия 2602',
  '7272': 'Арина 7272',
  '1505': 'Александр 1505',
  '2404': 'Эмиль 2404',
  '5984': 'Полина 5984',
  '0704': 'Наталья 0704',
  '2201': 'Катя 2201',
  '1606': 'Лали 1606',
  '0104': 'Екатерина 0104',
  '2006': 'Ирина 2006',
  '1802': 'Полина 1802',
  '1996': 'Вероника 1996',
  '2405': 'Ира 2405',
  '3007': 'Юля 3007',
  '2104': 'Алекс 2104',
  '0208': 'Марина 0208',
};

function mapEmployeeByCode(value) {
  const match = String(value || '').match(/(\d{4})\s*$/);
  if (match) {
    return EMPLOYEE_MAP[match[1]] || value;
  }
  return value;
}

function mapEmployee(value) {
  return mapEmployeeByCode(value);
}

export default function Analytics() {
  const [data, setData] = useState(null);
  const [details, setDetails] = useState(null);
  const [showDetails, setShowDetails] = useState(false);
  const [rating, setRating] = useState([]);
  const [ratingRange, setRatingRange] = useState({ from: '', to: '' });
  const [sort, setSort] = useState('');
  const [pageSize, setPageSize] = useState(50);
  const [filters, setFilters] = useState({
    from: '',
    to: '',
    code: '',
    name: '',
    doc: '',
    employee: '',
    type: 'all',
  });

  const employeeOptions = Object.entries(EMPLOYEE_MAP).map(([code, name]) => ({
    code,
    name,
  }));

  function formatDateRu(value) {
    if (!value) return '';
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString('ru-RU');
  }

  async function load(refresh = false) {
    try {
      const res = refresh
        ? await api.post('analytics/sales/refresh')
        : await api.get('analytics/sales');
      setData(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function loadDetails(size = pageSize) {
    try {
      const params = {
        date_from: filters.from || undefined,
        date_to: filters.to || undefined,
        code_substr: filters.code || undefined,
        name_substr: filters.name || undefined,
        doc_num_substr: filters.doc || undefined,
        employee: filters.employee || undefined,
        item_type: filters.type !== 'all' ? filters.type : undefined,
        page_size: size,
      };
      const res = await api.get('analytics/sales/details', { params });
      setDetails(res.data);
      setShowDetails(true);
    } catch (err) {
      console.error(err);
    }
  }

  async function loadRating() {
    try {
      const params = {
        date_from: ratingRange.from || undefined,
        date_to: ratingRange.to || undefined,
        item_type: filters.type !== 'all' ? filters.type : undefined,
      };
      const res = await api.get('analytics/sales/rating', { params });
      setRating(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  useEffect(() => {
    load();
    window.refreshPage = load;
  }, []);

  // Подготовка данных с преобразованием сотрудников по коду
  const mappedDetails = details?.items
    ? details.items.map((raw) => {
        const empRaw = raw.description || raw.employee || '';
        const empName = mapEmployeeByCode(empRaw);
        return {
          date: raw.doc_date || raw.period,
          number: raw.doc_num || raw.doc_number || raw.order_number,
          employee: empName,
          code: raw.item_code || '',
          name: raw.item_name || raw.item,
          cost: raw.kredit ?? raw.cost,
          type: raw.item_type || 'cosmetics',
        };
      })
    : [];

  // Фильтрация по сотруднику
  const filteredDetails = filters.employee
    ? mappedDetails.filter((item) => item.employee === filters.employee)
    : mappedDetails;

  const sortedDetails = [...filteredDetails];
  if (sort === 'employee') {
    sortedDetails.sort((a, b) => a.employee.localeCompare(b.employee));
  } else if (sort === 'cost') {
    sortedDetails.sort((a, b) => Number(b.cost) - Number(a.cost));
  }

  // Итоги
  const goodsCount = filteredDetails.filter((item) => Number(item.cost) > 0).length;
  const totalSum = filteredDetails.reduce(
    (sum, item) => (Number(item.cost) > 0 ? sum + Number(item.cost) : sum),
    0
  );

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Аналитика продаж</h1>
      <button className="btn" onClick={() => load(true)}>
        Обновить
      </button>
      <button className="btn ml-2" onClick={() => loadDetails()}>
        Аналитика продаж
      </button>

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

      {showDetails && (
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
            <select
              className="border p-2"
              value={filters.employee}
              onChange={(e) => setFilters({ ...filters, employee: e.target.value })}
            >
              <option value="">Все сотрудники</option>
              {employeeOptions.map((opt) => (
                <option key={opt.code} value={opt.name}>
                  {opt.name}
                </option>
              ))}
            </select>
            <select
              className="border p-2"
              value={filters.type}
              onChange={(e) => setFilters({ ...filters, type: e.target.value })}
            >
              <option value="all">Все</option>
              <option value="cosmetics">Косметика</option>
              <option value="services">Услуги</option>
            </select>
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
            <select
              className="border p-2"
              value={pageSize}
              onChange={(e) => {
                const val = Number(e.target.value);
                setPageSize(val);
                loadDetails(val);
              }}
            >
              {[50, 100, 150, 200, 500].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            <select
              className="border p-2"
              value={sort}
              onChange={(e) => setSort(e.target.value)}
            >
              <option value="">Без сортировки</option>
              <option value="employee">По сотруднику</option>
              <option value="cost">По сумме</option>
            </select>
            <button className="btn" onClick={() => loadDetails()}>
              Фильтр
            </button>
          </div>

          <div className="text-sm text-gray-600">
            Всего записей: {filteredDetails.length} | Количество товаров: {goodsCount} | Общая сумма: {totalSum} ₽
          </div>

          <div className="overflow-auto max-h-96">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="p-2 text-left">Дата</th>
                  <th className="p-2 text-left">№ заказа</th>
                  <th className="p-2 text-left">Сотрудник</th>
                  <th className="p-2 text-left">Код товара</th>
                  <th className="p-2 text-left">Наименование</th>
                  <th className="p-2 text-left">Сумма</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {sortedDetails.map((it, idx) => (
                  <tr key={idx}>
                    <td className="p-2">{formatDateRu(it.date)}</td>
                    <td className="p-2">{it.number}</td>
                    <td className="p-2">{mapEmployee(it.employee)}</td>
                    <td className="p-2">{it.code}</td>
                    <td className="p-2">{it.name}</td>
                    <td className="p-2">{it.cost}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 space-y-2">
            <h3 className="font-semibold">Рейтинг сотрудников</h3>
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="date"
                className="border p-2"
                value={ratingRange.from}
                onChange={(e) => setRatingRange({ ...ratingRange, from: e.target.value })
                }
              />
              <input
                type="date"
                className="border p-2"
                value={ratingRange.to}
                onChange={(e) => setRatingRange({ ...ratingRange, to: e.target.value })
                }
              />
              <button className="btn" onClick={loadRating}>
                Показать
              </button>
            </div>

            <div className="overflow-auto max-h-60">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="p-2 text-left">Сотрудник</th>
                    <th className="p-2 text-left">Сумма</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {rating.map((r, idx) => (
                    <tr key={idx}>
                      <td className="p-2">{mapEmployee(r.description || r.employee)}</td>
                      <td className="p-2">{r.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}






