import axios from 'axios';

export const POINT_TOKEN_KEY = 'point_token';
const isPointRequest = (url) => /^\/?point\//.test(String(url || ''));

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
  // Какую страницу человек сейчас смотрит — для журнала активности
  // (app/utils/activity.py): по адресам API это не понять, страницы попутно
  // дёргают чужие справочники.
  config.headers = config.headers || {};
  config.headers['X-Page'] = window.location.pathname;
  // Кабинет точки на ПК салона входит не по логину, а по ключу компьютера.
  if (isPointRequest(config.url)) {
    let pointToken = null;
    try { pointToken = localStorage.getItem(POINT_TOKEN_KEY); } catch { /* нет доступа — войти не выйдет */ }
    if (pointToken) {
      config.headers = config.headers || {};
      config.headers['X-Point-Token'] = pointToken;
    }
  }
  return config;
});

/** Приводит `detail` от FastAPI к строке.
 *
 * У 422 (ошибка валидации тела запроса) detail — это МАССИВ объектов
 * `{loc, msg, type}`, а не строка. По коду в 74 местах написано
 * `toast(e.response?.data?.detail || e.message)` — и такой массив уходит
 * прямо в JSX. React не умеет рисовать объект, падает всё дерево, и вместо
 * сообщения об ошибке пользователь получает белый экран: непонятно даже,
 * что запрос вообще не прошёл.
 *
 * Чиним здесь, а не в 74 местах: так белый экран не вернётся и в тех
 * вызовах, которые напишут завтра.
 */
function detailToText(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => {
      if (typeof d === 'string') return d;
      // loc = ["body", "send_message"] — первый элемент служебный.
      const where = Array.isArray(d?.loc) ? d.loc.slice(1).join('.') : '';
      const msg = d?.msg || d?.type || JSON.stringify(d);
      return where ? `${where}: ${msg}` : msg;
    });
    return parts.join('; ');
  }
  if (detail && typeof detail === 'object') {
    return detail.msg || detail.message || JSON.stringify(detail);
  }
  return String(detail);
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail;
    if (detail != null && typeof detail !== 'string') {
      try {
        error.response.data.detail = detailToText(detail);
      } catch {
        error.response.data.detail = 'Некорректные данные запроса';
      }
    }
    if (error.response?.status === 401 && isPointRequest(error.config?.url)) {
      // Ключ ПК отозван или неверный — кабинет точки сам покажет ввод кода,
      // на страницу входа сотрудника отсюда уводить нельзя.
      window.dispatchEvent(new CustomEvent('point-unauthorized'));
      return Promise.reject(error);
    }
    // Кабинет точки живёт без входа сотрудника: 401 на проверке профиля
    // (auth/me при загрузке приложения) не должен уводить его на страницу входа.
    if (error.response?.status === 401 && window.location.pathname.startsWith('/admin/point')) {
      return Promise.reject(error);
    }
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      const path = window.location.pathname;
      const onLoginPage = path === '/login' || path === '/admin/login' || path === '/employee/login';
      if (!onLoginPage) {
        if (path.startsWith('/employee')) {
          window.location.href = '/employee/login';
        } else {
          window.location.href = '/admin/login';
        }
      }
    }
    return Promise.reject(error);
  }
);

export default api;



