import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import api from '../api.js';

const AuthContext = createContext({
  user: null,
  loading: true,
  login: async () => {},
  logout: async () => {},
  refresh: async () => {},
});

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    // Вход стираем, только когда сервер прямо ответил 401 — токен
    // недействителен. Раньше его стирала любая ошибка при запуске: телефон
    // только проснулся и сети ещё нет, моргнул туннель, сервер
    // перезапускается после деплоя — и мастер с действующим 30-дневным
    // входом снова видел экран пароля. При сетевой ошибке или 5xx
    // повторяем, пока связь не появится.
    const RETRY_DELAYS_MS = [1500, 3000, 5000, 8000, 12000];

    const loadProfile = async (attempt = 0) => {
      try {
        const res = await api.get('auth/me');
        if (active) {
          setUser(res.data);
          setLoading(false);
        }
      } catch (err) {
        const status = err?.response?.status;
        const hasToken = !!localStorage.getItem('auth_token');
        if (status === 401 || !hasToken || attempt >= RETRY_DELAYS_MS.length) {
          if (status === 401 && hasToken) localStorage.removeItem('auth_token');
          if (active) {
            setUser(null);
            setLoading(false);
          }
          return;
        }
        setTimeout(() => { if (active) loadProfile(attempt + 1); }, RETRY_DELAYS_MS[attempt]);
      }
    };

    loadProfile();

    return () => {
      active = false;
    };
  }, []);

  const login = async (loginName, password) => {
    const res = await api.post('auth/login', { login: loginName, password });
    localStorage.setItem('auth_token', res.data.token);
    setUser(res.data.user);
    try {
      await fetch('/session/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ login: loginName, password }),
        credentials: 'include',
      });
    } catch (err) {
      /* ignore */
    }
    return res.data.user;
  };

  const logout = async () => {
    localStorage.removeItem('auth_token');
    setUser(null);
    try {
      await fetch('/session/logout', {
        method: 'POST',
        credentials: 'include',
      });
    } catch (err) {
      /* ignore */
    }
  };

  const refresh = async () => {
    const res = await api.get('auth/me');
    setUser(res.data);
    return res.data;
  };

  const value = useMemo(
    () => ({ user, loading, login, logout, refresh, setUser }),
    [user, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
