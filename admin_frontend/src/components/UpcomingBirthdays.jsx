import { useEffect, useState } from 'react';
import api from '../api';

export default function UpcomingBirthdays({ days = 30 }) {
  const [list, setList] = useState([]);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const res = await api.get('birthdays/', { params: { days } });
      setList(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  function formatDateRu(value) {
    return new Date(value).toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'long',
    });
  }

  if (!list.length) return null;

  return (
    <div className="space-y-2">
      <h3 className="text-xl font-semibold">Ближайшие дни рождения</h3>
      <div className="flex flex-wrap gap-2">
        {list.map((b) => (
          <div
            key={b.user_id}
            className="bg-white border rounded shadow p-3 text-sm"
          >
            <div>🎂 {b.full_name}</div>
            <div>📅 {formatDateRu(b.birthdate)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
