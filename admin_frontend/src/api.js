import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      const path = window.location.pathname;
      if (path.startsWith('/employee')) {
        if (path !== '/employee/login') window.location.href = '/employee/login';
      } else {
        if (path !== '/admin/login') window.location.href = '/admin/login';
      }
    }
    return Promise.reject(error);
  }
);

export default api;



