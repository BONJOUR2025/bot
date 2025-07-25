import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
});

api.interceptors.response.use(
  (response) => {
    if (import.meta.env.DEV) {
      console.log('API', response.config?.url, response.data);
    }
    return response;
  },
  (error) => {
    if (import.meta.env.DEV) {
      console.error('API', error.config?.url, error.message);
    }
    return Promise.reject(error);
  }
);

export default api;

export async function getEmployees() {
  const res = await api.get('/employees/');
  return res.data;
}

export async function getActivePayouts() {
  const res = await api.get('/payouts/active');
  return res.data;
}

export async function getActiveVacations() {
  const res = await api.get('/vacations/active');
  return res.data;
}

export async function getBirthdays(days = 7) {
  const res = await api.get(`/birthdays/?days=${days}`);
  return res.data;
}

export async function getSales() {
  const res = await api.get('/analytics/sales');
  return res.data;
}
