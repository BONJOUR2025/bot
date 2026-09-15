/** Кабинет открыт внутри приложения «BONJOUR Мастер» (Android WebView).
 *
 *  Метку в User-Agent ставит само приложение (device/master_app, MainActivity).
 *  Во WebView не работают push-уведомления браузера и скачивание файлов, поэтому
 *  такие элементы прячем — кнопка, которая молча ничего не делает, хуже её
 *  отсутствия. */
export const IN_MASTER_APP =
  typeof navigator !== 'undefined' && /BonjourMasterApp\//.test(navigator.userAgent || '');
