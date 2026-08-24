import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowUpRight } from 'lucide-react';

import { useAuth } from '../providers/AuthProvider.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';

export function getHomeForUser(user) {
  if (!user) return '/login';
  // employee_id is only ever set on employee accounts (see access_control_service.py) —
  // check it before permissions, since an employee can also hold scoped admin
  // permissions (e.g. "payouts") without being an admin/owner.
  if (user.employee_id) return '/employee/salary';
  if (user.permissions?.length > 0) return '/admin';
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
    // Editorial Split: слева — крупная типографика и назначение системы,
    // справа — сама форма. На узком экране колонки складываются в одну,
    // текстовый блок остаётся сверху (см. .auth-split в globals.css).
    <div className="auth-split">
      <div className="auth-split__pitch">
        <span className="ui-eyebrow">BONJOUR · Центр управления</span>
        <h1 className="auth-split__title">
          Вход в
          <br />
          <b>систему</b>.
        </h1>
        <p className="auth-split__lead">
          Персонал, зарплата, продажи и индивидуальный пошив — в одной панели.
        </p>
      </div>

      <div className={`auth-card ${isMobile ? 'auth-card--mobile' : ''}`}>
        <div className="auth-card__logo">B</div>
        <div className="auth-card__header">
          <h2>Добро пожаловать</h2>
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
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
          <button type="submit" className="btn btn--primary ui-btn--nubbed" disabled={loading}>
            {loading ? 'Вход…' : 'Войти'}
            <span className="ui-nub">
              <ArrowUpRight size={14} strokeWidth={1.4} />
            </span>
          </button>
        </form>
      </div>
    </div>
  );
}
