/**
 * Блокировка прокрутки страницы — со счётчиком, один на всё приложение.
 *
 * Блокировать фон нужно в трёх разных местах: компоненту Modal, хуку
 * useDialogChrome (он следит за самодельными подложками) и полноэкранному
 * Viewer3D. Каждый делал это сам, по схеме «запомнить прежнее значение →
 * поставить hidden → вернуть прежнее». Схема разваливается, как только
 * блокировки накладываются: второй запоминает не исходное состояние, а
 * hidden, оставленный первым, и, отпуская, возвращает hidden — страница
 * перестаёт прокручиваться навсегда.
 *
 * Это и происходило на каждом окне из Modal: Modal ставил hidden, следом
 * MutationObserver в useDialogChrome видел появившуюся .modal-backdrop и
 * запоминал hidden как «прежнее». При закрытии Modal честно возвращал
 * пустую строку, а useDialogChrome тут же ставил обратно hidden.
 *
 * Счётчик снимает вопрос порядка: исходное состояние запоминается один раз,
 * на первом захвате, и возвращается один раз, когда отпущен последний.
 *
 * lockScroll() возвращает функцию «отпустить». Повторный её вызов ничего не
 * делает — иначе один компонент, отпустивший дважды (например, в StrictMode),
 * снял бы чужую блокировку.
 */
let depth = 0;
let prevOverflow = '';
let prevPadding = '';

export function lockScroll() {
  const { body } = document;

  if (depth === 0) {
    prevOverflow = body.style.overflow;
    prevPadding = body.style.paddingRight;
    // Ширину полосы прокрутки компенсируем padding-ом, иначе страница под
    // окном дёргается вправо на её ширину в момент открытия.
    const gap = window.innerWidth - document.documentElement.clientWidth;
    body.style.overflow = 'hidden';
    if (gap > 0) body.style.paddingRight = `${gap}px`;
  }
  depth += 1;

  let released = false;
  return function release() {
    if (released) return;
    released = true;
    depth -= 1;
    if (depth === 0) {
      body.style.overflow = prevOverflow;
      body.style.paddingRight = prevPadding;
    }
  };
}
