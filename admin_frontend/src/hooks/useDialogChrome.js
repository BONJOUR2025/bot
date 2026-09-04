import { useEffect } from 'react';

import { lockScroll } from '../utils/scrollLock.js';

/**
 * Общее поведение модальных окон — для тех, что собраны вручную.
 *
 * Компонент Modal.jsx умеет закрываться по Escape, блокировать прокрутку
 * фона и объявлять себя скринридеру. Но половина окон в приложении его
 * не использует: только в подборе персонала одиннадцать собственных
 * подложек .modal-backdrop с разными z-index (вложенные окна). Переписать
 * их на общий компонент нельзя, не сломав эту вложенность: Modal уходит
 * порталом в body и ставит свой z-index.
 *
 * Поэтому поведение навешивается снаружи. Наблюдатель следит за
 * появлением любых .modal-backdrop в документе и:
 *
 * - блокирует прокрутку страницы, пока открыто хотя бы одно окно;
 * - по Escape закрывает верхнее;
 * - проставляет role="dialog" и aria-modal, если их нет.
 *
 * Escape работает так: подложки закрываются кликом мимо окна
 * (`e.target === e.currentTarget && onClose()`), поэтому вместо поиска
 * чужого обработчика мы синтезируем клик по самой подложке. Цель клика
 * совпадает с элементом-обработчиком, то есть срабатывает ровно та же
 * ветка, что и при клике мышью. Если у подложки обработчика нет,
 * ничего не происходит — как и раньше.
 */
export default function useDialogChrome() {
  useEffect(() => {
    // Отпускалка общего счётчика; null — сейчас не держим.
    let releaseScroll = null;

    const backdrops = () => [...document.querySelectorAll('.modal-backdrop')];

    // Верхнее окно: сначала по z-index, при равенстве — последнее в DOM.
    const topmost = () => {
      const list = backdrops();
      if (!list.length) return null;
      return list.reduce((best, el) => {
        const z = parseInt(getComputedStyle(el).zIndex, 10) || 0;
        const bz = parseInt(getComputedStyle(best).zIndex, 10) || 0;
        return z >= bz ? el : best;
      });
    };

    const sync = () => {
      const list = backdrops();

      list.forEach((el) => {
        if (!el.getAttribute('role')) el.setAttribute('role', 'dialog');
        if (!el.getAttribute('aria-modal')) el.setAttribute('aria-modal', 'true');
      });

      const shouldLock = list.length > 0;
      if (shouldLock && !releaseScroll) {
        releaseScroll = lockScroll();
      } else if (!shouldLock && releaseScroll) {
        releaseScroll();
        releaseScroll = null;
      }
    };

    const onKeyDown = (e) => {
      if (e.key !== 'Escape') return;
      const el = topmost();
      if (!el) return;
      // Клик по самой подложке — та же ветка, что и при клике мышью мимо
      // окна. Модалки, собранные без обработчика, просто не отреагируют.
      el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    };

    const mo = new MutationObserver(sync);
    mo.observe(document.body, { childList: true, subtree: true });
    document.addEventListener('keydown', onKeyDown);
    sync();

    return () => {
      mo.disconnect();
      document.removeEventListener('keydown', onKeyDown);
      releaseScroll?.();
    };
  }, []);
}
