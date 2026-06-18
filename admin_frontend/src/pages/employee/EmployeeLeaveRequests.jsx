import { useEffect, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { useAuth } from '../../providers/AuthProvider.jsx';
import api from '../../api.js';

const TYPES = ['Отгул', 'Отпуск без содержания', 'Больничный', 'Другое'];

const STATUS_LABELS = {
  'Ожидает': { label: 'Ожидает', cls: 'badge--warning' },
  'Одобрено': { label: 'Одобрено', cls: 'badge--success' },
  'Отклонено': { label: 'Отклонено', cls: 'badge--error' },
};

function fmtDate(value) {
  if (!value) return '';
  return new Date(value).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export default function EmployeeLeaveRequests() {
  const { user } = useAuth();
  const employeeId = user?.employee_id;

  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [employee, setEmployee] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  const [form, setForm] = useState({
    type: TYPES[0],
    start_date: '',
    end_date: '',
    comment: '',
  });

  const loadRequests = () => {
    if (!employeeId) return;
    setLoading(true);
    api
      .get('/leave-requests/', { params: { employee_id: employeeId } })
      .then((res) => setRequests(res.data || []))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadRequests();
    if (employeeId) {
      api.get(`/employees/${employeeId}`).then((res) => setEmployee(res.data));
    }
  }, [employeeId]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!employee) return;
    if (!form.start_date || !form.end_date) {
      setFormError('Укажите даты');
      return;
    }
    if (form.start_date > form.end_date) {
      setFormError('Дата начала не может быть позже даты окончания');
      return;
    }
    setSubmitting(true);
    setFormError('');
    try {
      await api.post('/leave-requests/', {
        employee_id: employeeId,
        name: employee.full_name || employee.name,
        type: form.type,
        start_date: form.start_date,
        end_date: form.end_date,
        comment: form.comment || '',
      });
      setShowForm(false);
      setForm({ type: TYPES[0], start_date: '', end_date: '', comment: '' });
      loadRequests();
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Ошибка при отправке заявки');
    } finally {
      setSubmitting(false);
    }
  };

  if (!employeeId) {
    return (
      <div className="emp-page">
        <h2 className="emp-page__title">Отгулы и отсутствие</h2>
        <p className="emp-page__empty">Аккаунт не привязан к сотруднику. Обратитесь к администратору.</p>
      </div>
    );
  }

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">Отгулы и отсутствие</h2>
        <button
          type="button"
          className="btn btn--primary btn--sm"
          onClick={() => setShowForm((v) => !v)}
        >
          <Plus size={16} />
          Подать заявку
        </button>
      </div>

      {showForm && (
        <div className="emp-form-card">
          <div className="emp-form-card__header">
            <span>Новая заявка</span>
            <button type="button" className="icon-button" onClick={() => setShowForm(false)}>
              <X size={16} />
            </button>
          </div>
          <form onSubmit={handleSubmit}>
            <div className="emp-form-row">
              <label className="form-field">
                <span>Тип</span>
                <select name="type" value={form.type} onChange={handleChange} className="emp-select">
                  {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              <label className="form-field">
                <span>Дата начала</span>
                <input type="date" name="start_date" value={form.start_date} onChange={handleChange} required />
              </label>
              <label className="form-field">
                <span>Дата окончания</span>
                <input type="date" name="end_date" value={form.end_date} onChange={handleChange} required />
              </label>
            </div>
            <label className="form-field">
              <span>Комментарий (необязательно)</span>
              <input
                name="comment"
                value={form.comment}
                onChange={handleChange}
                placeholder="Укажите причину или комментарий"
              />
            </label>
            {formError && <div className="form-error">{formError}</div>}
            <div className="emp-form-card__actions">
              <button type="submit" className="btn btn--primary" disabled={submitting}>
                {submitting ? 'Отправка…' : 'Отправить заявку'}
              </button>
            </div>
          </form>
        </div>
      )}

      {loading && <p className="emp-page__loading">Загрузка…</p>}

      {!loading && requests.length === 0 && (
        <p className="emp-page__empty">Нет заявок</p>
      )}

      {requests.length > 0 && (
        <div className="emp-list">
          {requests.map((r) => {
            const st = STATUS_LABELS[r.status] || { label: r.status, cls: '' };
            return (
              <div key={r.id} className="emp-payout-item">
                <div className="emp-payout-item__top">
                  <span className="emp-payout-item__amount">{r.type}</span>
                  <span className={`badge ${st.cls}`}>{st.label}</span>
                </div>
                <div className="emp-payout-item__details">
                  <span>{fmtDate(r.start_date)} — {fmtDate(r.end_date)}</span>
                </div>
                {r.comment && <div className="emp-payout-item__note">{r.comment}</div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
