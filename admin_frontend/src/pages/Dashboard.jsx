import { useEffect, useState } from 'react';
import api from '../api';

export default function Dashboard() {
  const [birthday, setBirthday] = useState(null);
  const [cosmetics, setCosmetics] = useState(0);
  const [vacations, setVacations] = useState([]);
  const [payouts, setPayouts] = useState([]);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const bRes = await api.get('birthdays/', { params: { days: 365 } });
      setBirthday(bRes.data[0] || null);
      const today = new Date().toISOString().slice(0, 10);
      const sRes = await api.get('analytics/sales/details', {
        params: { date_from: today, date_to: today, page_size: 1 },
      });
      setCosmetics(sRes.data.total || 0);
      const vRes = await api.get('vacations/active');
      setVacations(vRes.data);
      const pRes = await api.get('payouts/active');
      setPayouts(pRes.data);
    } catch (err) {
      console.error(err);
    }
  }

  function formatDateRu(value) {
    if (!value) return '';
    return new Date(value).toLocaleDateString('ru-RU');
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <h2 className="text-2xl font-semibold">Дашборд</h2>
      <div className="space-y-2">
        <h3 className="text-xl font-semibold">Ближайший день рождения</h3>
        {birthday ? (
          <div className="bg-white border rounded shadow p-3">
            <div>{birthday.full_name}</div>
            <div>{formatDateRu(birthday.birthdate)}</div>
          </div>
        ) : (
          <div>Нет данных</div>
        )}
      </div>
      <div className="space-y-2">
        <h3 className="text-xl font-semibold">Продажи косметики сегодня</h3>
        <div className="bg-white border rounded shadow p-3">
          {cosmetics} ₽
        </div>
      </div>
      <div className="space-y-2">
        <h3 className="text-xl font-semibold">Сотрудники в отпуске</h3>
        {vacations.length ? (
          <ul className="list-disc ml-4">
            {vacations.map((v) => (
              <li key={v.id}>{v.name}</li>
            ))}
          </ul>
        ) : (
          <div>Нет</div>
        )}
      </div>
      <div className="space-y-2">
        <h3 className="text-xl font-semibold">Активные запросы на выплату</h3>
        {payouts.length ? (
          <ul className="list-disc ml-4">
            {payouts.map((p) => (
              <li key={p.id}>
                {p.name} — {p.amount} ₽
              </li>
            ))}
          </ul>
        ) : (
          <div>Нет</div>
        )}
      </div>
    </div>
  );
}
