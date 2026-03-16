import { useEffect, useState } from 'react';
import { useAuth } from '../../providers/AuthProvider.jsx';
import api from '../../api.js';

function Row({ label, value }) {
  if (!value) return null;
  return (
    <div className="emp-profile-row">
      <span className="emp-profile-row__label">{label}</span>
      <span className="emp-profile-row__value">{value}</span>
    </div>
  );
}

export default function EmployeeProfile() {
  const { user } = useAuth();
  const employeeId = user?.employee_id;

  const [employee, setEmployee] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!employeeId) return;
    setLoading(true);
    api
      .get(`/employees/${employeeId}`)
      .then((res) => setEmployee(res.data))
      .catch(() => setError('Не удалось загрузить профиль'))
      .finally(() => setLoading(false));
  }, [employeeId]);

  if (!employeeId) {
    return (
      <div className="emp-page">
        <h2 className="emp-page__title">Профиль</h2>
        <p className="emp-page__empty">Аккаунт не привязан к сотруднику. Обратитесь к администратору.</p>
      </div>
    );
  }

  return (
    <div className="emp-page">
      <h2 className="emp-page__title">Профиль</h2>

      {loading && <p className="emp-page__loading">Загрузка…</p>}
      {error && <p className="emp-page__error">{error}</p>}

      {employee && (
        <div className="emp-profile-card">
          {employee.photo_url && (
            <div className="emp-profile-card__photo">
              <img src={employee.photo_url} alt={employee.name} />
            </div>
          )}

          <div className="emp-profile-card__name">
            {employee.full_name || employee.name}
          </div>
          {employee.position && (
            <div className="emp-profile-card__position">{employee.position}</div>
          )}

          <div className="emp-profile-section">
            <div className="emp-profile-section__title">Контакты</div>
            <Row label="Телефон" value={employee.phone} />
          </div>

          <div className="emp-profile-section">
            <div className="emp-profile-section__title">Реквизиты</div>
            <Row label="Карта" value={employee.card_number} />
            <Row label="Банк" value={employee.bank} />
          </div>

          <div className="emp-profile-section">
            <div className="emp-profile-section__title">О сотруднике</div>
            <Row label="Подразделение" value={employee.work_place} />
            <Row label="Размер одежды" value={employee.clothing_size} />
            <Row
              label="Дата рождения"
              value={
                employee.birthdate
                  ? new Date(employee.birthdate).toLocaleDateString('ru-RU', {
                      day: '2-digit',
                      month: '2-digit',
                      year: 'numeric',
                    })
                  : null
              }
            />
            {employee.note && <Row label="Заметка" value={employee.note} />}
          </div>
        </div>
      )}
    </div>
  );
}
