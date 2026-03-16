import { useEffect, useState } from 'react';
import { Bell, BellOff } from 'lucide-react';
import { useAuth } from '../../providers/AuthProvider.jsx';
import api from '../../api.js';
import { subscribePush, unsubscribePush, getPushState } from '../../utils/push.js';

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

  const [pushState, setPushState] = useState({ supported: false, subscribed: false });
  const [pushLoading, setPushLoading] = useState(false);
  const [pushError, setPushError] = useState('');

  useEffect(() => {
    if (!employeeId) return;
    setLoading(true);
    api
      .get(`/employees/${employeeId}`)
      .then((res) => setEmployee(res.data))
      .catch(() => setError('Не удалось загрузить профиль'))
      .finally(() => setLoading(false));

    getPushState(employeeId).then(setPushState);
  }, [employeeId]);

  const handlePushToggle = async () => {
    setPushLoading(true);
    setPushError('');
    try {
      if (pushState.subscribed) {
        await unsubscribePush(employeeId);
        setPushState((s) => ({ ...s, subscribed: false }));
      } else {
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
          setPushError('Разрешение на уведомления не выдано');
          return;
        }
        await subscribePush(employeeId);
        setPushState((s) => ({ ...s, subscribed: true }));
      }
    } catch (err) {
      setPushError(err.message || 'Ошибка при настройке уведомлений');
    } finally {
      setPushLoading(false);
    }
  };

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

          {pushState.supported && (
            <div className="emp-profile-section emp-profile-section--push">
              <div className="emp-profile-section__title">Уведомления</div>
              {pushState.denied ? (
                <p className="emp-page__empty" style={{ fontSize: '0.8rem', margin: 0 }}>
                  Уведомления заблокированы в настройках браузера
                </p>
              ) : (
                <div className="emp-push-row">
                  <div className="emp-push-row__info">
                    {pushState.subscribed ? (
                      <>
                        <Bell size={16} />
                        <span>Уведомления включены</span>
                      </>
                    ) : (
                      <>
                        <BellOff size={16} />
                        <span>Уведомления выключены</span>
                      </>
                    )}
                  </div>
                  <button
                    type="button"
                    className={`btn btn--sm ${pushState.subscribed ? 'btn--secondary' : 'btn--primary'}`}
                    onClick={handlePushToggle}
                    disabled={pushLoading}
                  >
                    {pushLoading
                      ? '…'
                      : pushState.subscribed
                      ? 'Выключить'
                      : 'Включить'}
                  </button>
                </div>
              )}
              {pushError && <p className="emp-page__error" style={{ marginTop: '0.4rem', fontSize: '0.8rem' }}>{pushError}</p>}
              {!pushState.subscribed && !pushState.denied && (
                <p style={{ fontSize: '0.75rem', color: 'var(--color-text-faint)', marginTop: '0.4rem' }}>
                  Получайте уведомления об изменении статуса заявок на аванс
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
