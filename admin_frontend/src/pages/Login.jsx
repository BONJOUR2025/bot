import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../providers/AuthProvider.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || '/';

  const [form, setForm] = useState({ login: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { isMobile } = useViewport();

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(form.login, form.password);
      navigate(from, { replace: true });
    } catch (err) {
      console.error(err);
      setError('Неверный логин или пароль');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`auth-card ${isMobile ? 'auth-card--mobile' : ''}`}>
      <div className="auth-card__aura" aria-hidden />
      <div className="auth-card__grid">
        <div className="auth-card__meta">
          <div className="pill pill--accent">Новый десктоп</div>
          <h1>Быстрый доступ к панели HR</h1>
          <p>
            Модернизированный интерфейс с pywebview открывает админку как родное окно —
            с плавными тенями, обтекаемыми карточками и акцентными градиентами.
          </p>
          <div className="auth-card__stats">
            <div className="stat-card">
              <span className="stat-card__label">pywebview</span>
              <strong>Нативное окно</strong>
              <small>SPA работает локально без браузера</small>
            </div>
            <div className="stat-card stat-card--glass">
              <span className="stat-card__label">UI</span>
              <strong>Градиенты и неон</strong>
              <small>Современная анимация и типографика</small>
            </div>
          </div>
        </div>

        <div className="auth-card__panel">
          <div className="auth-card__logo">HR</div>
          <div className="auth-card__header">
            <h2>Вход в панель</h2>
            <p>Авторизуйтесь, чтобы управлять сотрудниками и выплатами</p>
          </div>
          <form className="auth-card__form" onSubmit={handleSubmit}>
            <label className="form-field">
              <span>Логин</span>
              <input
                id="login"
                name="login"
                value={form.login}
                onChange={handleChange}
                autoComplete="username"
                required
              />
            </label>
            <label className="form-field">
              <span>Пароль</span>
              <input
                id="password"
                type="password"
                name="password"
                value={form.password}
                onChange={handleChange}
                autoComplete="current-password"
                required
              />
            </label>
            {error && <div className="form-error">{error}</div>}
            <button type="submit" className="btn btn--primary" disabled={loading}>
              {loading ? 'Вход…' : 'Войти'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
