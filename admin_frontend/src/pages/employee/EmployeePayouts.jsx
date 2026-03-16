import { useEffect, useState } from 'react';
import { Plus, X } from 'lucide-react';
import { useAuth } from '../../providers/AuthProvider.jsx';
import api from '../../api.js';

const METHODS = ['💳 На карту', '🏦 Из кассы'];
const PAYOUT_TYPES = ['Аванс', 'Зарплата'];

const STATUS_LABELS = {
  'Ожидает': { label: 'Ожидает', cls: 'badge--warning' },
  'Одобрено': { label: 'Одобрено', cls: 'badge--info' },
  'Отклонено': { label: 'Отклонено', cls: 'badge--error' },
  'Выплачено': { label: 'Выплачено', cls: 'badge--success' },
};

function fmt(n) {
  return Number(n).toLocaleString('ru-RU') + ' ₽';
}

function fmtDate(ts) {
  if (!ts) return '';
  return new Date(ts).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export default function EmployeePayouts() {
  const { user } = useAuth();
  const employeeId = user?.employee_id;

  const [payouts, setPayouts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [employee, setEmployee] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  const [form, setForm] = useState({
    amount: '',
    method: METHODS[0],
    payout_type: PAYOUT_TYPES[0],
    note: '',
  });

  const loadPayouts = () => {
    if (!employeeId) return;
    setLoading(true);
    api
      .get('/payouts/', { params: { employee_id: employeeId } })
      .then((res) => setPayouts(res.data || []))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadPayouts();
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
    const amount = parseFloat(form.amount);
    if (!amount || amount <= 0) {
      setFormError('Укажите сумму');
      return;
    }
    setSubmitting(true);
    setFormError('');
    try {
      await api.post('/payouts/', {
        user_id: employeeId,
        name: employee.full_name || employee.name,
        phone: employee.phone || '',
        card_number: employee.card_number || '',
        bank: employee.bank || '',
        amount,
        method: form.method,
        payout_type: form.payout_type,
        note: form.note || null,
      });
      setShowForm(false);
      setForm({ amount: '', method: METHODS[0], payout_type: PAYOUT_TYPES[0], note: '' });
      loadPayouts();
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Ошибка при отправке запроса');
    } finally {
      setSubmitting(false);
    }
  };

  if (!employeeId) {
    return (
      <div className="emp-page">
        <h2 className="emp-page__title">Авансы</h2>
        <p className="emp-page__empty">Аккаунт не привязан к сотруднику. Обратитесь к администратору.</p>
      </div>
    );
  }

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">Авансы</h2>
        <button
          type="button"
          className="btn btn--primary btn--sm"
          onClick={() => setShowForm((v) => !v)}
        >
          <Plus size={16} />
          Запросить
        </button>
      </div>

      {showForm && (
        <div className="emp-form-card">
          <div className="emp-form-card__header">
            <span>Новый запрос</span>
            <button type="button" className="icon-button" onClick={() => setShowForm(false)}>
              <X size={16} />
            </button>
          </div>
          <form onSubmit={handleSubmit}>
            <div className="emp-form-row">
              <label className="form-field">
                <span>Сумма</span>
                <input
                  type="number"
                  name="amount"
                  value={form.amount}
                  onChange={handleChange}
                  min="1"
                  placeholder="0"
                  required
                />
              </label>
              <label className="form-field">
                <span>Способ получения</span>
                <select name="method" value={form.method} onChange={handleChange} className="emp-select">
                  {METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </label>
              <label className="form-field">
                <span>Тип</span>
                <select name="payout_type" value={form.payout_type} onChange={handleChange} className="emp-select">
                  {PAYOUT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
            </div>
            <label className="form-field">
              <span>Комментарий (необязательно)</span>
              <input
                name="note"
                value={form.note}
                onChange={handleChange}
                placeholder="Укажите причину или комментарий"
              />
            </label>
            {formError && <div className="form-error">{formError}</div>}
            <div className="emp-form-card__actions">
              <button type="submit" className="btn btn--primary" disabled={submitting}>
                {submitting ? 'Отправка…' : 'Отправить запрос'}
              </button>
            </div>
          </form>
        </div>
      )}

      {loading && <p className="emp-page__loading">Загрузка…</p>}

      {!loading && payouts.filter(p => p.payout_type === 'Аванс').length === 0 && (
        <p className="emp-page__empty">Нет запросов на выплату</p>
      )}

      {payouts.length > 0 && (() => {
        // Sort newest first
        const sorted = [...payouts].sort((a, b) => {
          const ta = a.timestamp ? new Date(a.timestamp).getTime() : 0;
          const tb = b.timestamp ? new Date(b.timestamp).getTime() : 0;
          return tb - ta;
        });

        // Find last paid salary to filter advances since then
        const lastSalary = sorted.find(
          (p) => p.payout_type === 'Зарплата' && p.status === 'Выплачено'
        );
        const cutoff = lastSalary?.timestamp ? new Date(lastSalary.timestamp).getTime() : null;

        const visible = sorted.filter((p) => {
          if (p.payout_type !== 'Аванс') return false;
          if (cutoff == null) return true;
          return new Date(p.timestamp || 0).getTime() >= cutoff;
        });

        if (visible.length === 0) {
          return <p className="emp-page__empty">Авансов с последней зарплаты нет</p>;
        }

        return (
          <div className="emp-list">
            {visible.map((p) => {
              const st = STATUS_LABELS[p.status] || { label: p.status, cls: '' };
              return (
                <div key={p.id} className="emp-payout-item">
                  <div className="emp-payout-item__top">
                    <span className="emp-payout-item__amount">{fmt(p.amount)}</span>
                    <span className={`badge ${st.cls}`}>{st.label}</span>
                  </div>
                  <div className="emp-payout-item__details">
                    <span>{p.payout_type} · {p.method}</span>
                    {p.timestamp && <span>{fmtDate(p.timestamp)}</span>}
                  </div>
                  {p.note && <div className="emp-payout-item__note">{p.note}</div>}
                </div>
              );
            })}
          </div>
        );
      })()}
    </div>
  );
}
