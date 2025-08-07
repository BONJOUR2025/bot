import { useEffect, useState } from 'react';
import { Cake, Calendar } from 'lucide-react';
import api from '../api';

export default function Birthdays() {
  const [list, setList] = useState([]);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const res = await api.get('birthdays/', { params: { days: 365 } });
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

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <h2 className="text-2xl font-semibold flex items-center gap-2">
        <Cake size={24} /> Дни рождения сотрудников
      </h2>
      <div className="flex flex-col gap-2">
        {list.map((b) => (
          <div
            key={b.user_id}
            className="bg-white rounded border shadow p-3 flex items-center justify-between"
          >
            <div className="flex flex-col">
              <span className="font-medium">{b.full_name}</span>
              {b.phone && (
                <span className="text-gray-500 text-sm">{b.phone}</span>
              )}
            </div>
            <div className="flex items-center gap-1 text-sm">
              <Calendar size={16} /> {formatDateRu(b.birthdate)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
