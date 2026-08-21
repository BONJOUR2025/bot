import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArchiveRestore, RefreshCw } from 'lucide-react';
import api from '../api';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';

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
        <div>
          <span className="ui-eyebrow mb-3">{employees.length ? `В архиве: ${employees.length}` : 'Архив пуст'}</span>
          <h2 className="text-2xl font-semibold">Архив сотрудников</h2>
        </div>
        <button
          className="btn bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text)] hover:bg-[color:var(--color-control-bg-hover)] flex items-center gap-2"
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
        <div className="text-sm text-[color:var(--color-text-muted)]">
          Всего: {filtered.length}
        </div>
      </div>
      <ResponsiveTable
        data={filtered}
        keyFn={(e) => e.id}
        rowClass={() => 'bg-[color:var(--color-bg-subtle)]'}
        emptyText="Нет архивных сотрудников"
        columns={[
          { label: 'ФИО', key: 'full_name', primary: true },
          { label: 'Имя', key: 'name', mobileHide: true },
          { label: 'Телефон', key: 'phone' },
          { label: 'Статус', key: 'status' },
          { label: 'Место', key: 'work_place' },
          {
            label: 'Дата архивации',
            render: (e) => e.archived_at ? new Date(e.archived_at).toLocaleString('ru-RU') : '—',
            mobileHide: true,
          },
          {
            label: '',
            isAction: true,
            cellClass: 'text-right',
            render: (e) => (
              <button
                className="text-green-600 hover:text-green-800 flex items-center gap-1"
                onClick={() => restore(e.id)}
              >
                <ArchiveRestore size={16} /> Вернуть
              </button>
            ),
          },
        ]}
      />
    </div>
  );
}
