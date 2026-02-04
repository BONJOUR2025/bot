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
  (response) => {
    console.log('API', response.config?.url, response.data);
    return response;
  },
  (error) => {
    console.error('API', error.config?.url, error.message);
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      const loginPath = '/admin/login';
      if (!window.location.pathname.startsWith(loginPath)) {
        window.location.href = loginPath;
      }
    }
    return Promise.reject(error);
  }
);

export default api;



