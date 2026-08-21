import { useEffect } from 'react';

/**
 * Гасит горизонтальный свайп внутри элемента, чтобы Safari не перехватывал
 * его под системный жест «свайп от края экрана = назад/вперёд».
 *
 * `touch-action: pan-y` в CSS — это лишь пассивная подсказка браузерному
 * скролл-движку. Системный edge-свайп в Safari — отдельный распознаватель
 * жестов на уровне UIKit, который слушает касания рядом с краем экрана
 * независимо от того, что говорит touch-action про элемент под пальцем.
 * Единственное, что реально может его остановить со стороны страницы —
 * активный (не passive) обработчик touchmove с явным preventDefault():
 * пока событие обрабатывается страницей, системный жест не срабатывает.
 *
 * Различаем направление сами: вертикальный свайп (прокрутка списка
 * пунктов меню) не трогаем вообще — preventDefault только когда сдвиг по
 * горизонтали заметно больше, чем по вертикали.
 *
 * @param {import('react').RefObject<HTMLElement>} ref
 * @param {boolean} [active=true] — выключать вне мобильного вида, чтобы
 *   не вешать лишние обработчики там, где панель не выезжает поверх экрана.
 */
export default function useSwipeGuard(ref, active = true) {
  useEffect(() => {
    const el = ref?.current;
    if (!el || !active) return undefined;

    let startX = 0;
    let startY = 0;
    let horizontal = false;

    const onStart = (e) => {
      const t = e.touches[0];
      startX = t.clientX;
      startY = t.clientY;
      horizontal = false;
    };

    const onMove = (e) => {
      const t = e.touches[0];
      const dx = t.clientX - startX;
      const dy = t.clientY - startY;
      // Направление решаем один раз, по первому заметному сдвигу — иначе
      // на диагональном движении флаг дёргался бы туда-сюда каждый кадр.
      if (!horizontal && Math.abs(dx) > 8 && Math.abs(dx) > Math.abs(dy)) {
        horizontal = true;
      }
      if (horizontal) e.preventDefault();
    };

    // passive:false обязателен — иначе preventDefault в touchmove браузер
    // просто проигнорирует (и выдаст предупреждение в консоли).
    el.addEventListener('touchstart', onStart, { passive: true });
    el.addEventListener('touchmove', onMove, { passive: false });

    return () => {
      el.removeEventListener('touchstart', onStart);
      el.removeEventListener('touchmove', onMove);
    };
  }, [ref, active]);
}
