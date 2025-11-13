import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArchiveRestore, RefreshCw } from 'lucide-react';
import api from '../api';

export default function ArchivedEmployees() {
  const [employees, setEmployees] = useState([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      setLoading(true);
      const res = await api.get('employees/', { params: { archived: true } });
      setEmployees(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function restore(id) {
    if (!window.confirm('Вернуть сотрудника из архива?')) return;
    try {
      await api.post(`employees/${id}/restore`);
      load();
    } catch (err) {
      console.error(err);
      alert('Не удалось восстановить сотрудника');
    }
  }

  const filtered = employees.filter((e) => {
    const text = `${e.full_name} ${e.name}`.toLowerCase();
    return text.includes(query.toLowerCase());
  });

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-3">
        <h2 className="text-2xl font-semibold">Архив сотрудников</h2>
        <button
          className="btn bg-gray-100 text-gray-800 hover:bg-gray-200 flex items-center gap-2"
          onClick={load}
          disabled={loading}
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Обновить
        </button>
        <Link className="btn" to="/admin/employees">
          Назад к списку
        </Link>
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <input
          className="input flex-grow"
          placeholder="Поиск по имени"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="text-sm text-gray-500">
          Всего: {filtered.length}
        </div>
      </div>
      <div className="overflow-auto border rounded shadow bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="p-2 text-left">Имя</th>
              <th className="p-2 text-left">ФИО</th>
              <th className="p-2 text-left">Телефон</th>
              <th className="p-2 text-left">Статус</th>
              <th className="p-2 text-left">Место</th>
              <th className="p-2 text-left">Дата архивации</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {filtered.map((e) => (
              <tr key={e.id} className="bg-neutral-50">
                <td className="p-2">{e.name}</td>
                <td className="p-2">{e.full_name}</td>
                <td className="p-2">{e.phone}</td>
                <td className="p-2">{e.status}</td>
                <td className="p-2">{e.work_place}</td>
                <td className="p-2 text-sm text-gray-500">
                  {e.archived_at ? new Date(e.archived_at).toLocaleString('ru-RU') : '—'}
                </td>
                <td className="p-2 text-right">
                  <button
                    className="text-green-600 hover:text-green-800 flex items-center gap-1"
                    onClick={() => restore(e.id)}
                  >
                    <ArchiveRestore size={16} /> Вернуть
                  </button>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan="7" className="p-4 text-center text-gray-500">
                  Нет архивных сотрудников
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
