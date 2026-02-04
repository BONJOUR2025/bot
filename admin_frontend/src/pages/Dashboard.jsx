import { useEffect, useState } from 'react';
import api from '../api';
import Card from '../components/ui/Card';

export default function Dashboard() {
  const [birthday, setBirthday] = useState(null);
  const [vacations, setVacations] = useState([]);
  const [payouts, setPayouts] = useState([]);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const bRes = await api.get('birthdays/', { params: { days: 365 } });
      setBirthday(bRes.data[0] || null);
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
      <Card title="Ближайший день рождения">
        {birthday ? (
          <div>
            <div>{birthday.full_name}</div>
            <div>{formatDateRu(birthday.birthdate)}</div>
          </div>
        ) : (
          <div>Нет данных</div>
        )}
      </Card>
      <Card title="Сотрудники в отпуске">
        {vacations.length ? (
          <ul className="list-disc ml-4">
            {vacations.map((v) => (
              <li key={v.id}>{v.name}</li>
            ))}
          </ul>
        ) : (
          <div>Нет</div>
        )}
      </Card>
      <Card title="Активные запросы на выплату">
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
      </Card>
    </div>
  );
}




