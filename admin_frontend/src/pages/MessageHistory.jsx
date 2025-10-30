import { useEffect, useMemo, useState } from 'react';
import { MessageCircle, Users, AlertCircle, Clock, RefreshCcw, Trash2 } from 'lucide-react';
import api from '../api';

const typeFilters = [
  { value: 'all', label: 'Все сообщения' },
  { value: 'direct', label: 'Персональные' },
  { value: 'broadcast', label: 'Рассылки' },
];

function StatusBadge({ status }) {
  const normalized = (status || '').toLowerCase();
  let color = 'bg-gray-200 text-gray-700';
  if (normalized.includes('ошибка') || normalized.includes('error')) {
    color = 'bg-red-100 text-red-700';
  } else if (normalized.includes('отправлено') || normalized.includes('успех')) {
    color = 'bg-green-100 text-green-700';
  } else if (normalized.includes('ожид') || normalized.includes('pending')) {
    color = 'bg-yellow-100 text-yellow-700';
  }
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${color}`}>
      {status || '—'}
    </span>
  );
}

export default function MessageHistory() {
  const [entries, setEntries] = useState([]);
  const [expandedId, setExpandedId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [typeFilter, setTypeFilter] = useState('all');

  const loadEntries = async () => {
    setLoading(true);
    try {
      const response = await api.get('telegram/sent_messages');
      setEntries(response.data);
      setError(null);
    } catch (err) {
      console.error(err);
      setError('Не удалось загрузить историю сообщений');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadEntries();
  }, []);

  const filteredEntries = useMemo(() => {
    if (typeFilter === 'all') return entries;
    if (typeFilter === 'broadcast') return entries.filter((entry) => entry.broadcast);
    return entries.filter((entry) => !entry.broadcast);
  }, [entries, typeFilter]);

  const toggleExpanded = (id) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Удалить запись из истории?')) return;
    try {
      await api.delete(`telegram/sent_messages/${id}`);
      setEntries((prev) => prev.filter((entry) => entry.id !== id));
    } catch (err) {
      console.error(err);
      setError('Не удалось удалить запись');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-gray-800">
          <MessageCircle size={24} /> История сообщений
        </h1>
        <div className="flex items-center gap-2">
          <select
            className="rounded border border-gray-300 px-3 py-2 shadow-sm"
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
          >
            {typeFilters.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={loadEntries}
            className="btn flex items-center gap-2"
            disabled={loading}
          >
            <RefreshCcw size={16} className={loading ? 'animate-spin' : ''} />
            Обновить
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <AlertCircle size={18} /> {error}
        </div>
      )}

      <div className="grid gap-4">
        {filteredEntries.length === 0 && !loading && (
          <div className="rounded border border-dashed border-gray-300 bg-white p-6 text-center text-gray-500">
            Нет сообщений для отображения.
          </div>
        )}

        {filteredEntries.map((entry) => (
          <article key={entry.id} className="rounded border border-gray-200 bg-white p-4 shadow-sm">
            <header className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <Clock size={16} />
                  {new Date(entry.timestamp).toLocaleString()}
                </div>
                <p className="whitespace-pre-wrap text-gray-900">{entry.message}</p>
                <div className="flex flex-wrap items-center gap-2 text-sm text-gray-600">
                  <StatusBadge status={entry.status} />
                  {entry.requires_ack && (
                    <span className="rounded bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                      Требуется подтверждение
                    </span>
                  )}
                  {entry.user_id && !entry.broadcast && (
                    <span className="text-xs text-gray-500">ID получателя: {entry.user_id}</span>
                  )}
                </div>
              </div>
              <div className="flex flex-col items-end gap-2">
                <span className="text-xs uppercase tracking-wide text-gray-400">
                  {entry.broadcast ? 'Рассылка' : 'Персональное'}
                </span>
                <button
                  type="button"
                  onClick={() => handleDelete(entry.id)}
                  className="text-red-600 hover:text-red-700"
                  title="Удалить запись"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </header>

            {entry.photo_url && (
              <img
                src={entry.photo_url}
                alt="Прикреплённое изображение"
                className="mt-3 max-h-48 w-full rounded object-contain"
              />
            )}

            {entry.broadcast && (
              <div className="mt-4 space-y-2">
                <button
                  type="button"
                  onClick={() => toggleExpanded(entry.id)}
                  className="flex items-center gap-2 text-sm font-medium text-blue-600 hover:underline"
                >
                  <Users size={16} />
                  {expandedId === entry.id ? 'Скрыть получателей' : 'Показать получателей'}
                </button>
                {expandedId === entry.id && (
                  <div className="overflow-hidden rounded border">
                    <table className="min-w-full divide-y divide-gray-200 text-sm">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-3 py-2 text-left font-medium text-gray-600">Получатель</th>
                          <th className="px-3 py-2 text-left font-medium text-gray-600">Статус</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {(entry.recipients || []).map((recipient) => (
                          <tr key={`${recipient.user_id}-${recipient.status}`}>
                            <td className="px-3 py-2 text-gray-700">
                              {recipient.name || recipient.user_id || '—'}
                            </td>
                            <td className="px-3 py-2">
                              <StatusBadge status={recipient.status} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
