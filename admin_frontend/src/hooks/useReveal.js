import { useEffect } from 'react';

/**
 * Проявление блоков с классом .ui-reveal.
 *
 * Наблюдатель один на весь экран и следит за всем поддеревом, а не за
 * заранее собранным списком узлов. Это принципиально: раньше хук
 * собирал `querySelectorAll('.ui-reveal')` один раз при монтировании, и
 * любой элемент, добавленный позже, оставался с opacity:0 навсегда.
 * Так и вышло — заголовки дашборда и сводного отчёта по ФОТ получили
 * класс, но не попали ни под один наблюдатель и были невидимы,
 * продолжая занимать место. На странице, где данные приходят после
 * запроса, это касалось бы вообще всего содержимого.
 *
 * Поэтому здесь два наблюдателя: IntersectionObserver проявляет то, что
 * попало во вьюпорт, а MutationObserver подхватывает узлы, появившиеся
 * после загрузки данных.
 *
 * @param {import('react').RefObject<HTMLElement>} rootRef контейнер экрана
 * @param {object}  [opts]
 * @param {number}  [opts.stagger=70] задержка между соседними блоками, мс
 * @param {number}  [opts.max=8]      после скольких блоков задержку не растить
 */
export default function useReveal(rootRef, { stagger = 70, max = 8 } = {}) {
  useEffect(() => {
    const root = rootRef?.current;
    if (!root) return undefined;

    const reduced =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

    const revealAll = () => {
      root.querySelectorAll('.ui-reveal:not(.is-in)').forEach((el) => el.classList.add('is-in'));
    };

    // Без наблюдателя или при выключенной анимации показываем сразу:
    // пустой экран хуже, чем экран без эффекта.
    if (reduced || typeof IntersectionObserver === 'undefined') {
      revealAll();
      return undefined;
    }

    let shown = 0;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const el = entry.target;
          // Задержку считаем в момент появления, а не по позиции в DOM:
          // иначе блок, до которого доскроллили первым, ждал бы очередь
          // всех предшествующих.
          el.style.setProperty('--reveal-delay', `${Math.min(shown, max) * stagger}ms`);
          shown += 1;
          el.classList.add('is-in');
          io.unobserve(el);
        });
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.05 },
    );

    const observeAll = () => {
      root.querySelectorAll('.ui-reveal:not(.is-in)').forEach((el) => io.observe(el));
    };
    observeAll();

    // Содержимое почти всегда приходит после запроса к API, то есть
    // позже монтирования. Без этого наблюдателя оно осталось бы скрытым.
    const mo = new MutationObserver(observeAll);
    mo.observe(root, { childList: true, subtree: true });

    // Страховка: если что-то помешает наблюдателю сработать, через пять
    // секунд показываем всё принудительно. Невидимый контент — куда
    // худший исход, чем пропущенная анимация.
    const failsafe = setTimeout(revealAll, 5000);

    return () => {
      io.disconnect();
      mo.disconnect();
      clearTimeout(failsafe);
    };
  }, [rootRef, stagger, max]);
}
