import { useEffect, useRef } from 'react';

/**
 * Системная кнопка «Назад» закрывает открытое окно, а не уводит со страницы.
 *
 * Приложение мастера на Android по «Назад» листает историю WebView
 * (goBack), а на корне закрывается. Но карточка заказа, фото во весь
 * экран, диалоги и меню кабинета — это состояние React, в истории их нет:
 * «Назад» пролистывал их насквозь — уводил на прошлый раздел или сразу
 * закрывал приложение. То же в браузере на телефоне жестом «назад».
 *
 * Пока окно открыто, в истории лежит своя запись с тем же адресом. «Назад»
 * снимает её — и закрывается только верхнее из открытых окон (фото поверх
 * карточки заказа закрывается первым). Если окно закрыли кнопкой на экране,
 * запись снимается за ним, чтобы следующий «Назад» не уходил в пустоту.
 */

const stack = [];
let skipPops = 0;
let listening = false;
// Запись, которую окно только что освободило. Снимаем её не сразу: если
// тут же открылось следующее окно (закрыл одно фото — открыл другое; или
// React в разработке монтирует компонент дважды), оно забирает эту запись
// себе. Иначе асинхронный history.back() снял бы уже новую запись.
let released = null;

function onPopState() {
  if (skipPops > 0) {
    skipPops -= 1;
    return;
  }
  const top = stack.pop();
  if (top) {
    top.popped = true;
    top.close();
  }
}

export default function useBackClose(active, onClose) {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!active || typeof window === 'undefined') return undefined;
    if (!listening) {
      window.addEventListener('popstate', onPopState);
      listening = true;
    }
    let token;
    if (released && window.history.state?.bonjourOverlay === released.token) {
      clearTimeout(released.timer);
      token = released.token;
    } else {
      token = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      // Состояние роутера (key, idx) копируем: для React Router это та же
      // страница, и при снятии записи он ничего не перерисовывает.
      window.history.pushState({ ...(window.history.state || {}), bonjourOverlay: token }, '');
    }
    released = null;
    const entry = { token, popped: false, close: () => closeRef.current?.() };
    stack.push(entry);

    return () => {
      const i = stack.indexOf(entry);
      if (i !== -1) stack.splice(i, 1);
      // Закрыли кнопкой на экране — снимаем свою запись. Если поверх уже
      // перешли на другую страницу, запись не наша и трогать историю нельзя.
      if (entry.popped) return;
      const timer = setTimeout(() => {
        if (released?.token !== token) return;
        released = null;
        if (window.history.state?.bonjourOverlay === token) {
          skipPops += 1;
          window.history.back();
        }
      }, 0);
      released = { token, timer };
    };
  }, [active]);
}
