import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArchiveRestore, Lock, RefreshCw } from 'lucide-react';
import api from '../api';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';

// Срок хранения в архиве, посчитанный от реальной archived_at до текущей
// даты — не декоративное число, а фактический возраст записи в «холодном
// хранилище».
function archiveAgeLabel(archivedAt) {
  if (!archivedAt) return null;
  const d = new Date(archivedAt);
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  let months = (now.getFullYear() - d.getFullYear()) * 12 + (now.getMonth() - d.getMonth());
  if (now.getDate() < d.getDate()) months -= 1;
  months = Math.max(0, months);
  if (months < 1) return '< 1 мес';
  const years = Math.floor(months / 12);
  const rem = months % 12;
  if (years === 0) return `${months} мес`;
  if (rem === 0) return `${years} г`;
  return `${years} г ${rem} мес`;
}

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

  // Реальные min/max по archived_at среди загруженных записей — не
  // выдуманные даты, а фактический диапазон хранения архива.
  const archiveStats = useMemo(() => {
    const dated = employees
      .map((e) => e.archived_at)
      .filter(Boolean)
      .map((v) => new Date(v))
      .filter((d) => !Number.isNaN(d.getTime()));
    if (!dated.length) return { oldest: null, newest: null };
    const times = dated.map((d) => d.getTime());
    return {
      oldest: new Date(Math.min(...times)),
      newest: new Date(Math.max(...times)),
    };
  }, [employees]);

  const fmtDate = (d) => d.toLocaleDateString('ru-RU');

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <span className="ui-eyebrow mb-3">{employees.length ? `В архиве: ${employees.length}` : 'Архив пуст'}</span>
          <h2 className="text-2xl font-semibold">Архив сотрудников</h2>
        </div>
        {/* Телеметрия опечатанного хранилища: реальное количество записей
            и реальный диапазон дат archived_at — не декоративные цифры. */}
        <div className="archive-fui-stamp">
          <span>ЗАПИСЕЙ: <b>{employees.length}</b></span>
          {archiveStats.oldest && (
            <>
              <span className="sep">/</span>
              <span>СТАРЕЙШАЯ ЗАПИСЬ: <b>{fmtDate(archiveStats.oldest)}</b></span>
            </>
          )}
          {archiveStats.newest && (
            <>
              <span className="sep">/</span>
              <span>НОВЕЙШАЯ: <b>{fmtDate(archiveStats.newest)}</b></span>
            </>
          )}
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
          {
            label: 'ФИО',
            primary: true,
            render: (e) => {
              const age = archiveAgeLabel(e.archived_at);
              return (
                <div className="flex flex-col gap-1">
                  <span>{e.full_name}</span>
                  {age && (
                    <span className="archive-fui-tag">
                      <Lock size={10} /> АРХИВ · {age}
                    </span>
                  )}
                </div>
              );
            },
          },
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
                className="ui-tap-44 text-green-600 hover:text-green-800 flex items-center gap-1"
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
