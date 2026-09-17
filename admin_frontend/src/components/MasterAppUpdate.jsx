import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import api from '../api.js';
import { APP_INFO_URL, APP_KIND, MASTER_APP_UPDATE_URL, isOlderVersion, masterAppVersion } from '../utils/masterApp.js';

/** Плашка «Доступна новая версия» внутри приложения «BONJOUR Мастер».
 *
 *  Сравнивает версию из User-Agent приложения с APK, лежащим на сервере.
 *  Кнопка ведёт на страницу установки через http-адрес: даже версия 1.0.0,
 *  где у WebView нет загрузчика, открывает всё, что не https://app.bonjour.pw,
 *  во внешнем браузере — а там сервер перенаправит на https и скачивание
 *  работает. Новая версия ставится поверх старой: подпись та же. */
export default function MasterAppUpdate() {
  const installed = masterAppVersion();
  const [latest, setLatest] = useState(null);

  useEffect(() => {
    if (!installed) return undefined;
    let alive = true;
    api
      .get(APP_INFO_URL)
      .then((res) => {
        if (alive && res.data?.available) setLatest(res.data.version_name);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [installed]);

  if (!installed || !latest || !isOlderVersion(installed, latest)) return null;

  return (
    <div className="emp-app-update" role="status">
      <div className="emp-app-update__text">
        <b>Доступна новая версия приложения {latest}</b>
        <span>У вас {installed}. {APP_KIND === 'salon' ? 'Обновление ставится поверх, вход сохранится.' : 'В новой — сканер бирок камерой.'}</span>
      </div>
      <a className="btn btn--primary emp-app-update__btn" href={MASTER_APP_UPDATE_URL}>
        <Download size={18} />
        Обновить
      </a>
    </div>
  );
}
