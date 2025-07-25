import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
});

api.interceptors.response.use(
  (response) => {
    console.log('API', response.config?.url, response.data);
    return response;
  },
  (error) => {
    console.error('API', error.config?.url, error.message);
    return Promise.reject(error);
  }
);

export default api;
