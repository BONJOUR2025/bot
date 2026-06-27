import { useEffect, useState } from 'react';
import { Check, X } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';

const STATUS_LABELS = {
  'Ожидает': 'bg-yellow-100 text-yellow-700',
  'Одобрено': 'bg-green-100 text-green-700',
  'Отклонено': 'bg-red-100 text-red-700',
};

function fmtDate(value) {
  if (!value) return '';
  return new Date(value).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export default function LeaveRequests() {
  const { toast } = useToast();
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get('leave-requests/');
      const list = [...res.data].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      setRequests(list);
    } catch (err) {
      console.error(err);
      toast('Ошибка загрузки заявок', 'error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function setStatus(id, action) {
    try {
      await api.post(`leave-requests/${id}/${action}`);
      toast('Статус обновлён', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка обновления статуса', 'error');
    }
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <h2 className="text-2xl font-semibold">Заявки на отгул/отсутствие</h2>

      {loading ? (
        <div className="border rounded shadow bg-[color:var(--color-surface)] p-4">
          <SkeletonTable rows={6} cols={5} />
        </div>
      ) : (
        <ResponsiveTable
          data={requests}
          keyFn={(r) => r.id}
          emptyText="Нет заявок"
          columns={[
            { label: 'Сотрудник', key: 'name', primary: true },
            { label: 'Тип', key: 'type' },
            { label: 'Даты', render: (r) => `${fmtDate(r.start_date)} – ${fmtDate(r.end_date)}` },
            { label: 'Комментарий', key: 'comment' },
            {
              label: 'Статус',
              render: (r) => (
                <span className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${STATUS_LABELS[r.status] || 'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text)]'}`}>
                  {r.status}
                </span>
              ),
            },
            {
              label: '',
              isAction: true,
              cellClass: 'text-right',
              render: (r) =>
                r.status === 'Ожидает' ? (
                  <>
                    <button className="text-green-600 hover:text-green-800" onClick={() => setStatus(r.id, 'approve')} title="Одобрить">
                      <Check size={16} />
                    </button>
                    <button className="text-red-600 hover:text-red-800 ml-2" onClick={() => setStatus(r.id, 'reject')} title="Отклонить">
                      <X size={16} />
                    </button>
                  </>
                ) : null,
            },
          ]}
        />
      )}
    </div>
  );
}
