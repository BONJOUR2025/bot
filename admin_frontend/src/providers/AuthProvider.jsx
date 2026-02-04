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

    const loadProfile = async () => {
      try {
        const res = await api.get('auth/me');
        if (active) {
          setUser(res.data);
        }
      } catch (err) {
        if (localStorage.getItem('auth_token')) {
          localStorage.removeItem('auth_token');
        }
        if (active) {
          setUser(null);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
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
