import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import api from '../api.js';

const AuthContext = createContext({
  user: null,
  loading: true,
  login: async () => {},
  logout: () => {},
  refresh: async () => {},
});

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .get('auth/me')
      .then((res) => setUser(res.data))
      .catch(() => {
        localStorage.removeItem('auth_token');
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = async (loginName, password) => {
    const res = await api.post('auth/login', { login: loginName, password });
    localStorage.setItem('auth_token', res.data.token);
    setUser(res.data.user);
    return res.data.user;
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    setUser(null);
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
