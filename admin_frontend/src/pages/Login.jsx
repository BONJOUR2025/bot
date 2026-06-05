import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../providers/AuthProvider.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';

export function getHomeForUser(user) {
  if (!user) return '/login';
  if (user.permissions?.length > 0) return '/admin';
  if (user.employee_id) return '/employee/salary';
  return '/admin';
}

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { isMobile } = useViewport();

  const [form, setForm] = useState({ login: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const user = await login(form.login, form.password);
      const home = getHomeForUser(user);
      const from = location.state?.from?.pathname;
      const isAdmin = home.startsWith('/admin');
      // Only restore saved path if it belongs to the same zone
      const dest =
        from &&
        ((isAdmin && from.startsWith('/admin')) || (!isAdmin && from.startsWith('/employee')))
          ? from
          : home;
      navigate(dest, { replace: true });
    } catch {
      setError('Неверный логин или пароль');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`auth-card ${isMobile ? 'auth-card--mobile' : ''}`}>
      <div className="auth-card__logo">ЦУ</div>
      <div className="auth-card__header">
        <h1>Добро пожаловать</h1>
        <p>Введите логин и пароль для входа</p>
      </div>
      <form className="auth-card__form" onSubmit={handleSubmit}>
        <label className="form-field">
          <span>Логин</span>
          <input
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
  );
}
