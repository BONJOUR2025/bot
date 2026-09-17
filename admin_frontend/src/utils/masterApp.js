/** Кабинет открыт внутри приложения «BONJOUR Мастер» (Android WebView).
 *
 *  Метку в User-Agent ставит само приложение (device/master_app, MainActivity).
 *  Во WebView не работают push-уведомления браузера и скачивание файлов, поэтому
 *  такие элементы прячем — кнопка, которая молча ничего не делает, хуже её
 *  отсутствия. */
export const IN_MASTER_APP =
  typeof navigator !== 'undefined' && /BonjourMasterApp\//.test(navigator.userAgent || '');

/** Страница установки по http. Приложение (с версии 1.0.0) выпускает во внешний
 *  браузер всё, что не https://app.bonjour.pw, а сервер отвечает на http
 *  переадресацией на https — так мастер попадает в Chrome, где скачивание APK
 *  работает, даже в версии без собственного загрузчика. */
export const MASTER_APP_UPDATE_URL = 'http://app.bonjour.pw/api/master-app/';

/** Версия установленного приложения из User-Agent («BonjourMasterApp/1.0.0»). */
export function masterAppVersion() {
  if (typeof navigator === 'undefined') return null;
  const match = /BonjourMasterApp\/([\d.]+)/.exec(navigator.userAgent || '');
  return match ? match[1] : null;
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
