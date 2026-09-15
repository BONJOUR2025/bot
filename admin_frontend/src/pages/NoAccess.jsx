import { Navigate, useNavigate } from 'react-router-dom';
import { LogOut } from 'lucide-react';

import { useAuth } from '../providers/AuthProvider.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';
import { getHomeForUser } from './Login.jsx';

/** Аккаунт, которому некуда идти: не привязан к сотруднику и без прав в панели.
 *
 *  Раньше такой пользователь попадал в петлю редиректов: кабинет сотрудника
 *  отправлял его в /admin, а /admin — на «домашнюю страницу», которая для
 *  него снова /admin. Страница перенаправляла сама на себя и не рисовала
 *  ничего — пустой экран без единого запроса данных. Так вышло с логином
 *  мастера, заведённым в «Доступах» с ролью «Мастер», но без поля
 *  «Сотрудник»: кабинет узнаёт мастера по привязанной карточке, а не по роли.
 */
export default function NoAccess() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  const { isMobile } = useViewport();

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-sm text-[color:var(--muted-foreground)]">
        Загрузка…
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  // Аккаунт уже поправили в панели — отправляем туда, где его ждут.
  const home = getHomeForUser(user);
  if (home !== '/no-access') {
    return <Navigate to={home} replace />;
  }

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="auth-split">
      <div className="auth-split__pitch">
        <span className="ui-eyebrow">BONJOUR · Личный кабинет</span>
        <h1 className="auth-split__title">
          Вход
          <br />
          <b>не настроен</b>.
        </h1>
        <p className="auth-split__lead">
          Логин и пароль верные, но к логину не привязан сотрудник — поэтому кабинету нечего показать.
        </p>
      </div>

      <div className={`auth-card ${isMobile ? 'auth-card--mobile' : ''}`}>
        <div className="auth-card__logo">B</div>
        <div className="auth-card__header">
          <h2>Аккаунт не привязан к сотруднику</h2>
          <p>
            Попросите руководителя открыть «Настройки → Доступы», выбрать логин
            {user.login ? ` «${user.login}»` : ''} и указать в поле «Сотрудник» вашу карточку.
            После этого войдите заново.
          </p>
        </div>
        <button type="button" className="btn btn--primary" onClick={handleLogout}>
          <LogOut size={16} />
          Выйти
        </button>
      </div>
    </div>
  );
}
