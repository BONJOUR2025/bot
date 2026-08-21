import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * Сбрасывает прокрутку окна к верху при каждой смене маршрута.
 *
 * BrowserRouter (в отличие от data-роутера) не делает этого сам — только
 * createBrowserRouter умеет <ScrollRestoration>, а здесь используется
 * классический API. Без этого компонента прокрутка страницы переносится
 * между экранами как есть.
 *
 * Нашли это так: после входа на настоящем iPhone (мобильный Safari/WebKit)
 * заголовок дашборда оказывался наполовину под липкой шапкой. Причина не
 * в CSS — window.scrollY после логина был 118, хотя тест ничего не
 * прокручивал. На поле пароля был фокус, мобильный WebKit сам подскроллил
 * страницу, чтобы поле не пряталось под клавиатурой, а переход с /login на
 * /admin — client-side, без перезагрузки, — унёс эту прокрутку с собой.
 * Дашборд отрисовался уже съехавшим, и шапка легла поверх его заголовка.
 */
export default function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return null;
}
