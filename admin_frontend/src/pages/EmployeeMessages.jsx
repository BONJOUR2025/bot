import { useEffect, useState } from 'react';
import { MessageCircle, Send } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

const STATUS_LABELS = {
  new: { label: 'Новое', cls: 'bg-yellow-100 text-yellow-700' },
  read: { label: 'Прочитано', cls: 'bg-blue-100 text-blue-700' },
  replied: { label: 'Отвечено', cls: 'bg-green-100 text-green-700' },
};

function fmtDateTime(value) {
  if (!value) return '';
  return new Date(value).toLocaleString('ru-RU');
}

export default function EmployeeMessages() {
  const { toast } = useToast();
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [replyDrafts, setReplyDrafts] = useState({});

  async function load() {
    setLoading(true);
    try {
      const res = await api.get('employee-messages/');
      const list = [...res.data].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      setMessages(list);
    } catch (err) {
      console.error(err);
      toast('Ошибка загрузки сообщений', 'error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleReply(id) {
    const reply = (replyDrafts[id] || '').trim();
    if (!reply) return;
    try {
      await api.post(`employee-messages/${id}/reply`, { reply });
      setReplyDrafts((prev) => ({ ...prev, [id]: '' }));
      toast('Ответ отправлен', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка отправки ответа', 'error');
    }
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <h2 className="flex items-center gap-2 text-2xl font-semibold">
        <MessageCircle size={24} /> Сообщения от сотрудников
      </h2>

      {loading && <p className="text-[color:var(--color-text-muted)]">Загрузка…</p>}

      {!loading && messages.length === 0 && (
        <div className="rounded border border-dashed border-[color:var(--color-border)] bg-[color:var(--color-surface)] p-6 text-center text-[color:var(--color-text-muted)]">
          Сообщений нет
        </div>
      )}

      <div className="grid gap-4">
        {messages.map((m) => {
          const st = STATUS_LABELS[m.status] || { label: m.status, cls: 'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text)]' };
          return (
            <article key={m.id} className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-surface)] p-4 shadow-sm space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-[color:var(--color-text)]">{m.name}</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-[color:var(--color-text-faint)]">{fmtDateTime(m.created_at)}</span>
                  <span className={`rounded px-2 py-0.5 text-xs font-medium ${st.cls}`}>{st.label}</span>
                </div>
              </div>
              <p className="whitespace-pre-wrap text-[color:var(--color-text)]">{m.message}</p>
              {m.reply && (
                <div className="rounded bg-[color:var(--color-bg-subtle)] p-2 text-sm text-[color:var(--color-text)]">
                  <span className="font-medium">Ответ:</span> {m.reply}
                </div>
              )}
              {!m.reply && (
                <div className="flex gap-2">
                  <input
                    className="input flex-1"
                    placeholder="Ответить сотруднику…"
                    value={replyDrafts[m.id] || ''}
                    onChange={(e) => setReplyDrafts((prev) => ({ ...prev, [m.id]: e.target.value }))}
                  />
                  <button
                    type="button"
                    className="btn flex items-center gap-1"
                    onClick={() => handleReply(m.id)}
                    disabled={!(replyDrafts[m.id] || '').trim()}
                  >
                    <Send size={14} /> Отправить
                  </button>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
