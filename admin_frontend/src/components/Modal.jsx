import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

/**
 * Модальное окно: подложка + портал в body. Саму карточку рисует
 * вызывающая страница (обычно классом .modal-card).
 *
 * Компонент отвечает за поведение, которого раньше не было ни здесь, ни
 * на семнадцати использующих его страницах:
 *
 * - Escape закрывает окно. Без этого единственный способ выйти — попасть
 *   мышью по подложке или по крестику.
 * - Фон не прокручивается, пока окно открыто. Иначе колесо мыши над
 *   подложкой прокручивает страницу под ней, и, закрыв окно, человек
 *   оказывается не там, где был.
 * - Фокус переносится внутрь окна при открытии и возвращается на
 *   элемент, с которого его открыли, при закрытии.
 * - role="dialog" и aria-modal: без них скринридер продолжает читать
 *   страницу под окном как обычное содержимое.
 *
 * Полноценной ловушки фокуса (Tab по кругу внутри окна) здесь нет —
 * это потребовало бы обхода фокусируемых элементов на каждый Tab.
 * Перенос фокуса внутрь уже закрывает основной сценарий.
 */
export default function Modal({ children, isOpen, onClose, label }) {
  const surfaceRef = useRef(null);
  const restoreRef = useRef(null);

  // onClose приходит инлайновой стрелкой (`onClose={() => setOpen(false)}`)
  // со всех семнадцати страниц, то есть на каждом рендере это новая функция.
  // Пока она стояла в зависимостях эффекта, весь эффект переигрывался на
  // каждый рендер родителя: очистка возвращала фокус на элемент, с которого
  // окно открыли, а следующий заход тут же переводил его на первое поле
  // окна. На «Имуществе», где раз в секунду тикают часы телеметрии, это
  // означало кражу фокуса раз в секунду — открытый выпадающий список
  // (нативный select или datalist) закрывался сам собой, а курсор из
  // любого поля прыгал в первое. Замерено в браузере: 0.28 с после клика.
  //
  // Ссылка вместо зависимости: эффект видит всегда свежий onClose, но
  // запускается ровно один раз на открытие.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!isOpen) return undefined;

    restoreRef.current = document.activeElement;

    const onKeyDown = (e) => {
      if (e.key === 'Escape') closeRef.current?.();
    };
    document.addEventListener('keydown', onKeyDown);

    // Ширину полосы прокрутки компенсируем padding-ом, иначе в момент
    // открытия страница под окном дёргается вправо на её ширину.
    const { body } = document;
    const prevOverflow = body.style.overflow;
    const prevPadding = body.style.paddingRight;
    const gap = window.innerWidth - document.documentElement.clientWidth;
    body.style.overflow = 'hidden';
    if (gap > 0) body.style.paddingRight = `${gap}px`;

    // Ждём кадр: содержимое окна на этот момент уже смонтировано.
    const raf = requestAnimationFrame(() => {
      const surface = surfaceRef.current;
      if (!surface) return;
      const focusable = surface.querySelector(
        'input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      );
      (focusable || surface).focus?.();
    });

    return () => {
      document.removeEventListener('keydown', onKeyDown);
      cancelAnimationFrame(raf);
      body.style.overflow = prevOverflow;
      body.style.paddingRight = prevPadding;
      restoreRef.current?.focus?.();
    };
  }, [isOpen]);

  if (!isOpen) return null;

  // Роль и фокус висят на самой подложке, без промежуточной обёртки:
  // .modal-backdrop центрирует содержимое через flex, и лишний узел
  // между ней и карточкой стал бы flex-элементом, изменив раскладку
  // сразу на семнадцати страницах.
  return createPortal(
    <div
      ref={surfaceRef}
      className="modal-backdrop"
      style={{ zIndex: 9999, outline: 'none' }}
      role="dialog"
      aria-modal="true"
      aria-label={label}
      tabIndex={-1}
      onClick={(e) => e.target === e.currentTarget && closeRef.current?.()}
    >
      {children}
    </div>,
    document.body,
  );
}
