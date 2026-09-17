/** Кабинет открыт внутри нашего Android-приложения (WebView).
 *
 *  Приложений два — «BONJOUR Мастер» (мастера цеха) и «BONJOUR Салон»
 *  (администраторы точек). Каждое ставит свою метку в User-Agent
 *  (device/master_app, device/salon_app → MainActivity). Во WebView не работают
 *  push-уведомления браузера и скачивание файлов, поэтому такие элементы
 *  прячем — кнопка, которая молча ничего не делает, хуже её отсутствия. */

const APPS = [
  { key: 'master', mark: 'BonjourMasterApp', prefix: '/api/master-app', logins: '/master-app/logins' },
  { key: 'salon', mark: 'BonjourSalonApp', prefix: '/api/salon-app', logins: '/salon-app/logins' },
];

function detect() {
  if (typeof navigator === 'undefined') return null;
  const ua = navigator.userAgent || '';
  for (const app of APPS) {
    const match = new RegExp(`${app.mark}/([\\d.]+)`).exec(ua);
    if (match) return { ...app, version: match[1] };
  }
  return null;
}

const CURRENT = detect();

/** Кабинет открыт в приложении (любом из наших). */
export const IN_APP = CURRENT !== null;

/** Оставлено прежним именем: на него ссылаются экраны мастера. */
export const IN_MASTER_APP = IN_APP;

/** Какое именно приложение: 'master' | 'salon' | null. */
export const APP_KIND = CURRENT?.key ?? null;

/** Адрес списка логинов для входа: у мастеров и администраторов он разный. */
export const APP_LOGINS_URL = CURRENT?.logins ?? null;

/** Страница установки по http. Приложение (с первой версии) выпускает во внешний
 *  браузер всё, что не https://app.bonjour.pw, а сервер отвечает на http
 *  переадресацией на https — так человек попадает в Chrome, где скачивание APK
 *  работает, даже в версии без собственного загрузчика. */
export const MASTER_APP_UPDATE_URL = CURRENT
  ? `http://app.bonjour.pw${CURRENT.prefix}/`
  : 'http://app.bonjour.pw/api/master-app/';

/** Адрес сведений о свежей версии — для плашки обновления. */
export const APP_INFO_URL = CURRENT ? `${CURRENT.prefix.replace('/api', '')}/info` : '/master-app/info';

/** Версия установленного приложения из User-Agent («BonjourSalonApp/1.0.0»). */
export function masterAppVersion() {
  return CURRENT?.version ?? null;
}

/** «1.0.0» старше «1.1.0»? Сравнение по числам, а не строкам: «1.10» новее «1.9». */
export function isOlderVersion(installed, latest) {
  const a = String(installed).split('.').map((n) => Number.parseInt(n, 10) || 0);
  const b = String(latest).split('.').map((n) => Number.parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    const x = a[i] || 0;
    const y = b[i] || 0;
    if (x !== y) return x < y;
  }
  return false;
}
