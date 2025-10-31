import { useEffect, useMemo, useState } from 'react';
import {
  MessageCircle,
  Users,
  AlertCircle,
  Clock,
  RefreshCcw,
  Trash2,
  CheckCircle2,
  Hourglass,
} from 'lucide-react';
import api from '../api';

const typeFilters = [
  { value: 'all', label: 'Все сообщения' },
  { value: 'direct', label: 'Персональные' },
  { value: 'broadcast', label: 'Рассылки' },
];

const STATUS_MAP = {
  success: {
    match: (value) => /принят|успех|отправ|delivered|success/i.test(value),
    className: 'bg-green-100 text-green-700',
    label: 'Успешно',
  },
  warning: {
    match: (value) => /ожид|pending|wait|жд|не достав/i.test(value),
    className: 'bg-yellow-100 text-yellow-700',
    label: 'Ожидает',
  },
  error: {
    match: (value) => /ошиб|fail|невалид|откл|error/i.test(value),
    className: 'bg-red-100 text-red-700',
    label: 'Ошибка',
  },
};

function getStatusVariant(status) {
  const normalized = (status || '').trim();
  if (!normalized) {
    return { className: 'bg-gray-200 text-gray-700', label: 'Неизвестно' };
  }
  const entry = Object.values(STATUS_MAP).find((item) => item.match(normalized));
  if (entry) {
    return entry;
  }
  return { className: 'bg-gray-200 text-gray-700', label: normalized };
}

function StatusBadge({ status }) {
  const variant = getStatusVariant(status);
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${variant.className}`}>
      {status || variant.label}
    </span>
  );
}

function StatusSummary({ recipients }) {
  const summary = useMemo(() => {
    const result = {
      success: 0,
      warning: 0,
      error: 0,
    };
    (recipients || []).forEach((recipient) => {
      const status = (recipient.status || '').trim();
      if (!status) {
        return;
      }
      if (STATUS_MAP.success.match(status)) {
        result.success += 1;
      } else if (STATUS_MAP.error.match(status)) {
        result.error += 1;
      } else if (STATUS_MAP.warning.match(status)) {
        result.warning += 1;
      }
    });
    return result;
  }, [recipients]);

  const total = (recipients || []).length;
  if (!total) {
    return null;
  }

  const items = [
    { key: 'success', label: 'Успех', className: 'bg-green-100 text-green-700' },
    { key: 'warning', label: 'Ожидает', className: 'bg-yellow-100 text-yellow-700' },
    { key: 'error', label: 'Ошибки', className: 'bg-red-100 text-red-700' },
  ];

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="rounded bg-gray-100 px-2 py-0.5 text-gray-600">
        Всего получателей: {total}
      </span>
      {items
        .filter((item) => summary[item.key] > 0)
        .map((item) => (
          <span key={item.key} className={`rounded px-2 py-0.5 font-medium ${item.className}`}>
            {item.label}: {summary[item.key]}
          </span>
        ))}
      {summary.success + summary.warning + summary.error < total && (
        <span className="rounded bg-gray-100 px-2 py-0.5 text-gray-600">
          Без статуса: {total - (summary.success + summary.warning + summary.error)}
        </span>
      )}
    </div>
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
                  {entry.accepted && (
                    <span className="flex items-center gap-1 rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                      <CheckCircle2 size={14} />
                      Принято
                    </span>
                  )}
                  {entry.requires_ack && !entry.accepted && (
                    <span className="flex items-center gap-1 rounded bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-700">
                      <Hourglass size={14} />
                      Ожидает подтверждения
                    </span>
                  )}
                  {entry.user_id && !entry.broadcast && (
                    <span className="text-xs text-gray-500">ID получателя: {entry.user_id}</span>
                  )}
                </div>
                {entry.accepted && entry.timestamp_accept && (
                  <div className="flex items-center gap-2 text-xs text-green-600">
                    <Clock size={14} />
                    Подтверждено: {new Date(entry.timestamp_accept).toLocaleString()}
                  </div>
                )}
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
              <div className="mt-4 space-y-3">
                <StatusSummary recipients={entry.recipients} />
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
