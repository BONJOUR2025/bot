import { useEffect, useState } from 'react';
import { Send } from 'lucide-react';
import { useAuth } from '../../providers/AuthProvider.jsx';
import api from '../../api.js';
import { useToast } from '../../providers/ToastProvider.jsx';

const STATUS_LABELS = {
  new: { label: 'Отправлено', cls: 'badge--warning' },
  read: { label: 'Прочитано', cls: 'badge--info' },
  replied: { label: 'Есть ответ', cls: 'badge--success' },
};

function fmtDateTime(value) {
  if (!value) return '';
  return new Date(value).toLocaleString('ru-RU');
}

export default function EmployeeFeedback() {
  const { user } = useAuth();
  const { toast } = useToast();
  const employeeId = user?.employee_id;

  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [employee, setEmployee] = useState(null);

  const loadMessages = () => {
    if (!employeeId) return;
    setLoading(true);
    api
      .get('/employee-messages/', { params: { employee_id: employeeId } })
      .then((res) => setMessages(res.data || []))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadMessages();
    if (employeeId) {
      api.get(`/employees/${employeeId}`).then((res) => setEmployee(res.data));
    }
  }, [employeeId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!employee || !text.trim()) return;
    setSending(true);
    try {
      await api.post('/employee-messages/', {
        employee_id: employeeId,
        name: employee.full_name || employee.name,
        message: text.trim(),
      });
      setText('');
      toast('Сообщение отправлено', 'success');
      loadMessages();
    } catch {
      toast('Не удалось отправить сообщение', 'error');
    } finally {
      setSending(false);
    }
  };

  if (!employeeId) {
    return (
      <div className="emp-page">
        <h2 className="emp-page__title">Связь с администратором</h2>
        <p className="emp-page__empty">Аккаунт не привязан к сотруднику. Обратитесь к администратору.</p>
      </div>
    );
  }

  return (
    <div className="emp-page">
      <h2 className="emp-page__title">Связь с администратором</h2>

      <div className="emp-form-card">
        <form onSubmit={handleSubmit}>
          <label className="form-field">
            <span>Сообщение</span>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Напишите вопрос или сообщение администратору"
              rows={3}
              required
            />
          </label>
          <div className="emp-form-card__actions">
            <button type="submit" className="btn btn--primary" disabled={sending || !text.trim()}>
              <Send size={16} />
              {sending ? 'Отправка…' : 'Отправить'}
            </button>
          </div>
        </form>
      </div>

      {loading && <p className="emp-page__loading">Загрузка…</p>}

      {!loading && messages.length === 0 && (
        <p className="emp-page__empty">Сообщений пока нет</p>
      )}

      {messages.length > 0 && (
        <div className="emp-list">
          {messages.map((m) => {
            const st = STATUS_LABELS[m.status] || { label: m.status, cls: '' };
            return (
              <div key={m.id} className="emp-payout-item">
                <div className="emp-payout-item__top">
                  <span className="emp-payout-item__amount">{fmtDateTime(m.created_at)}</span>
                  <span className={`badge ${st.cls}`}>{st.label}</span>
                </div>
                <div className="emp-payout-item__note">{m.message}</div>
                {m.reply && (
                  <div className="emp-payout-item__note" style={{ marginTop: '0.5rem', fontWeight: 500 }}>
                    Ответ: {m.reply}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
