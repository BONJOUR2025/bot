import { useEffect, useState, useRef } from 'react';
import { Bell, BellOff, Pencil, Check, X, Camera } from 'lucide-react';
import { useAuth } from '../../providers/AuthProvider.jsx';
import api from '../../api.js';
import { useToast } from '../../providers/ToastProvider.jsx';
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

function EditableRow({ label, value, onSave }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || '');
  const [saving, setSaving] = useState(false);

  if (!editing) {
    return (
      <div className="emp-profile-row">
        <span className="emp-profile-row__label">{label}</span>
        <span className="emp-profile-row__value" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          {value || '—'}
          <button type="button" className="icon-button" style={{ padding: '0.15rem' }}
            onClick={() => { setDraft(value || ''); setEditing(true); }} aria-label={`Изменить ${label}`}>
            <Pencil size={13} />
          </button>
        </span>
      </div>
    );
  }

  return (
    <div className="emp-profile-row">
      <span className="emp-profile-row__label">{label}</span>
      <span className="emp-profile-row__value" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
        <input
          className="input"
          style={{ minWidth: 0 }}
          value={draft}
          autoFocus
          disabled={saving}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Escape') setEditing(false); }}
        />
        <button type="button" className="icon-button" disabled={saving}
          onClick={async () => { setSaving(true); await onSave(draft); setSaving(false); setEditing(false); }} aria-label="Сохранить">
          <Check size={14} />
        </button>
        <button type="button" className="icon-button" disabled={saving} onClick={() => setEditing(false)} aria-label="Отмена">
          <X size={14} />
        </button>
      </span>
    </div>
  );
}

export default function EmployeeProfile() {
  const { user } = useAuth();
  const { toast } = useToast();
  const employeeId = user?.employee_id;
  const fileInputRef = useRef(null);

  const [employee, setEmployee] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [uploadingPhoto, setUploadingPhoto] = useState(false);

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

  const saveField = async (field, value) => {
    try {
      const res = await api.patch(`/employees/${employeeId}/self`, { [field]: value });
      setEmployee(res.data);
      toast('Сохранено', 'success');
    } catch {
      toast('Не удалось сохранить', 'error');
    }
  };

  const handlePhotoChange = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setUploadingPhoto(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await api.post(`/employees/${employeeId}/photo`, fd);
      setEmployee((emp) => ({ ...emp, photo_url: res.data.url }));
      toast('Фото обновлено', 'success');
    } catch {
      toast('Не удалось загрузить фото', 'error');
    } finally {
      setUploadingPhoto(false);
    }
  };

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
          <div className="emp-profile-card__photo" style={{ position: 'relative', display: 'inline-block' }}>
            {employee.photo_url ? (
              <img src={employee.photo_url} alt={employee.name} />
            ) : (
              <div style={{ width: 80, height: 80, borderRadius: '50%', background: 'var(--color-bg-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Camera size={24} style={{ color: 'var(--color-text-faint)' }} />
              </div>
            )}
            <button
              type="button"
              className="icon-button"
              style={{ position: 'absolute', bottom: -4, right: -4, background: 'var(--color-bg)', borderRadius: '50%' }}
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadingPhoto}
              aria-label="Изменить фото"
            >
              <Pencil size={13} />
            </button>
            <input ref={fileInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handlePhotoChange} />
          </div>

          <div className="emp-profile-card__name">
            {employee.full_name || employee.name}
          </div>
          {employee.position && (
            <div className="emp-profile-card__position">{employee.position}</div>
          )}

          <div className="emp-profile-section">
            <div className="emp-profile-section__title">Контакты</div>
            <EditableRow label="Телефон" value={employee.phone} onSave={(v) => saveField('phone', v)} />
          </div>

          <div className="emp-profile-section">
            <div className="emp-profile-section__title">Реквизиты</div>
            <EditableRow label="Карта" value={employee.card_number} onSave={(v) => saveField('card_number', v)} />
            <EditableRow label="Банк" value={employee.bank} onSave={(v) => saveField('bank', v)} />
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

          <div className="emp-profile-section emp-profile-section--push">
            <div className="emp-profile-section__title">Уведомления</div>
            {pushState.iosNonStandalone && (
              <p style={{ fontSize: '0.8rem', color: 'var(--color-text-faint)', marginBottom: '0.5rem' }}>
                На iPhone уведомления сохраняются только если сайт добавлен на главный экран:
                нажмите «Поделиться» → «На экран «Домой»», затем откройте приложение оттуда и включите уведомления.
              </p>
            )}
            {!pushState.supported ? (
              <p style={{ fontSize: '0.8rem', color: 'var(--color-text-faint)', margin: 0 }}>
                {pushState.notSecure
                  ? 'Уведомления доступны только при подключении по HTTPS'
                  : 'Ваш браузер не поддерживает push-уведомления'}
              </p>
            ) : pushState.denied ? (
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
                  {pushLoading ? '…' : pushState.subscribed ? 'Выключить' : 'Включить'}
                </button>
              </div>
            )}
            {pushError && (
              <p className="emp-page__error" style={{ marginTop: '0.4rem', fontSize: '0.8rem' }}>
                {pushError}
              </p>
            )}
            {pushState.supported && !pushState.subscribed && !pushState.denied && (
              <p style={{ fontSize: '0.75rem', color: 'var(--color-text-faint)', marginTop: '0.4rem' }}>
                Получайте уведомления об изменении статуса заявок на аванс
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
