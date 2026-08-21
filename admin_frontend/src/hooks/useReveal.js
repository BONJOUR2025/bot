import { useEffect, useRef } from 'react';

/**
 * Появление блока при въезде в вьюпорт — основа хореографии Ethereal Glass.
 *
 * Возвращает ref, который надо повесить на контейнер. Все потомки с классом
 * .ui-reveal внутри него получают .is-in по мере появления, со сдвигом по
 * времени, чтобы блоки не «выстреливали» одновременно.
 *
 * Почему IntersectionObserver, а не слушатель scroll: обработчик скролла
 * срабатывает десятки раз в секунду и на каждом кадре заставляет читать
 * геометрию, то есть провоцирует layout thrashing. Наблюдатель уведомляет
 * только о смене видимости и делает это вне основного потока вёрстки.
 *
 * Анимируются исключительно transform/opacity/filter (см. .ui-reveal в
 * globals.css) — ни одно из них не вызывает пересчёт раскладки.
 *
 * @param {object}  [opts]
 * @param {number}  [opts.stagger=70]  задержка между соседними блоками, мс
 * @param {number}  [opts.max=10]      после скольких блоков задержку не растить
 *                                     (иначе низ длинной страницы ждёт секунды)
 * @param {unknown} [opts.deps]        пересобрать наблюдение при смене данных
 */
export default function useReveal({ stagger = 70, max = 10, deps } = {}) {
  const ref = useRef(null);

  useEffect(() => {
    const root = ref.current;
    if (!root) return undefined;

    const targets = Array.from(root.querySelectorAll('.ui-reveal:not(.is-in)'));
    if (!targets.length) return undefined;

    // Без поддержки наблюдателя (очень старый WebView) и при выключенной
    // анимации показываем всё сразу: пустая страница хуже, чем страница
    // без эффекта.
    const reduced =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

    if (reduced || typeof IntersectionObserver === 'undefined') {
      targets.forEach((el) => el.classList.add('is-in'));
      return undefined;
    }

    let shown = 0;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const el = entry.target;
          // Задержку считаем в момент появления, а не по позиции в DOM:
          // иначе блок, до которого доскроллили первым, всё равно ждал бы
          // очередь всех предшествующих.
          el.style.setProperty('--reveal-delay', `${Math.min(shown, max) * stagger}ms`);
          shown += 1;
          el.classList.add('is-in');
          io.unobserve(el);
        });
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.05 },
    );

    targets.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [stagger, max, deps]);

  return ref;
}
