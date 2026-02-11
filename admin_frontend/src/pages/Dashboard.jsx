import { useEffect, useState } from 'react';
import api from '../api';
import Card from '../components/ui/Card';
import Skeleton, { SkeletonCard } from '../components/ui/Skeleton.jsx';

export default function Dashboard() {
  const [birthday, setBirthday] = useState(null);
  const [vacations, setVacations] = useState([]);
  const [payouts, setPayouts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      const [bRes, vRes, pRes] = await Promise.all([
        api.get('birthdays/', { params: { days: 365 } }),
        api.get('vacations/active'),
        api.get('payouts/active'),
      ]);
      setBirthday(bRes.data[0] || null);
      setVacations(vRes.data);
      setPayouts(pRes.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  function formatDateRu(value) {
    if (!value) return '';
    return new Date(value).toLocaleDateString('ru-RU');
  }

  if (loading) {
    return (
      <div className="space-y-6 max-w-3xl mx-auto">
        <Skeleton variant="title" style={{ width: '150px' }} />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <h2 className="text-2xl font-semibold">Дашборд</h2>
      <Card title="Ближайший день рождения">
        {birthday ? (
          <div>
            <div className="font-medium">{birthday.full_name}</div>
            <div className="text-sm text-gray-500">{formatDateRu(birthday.birthdate)}</div>
          </div>
        ) : (
          <div className="text-gray-500">Нет данных</div>
        )}
      </Card>
      <Card title="Сотрудники в отпуске">
        {vacations.length ? (
          <ul className="list-disc ml-4 space-y-1">
            {vacations.map((v) => (
              <li key={v.id}>{v.name}</li>
            ))}
          </ul>
        ) : (
          <div className="text-gray-500">Нет</div>
        )}
      </Card>
      <Card title="Активные запросы на выплату">
        {payouts.length ? (
          <ul className="list-disc ml-4 space-y-1">
            {payouts.map((p) => (
              <li key={p.id}>
                <span className="font-medium">{p.name}</span> — <span className="text-blue-600">{p.amount} ₽</span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-gray-500">Нет</div>
        )}
      </Card>
    </div>
  );
}
