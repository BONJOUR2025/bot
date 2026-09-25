import { useEffect, useState } from 'react';
import { Send } from 'lucide-react';
import api from '../api.js';

/** Плашка «Подключите Telegram-бота» над заработком мастера.
 *
 *  Без бота мастер не получает уведомлений о заказах и работе. Ссылка ведёт
 *  в бота с меткой сотрудника (start=emp_<id>): запуск попадает в «Доступ →
 *  Пользователи бота» уже с подсказкой, кто это, и админ подтверждает
 *  привязку. Пока админ не привязал, плашка остаётся, но после нажатия
 *  говорит «ждём привязку», а не зовёт запускать бота снова. */
const STARTED_KEY = 'tg-bot-started';

function readStarted() {
  try {
    return window.localStorage.getItem(STARTED_KEY) === '1';
  } catch {
    return false;
  }
}

export default function TelegramBotBanner() {
  const [state, setState] = useState(null);
  const [started, setStarted] = useState(readStarted);

  useEffect(() => {
    let cancelled = false;
    api.get('/masters/me/telegram')
      .then((r) => { if (!cancelled) setState(r.data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  if (!state || state.linked || !state.bot_url) return null;

  const onOpen = () => {
    setStarted(true);
    try { window.localStorage.setItem(STARTED_KEY, '1'); } catch { /* только подсказка */ }
  };

  return (
    <div className="tg-banner" role="status">
      <Send size={20} className="tg-banner__icon" aria-hidden="true" />
      <div className="tg-banner__text">
        {started ? (
          <>
            <b>Бот запущен — ждём привязку</b>
            <span>Администратор подключит бота к вашему профилю, и уведомления начнут приходить. Если бот не открылся, нажмите ещё раз.</span>
          </>
        ) : (
          <>
            <b>Подключите Telegram-бота</b>
            <span>Чтобы всегда получать важные уведомления о заказах и работе.</span>
          </>
        )}
      </div>
      <a className="btn btn--primary tg-banner__btn" href={state.bot_url} target="_blank" rel="noreferrer" onClick={onOpen}>
        {started ? 'Открыть снова' : 'Запустить бота'}
      </a>
    </div>
  );
}
