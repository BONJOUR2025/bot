/** Фотографии заказа из Agbis и полноэкранный просмотрщик.
 *
 * Вынесено из Clients.jsx, чтобы тем же кодом пользовалась вкладка «Заказы»
 * на странице продаж: жесты, зум и полноэкранный режим на мобильном стоили
 * достаточно, чтобы не заводить им вторую копию.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { RefreshCw } from 'lucide-react';
import { useSpring, animated, to } from '@react-spring/web';
import { useGesture } from '@use-gesture/react';
import api from '../api';
import { useViewport } from '../providers/ViewportProvider.jsx';

const fmtDate = (v) => {
  if (!v) return '—';
  const d = new Date(v);
  return isNaN(d) ? '—' : d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
};

// Лента миниатюр заказа. Миниатюры лежат в самой базе Agbis и почти ничего
// не стоят; полноразмерный снимок хранится на компьютере в салоне, поэтому
// тянется только по клику — см. app/services/agbis_photos.
export default function OrderPhotos({ contragentId, docNum, visible }) {
  const [photos, setPhotos] = useState(null);
  const [loading, setLoading] = useState(false);
  const [viewer, setViewer] = useState(null); // индекс открытого снимка

  useEffect(() => {
    if (!visible || photos || loading) return;
    let cancelled = false;
    setLoading(true);
    api.get(`/clients/${contragentId}/orders/${encodeURIComponent(docNum)}/photos`)
      .then((r) => { if (!cancelled) setPhotos(r.data || []); })
      .catch(() => { if (!cancelled) setPhotos([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // photos/loading намеренно не в зависимостях: это результат самого
    // эффекта. Включение их сюда заставляло React разбирать только что
    // начатый запрос на следующий же рендер (loading false->true меняет
    // зависимость раньше, чем сервер успевал ответить) — эффект
    // перезапускался, видел loading=true и выходил по guard'у, а исходный
    // запрос отвечал уже в "отменённый" — setPhotos/setLoading(false)
    // никогда не срабатывали. Лента висла на «Загрузка фотографий» даже
    // когда сервер отвечал за доли секунды.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, contragentId, docNum]);

  // Миниатюра приходит прямо в ответе списка, как data URI — не отдельным
  // <img src> на каждую: у заказа бывает под 90 снимков, и 90 независимых
  // запросов к серверу (каждый со своим подключением к Firebird) — ровно
  // то, из-за чего фотографии и «висели в вечной загрузке».
  const withThumb = (photos || []).filter((p) => p.thumb);
  if (!visible || (!loading && withThumb.length === 0)) return null;

  // Снимки привязаны к позиции заказа, а не к заказу целиком: одна пара
  // обуви и сумка в одном заказе — это разные наборы фотографий.
  const groups = [];
  for (const p of withThumb) {
    const last = groups[groups.length - 1];
    if (last && last.dosId === p.dos_id) last.items.push(p);
    else groups.push({ dosId: p.dos_id, item: p.item, items: [p] });
  }

  return (
    <div className="mt-3">
      {loading && <div className="text-xs text-[color:var(--color-muted-foreground)]">Загрузка фотографий…</div>}
      {groups.map((g) => (
        <div key={g.dosId} className="mb-3">
          <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1.5">
            {g.item} · {g.items.length} фото
          </div>
          <div className="flex flex-wrap gap-1.5">
            {g.items.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setViewer(withThumb.indexOf(p))}
                title={p.is_main ? 'Главное фото' : undefined}
                className={`rounded-md overflow-hidden border transition-colors hover:border-[color:var(--color-primary)] ${
                  p.is_main ? 'border-[color:var(--color-primary)]' : 'border-[color:var(--color-border)]'
                }`}
              >
                <img
                  src={p.thumb}
                  alt=""
                  className="block w-14 h-16 object-cover"
                />
              </button>
            ))}
          </div>
        </div>
      ))}
      {viewer != null && (
        <PhotoViewer photos={withThumb} index={viewer} onIndex={setViewer} onClose={() => setViewer(null)} />
      )}
    </div>
  );
}


// Путь для axios — без префикса /api, он уже в baseURL. Для <img> нужен
// полный путь, там axios не участвует; авторизация в этом случае идёт
// httpOnly-кукой, которую браузер подставляет сам.
const fullPhotoPath = (p) => `/clients/photos/${p.id}/full?md5=${encodeURIComponent(p.md5)}`;

// Явная привязка вместо <animated.img>: eslint не засчитывает
// member-expression в JSX как использование импорта.
const AnimatedImg = animated.img;
const AnimatedDiv = animated.div;

const GAP = 16;          // зазор между кадрами ленты, как в стоковых галереях
const ZOOM_MIN = 1;
const ZOOM_MAX = 4;
const ZOOM_DOUBLE_TAP = 2.5;
const SPRING = { tension: 300, friction: 30 };

// Резинка iOS: за границей ход не блокируется, а вязнет — чем дальше тянешь,
// тем меньше отдача. Жёсткий clamp вместо неё ощущается как заедание.
function rubber(delta, dim, c = 0.55) {
  if (!dim) return 0;
  return (delta * dim * c) / (dim + c * Math.abs(delta));
}

// Смещение, при котором точка p (координаты сцены от центра) остаётся под
// пальцем при смене масштаба s0 -> s1. Без этого картинка при щипке уползает
// к центру — главная причина ощущения, что жест живёт своей жизнью.
function anchorOffset(p, o0, s0, s1) {
  return p - ((p - o0) * s1) / s0;
}

function PhotoViewer({ photos, index, onIndex, onClose }) {
  const { isMobile } = useViewport();
  const photo = photos[index];

  // Соседние кадры грузятся вместе с текущим: без них свайп показывал бы
  // пустоту, и ощущения ленты не возникает.
  const [urls, setUrls] = useState({});     // id -> blobURL
  const [errors, setErrors] = useState({}); // id -> текст ошибки
  const urlsRef = useRef({});

  useEffect(() => { urlsRef.current = urls; }, [urls]);

  useEffect(() => {
    let cancelled = false;
    const wanted = [index, index - 1, index + 1].map((i) => photos[i]).filter(Boolean);
    wanted.forEach((p) => {
      if (urlsRef.current[p.id]) return;
      // Через axios, а не через <img>: только так виден текст ошибки от
      // сервера — «агент недоступен» вместо молчаливой битой картинки.
      api.get(fullPhotoPath(p), { responseType: 'blob' })
        .then((r) => {
          if (cancelled) return;
          setUrls((m) => (m[p.id] ? m : { ...m, [p.id]: URL.createObjectURL(r.data) }));
        })
        .catch(async (e) => {
          if (cancelled) return;
          let detail = 'Не удалось загрузить снимок';
          try {
            const parsed = JSON.parse(await e.response.data.text());
            if (parsed?.detail) detail = parsed.detail;
          } catch { /* оставляем общее сообщение */ }
          setErrors((m) => ({ ...m, [p.id]: detail }));
        });
    });
    return () => { cancelled = true; };
  }, [index, photos]);

  // Блобы освобождаются при закрытии, а не при смене кадра: во время листания
  // они нужны соседям, и пересоздавать их на каждый шаг — лишние запросы.
  useEffect(() => () => {
    Object.values(urlsRef.current).forEach((u) => URL.revokeObjectURL(u));
  }, []);

  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft' && index > 0) onIndex(index - 1);
      if (e.key === 'ArrowRight' && index < photos.length - 1) onIndex(index + 1);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [index, photos.length, onIndex, onClose]);

  // ── Жесты ─────────────────────────────────────────────────────────
  // Позиция живёт в spring и пишется в transform напрямую: обновление через
  // useState на каждый touchmove — это ре-рендер на каждый пиксель движения,
  // ~60 раз в секунду, и никакие пороги такую дёрганость не лечат.
  const stageRef = useRef(null);
  const zoomRef = useRef(1);
  const lastTap = useRef(0);
  const [zoomed, setZoomed] = useState(false);

  const box = useCallback(() => stageRef.current?.getBoundingClientRect(), []);
  // Ширина меряется один раз и при ресайзе, а не внутри интерполятора:
  // getBoundingClientRect на каждом кадре для каждого из трёх кадров — это
  // 180 принудительных пересчётов layout в секунду, отсюда и подрагивание
  // при появлении нового снимка.
  const [stageWidth, setStageWidth] = useState(0);
  const widthRef = useRef(0);
  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const measure = () => {
      const w = el.getBoundingClientRect().width;
      widthRef.current = w;
      setStageWidth(w);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const stageW = useCallback(() => widthRef.current || window.innerWidth, []);

  const [{ dx, dy, dismiss, backdrop, ox, oy, sc }, spring] = useSpring(() => ({
    dx: 0, dy: 0, dismiss: 1, backdrop: 1, ox: 0, oy: 0, sc: 1, config: SPRING,
  }));

  const setZoomState = useCallback((s) => {
    zoomRef.current = s;
    setZoomed(s > 1.01);
  }, []);

  // Новый кадр открывается «как есть», без унаследованного зума.
  useEffect(() => {
    setZoomState(1);
    spring.set({ dx: 0, dy: 0, dismiss: 1, backdrop: 1, ox: 0, oy: 0, sc: 1 });
  }, [index, spring, setZoomState]);

  // Пределы панорамирования увеличенного кадра.
  const panMax = useCallback((s) => {
    const b = box();
    if (!b) return [0, 0];
    return [Math.max(0, (b.width * (s - 1)) / 2), Math.max(0, (b.height * (s - 1)) / 2)];
  }, [box]);

  // Доводим ленту до соседнего кадра и только по завершении анимации меняем
  // индекс, одновременно обнуляя сдвиг — иначе кадр дёрнулся бы на ширину
  // экрана в момент переключения.
  const settleTo = useCallback((target) => {
    const dir = target > index ? -1 : 1;
    spring.start({
      dx: dir * (stageW() + GAP),
      onRest: () => { onIndex(target); spring.set({ dx: 0 }); },
    });
  }, [index, onIndex, spring, stageW]);

  const bind = useGesture(
    {
      onDrag: ({ down, movement: [mx, my], velocity: [vx, vy], direction: [dxDir, dyDir],
                 pinching, cancel, tap, event }) => {
        if (pinching) { cancel(); return; }

        if (tap) {
          const now = Date.now();
          if (now - lastTap.current < 300) {
            lastTap.current = 0;
            const b = box();
            const s0 = zoomRef.current;
            const s1 = s0 > 1.01 ? 1 : ZOOM_DOUBLE_TAP;
            if (s1 === 1 || !b) {
              setZoomState(1);
              spring.start({ sc: 1, ox: 0, oy: 0 });
            } else {
              // Приближаем к точке касания, а не к центру.
              const px = (event?.clientX ?? b.left + b.width / 2) - (b.left + b.width / 2);
              const py = (event?.clientY ?? b.top + b.height / 2) - (b.top + b.height / 2);
              const [mxLim, myLim] = panMax(s1);
              const nx = anchorOffset(px, ox.get(), s0, s1);
              const ny = anchorOffset(py, oy.get(), s0, s1);
              setZoomState(s1);
              spring.start({
                sc: s1,
                ox: Math.min(mxLim, Math.max(-mxLim, nx)),
                oy: Math.min(myLim, Math.max(-myLim, ny)),
              });
            }
          } else {
            lastTap.current = now;
          }
          return;
        }

        const s = zoomRef.current;

        // Увеличенный кадр жест панорамирует, а не листает ленту.
        if (s > 1.01) {
          const b = box();
          const [mxLim, myLim] = panMax(s);
          const rx = mx > mxLim ? mxLim + rubber(mx - mxLim, b?.width)
            : mx < -mxLim ? -mxLim + rubber(mx + mxLim, b?.width) : mx;
          const ry = my > myLim ? myLim + rubber(my - myLim, b?.height)
            : my < -myLim ? -myLim + rubber(my + myLim, b?.height) : my;
          if (down) { spring.start({ ox: rx, oy: ry, immediate: true }); return; }
          spring.start({
            ox: Math.min(mxLim, Math.max(-mxLim, rx)),
            oy: Math.min(myLim, Math.max(-myLim, ry)),
          });
          return;
        }

        const w = stageW();
        const vertical = Math.abs(my) > Math.abs(mx);

        if (down) {
          if (vertical && my > 0) {
            // Свайп вниз: кадр уменьшается и тускнеет, как «убирание» в iOS.
            const k = 1 - Math.min(Math.abs(my) / (w * 2), 0.35);
            spring.start({
              dy: my, dismiss: k,
              backdrop: 1 - Math.min(Math.abs(my) / 400, 0.6),
              immediate: true,
            });
          } else {
            // На краях ленты ход вязнет резинкой, а не упирается насмерть.
            const atStart = index === 0 && mx > 0;
            const atEnd = index === photos.length - 1 && mx < 0;
            spring.start({ dx: (atStart || atEnd) ? rubber(mx, w) : mx, immediate: true });
          }
          return;
        }

        // Оба условия требуют вертикального преобладания. Без этого быстрый
        // горизонтальный свайп с малейшим уклоном вниз закрывал просмотр
        // вместо листания — и жест ощущался как чересчур чувствительный.
        const closeByDrag = my > 110 && vertical;
        const closeByFlick = vertical && dyDir > 0 && vy > 0.6 && my > 60;
        if (closeByDrag || closeByFlick) {
          spring.start({ dy: window.innerHeight, dismiss: 0.6, backdrop: 0 });
          setTimeout(onClose, 180);
          return;
        }

        const byDrag = Math.abs(mx) > w * 0.35;
        const byFlick = vx > 0.3 && Math.abs(mx) > 10;
        if ((byDrag || byFlick) && !vertical) {
          const target = dxDir < 0 ? index + 1 : index - 1;
          if (target >= 0 && target < photos.length) { settleTo(target); return; }
        }
        spring.start({ dx: 0, dy: 0, dismiss: 1, backdrop: 1 });
      },

      onPinch: ({ offset: [s], origin: [px, py], first, last, memo }) => {
        const b = box();
        if (!b) return memo;
        // Опорные значения фиксируются на старте жеста: пересчёт от текущих
        // на каждом кадре накапливает ошибку, и точка щипка «плывёт».
        const base = first ? { s0: zoomRef.current, ox: ox.get(), oy: oy.get() } : memo;
        if (!base) return memo;

        const next = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, s));
        const cx = px - (b.left + b.width / 2);
        const cy = py - (b.top + b.height / 2);
        const [mxLim, myLim] = panMax(next);
        const nx = anchorOffset(cx, base.ox, base.s0, next);
        const ny = anchorOffset(cy, base.oy, base.s0, next);

        setZoomState(next);
        if (last && next <= 1.01) {
          setZoomState(1);
          spring.start({ sc: 1, ox: 0, oy: 0 });
          return undefined;
        }
        spring.start({
          sc: next,
          ox: Math.min(mxLim, Math.max(-mxLim, nx)),
          oy: Math.min(myLim, Math.max(-myLim, ny)),
          immediate: !last,
        });
        return base;
      },
    },
    {
      // threshold 10px — иначе дрожание пальца при тапе читается как свайп.
      drag: { filterTaps: true, threshold: 10 },
      pinch: {
        scaleBounds: { min: ZOOM_MIN, max: ZOOM_MAX },
        rubberband: 0.2,
        from: () => [zoomRef.current, 0],
      },
    },
  );

  const slides = [index - 1, index, index + 1].filter((i) => i >= 0 && i < photos.length);

  if (isMobile) {
    return (
      <AnimatedDiv
        // 100dvh, а не 100vh: на мобильных 100vh уходит под адресную строку,
        // и низ кадра с подписью оказывался за краем экрана.
        className="fixed inset-0 z-50 flex flex-col"
        style={{ height: '100dvh', backgroundColor: backdrop.to((v) => `rgba(0,0,0,${v})`) }}
      >
        <div className="flex items-center justify-between gap-3 px-4 py-3 text-white/90 flex-shrink-0">
          <div className="text-xs min-w-0 truncate">
            <span className="font-medium">{photo.item}</span>
            <span className="opacity-70 ml-2">
              {index + 1} / {photos.length}{photo.date ? ` · ${fmtDate(photo.date)}` : ''}
            </span>
          </div>
          <button onClick={onClose} aria-label="Закрыть"
            className="flex-shrink-0 w-9 h-9 flex items-center justify-center rounded-full bg-white/10 text-xl leading-none">
            &times;
          </button>
        </div>

        <div ref={stageRef} {...bind()}
          className="flex-1 relative overflow-hidden"
          style={{ minHeight: 0, touchAction: 'none' }}>
          {slides.map((i) => {
            const p = photos[i];
            const url = urls[p.id];
            const err = errors[p.id];
            return (
              <AnimatedDiv
                key={p.id}
                className="absolute inset-0 flex items-center justify-center"
                style={{
                  x: dx.to((v) => (i - index) * ((stageWidth || window.innerWidth) + GAP) + v),
                  y: dy,
                }}
              >
                {err && <div className="text-sm text-red-400 text-center px-6">{err}</div>}
                {!err && !url && (
                  <div className="text-sm text-white/70 flex items-center gap-2">
                    <RefreshCw size={15} className="animate-spin" /> Загрузка из хранилища…
                  </div>
                )}
                {!err && url && (
                  <AnimatedImg
                    src={url}
                    alt=""
                    draggable={false}
                    className="max-h-full max-w-full object-contain select-none"
                    // Стиль одинаковой формы у всех кадров, а не только у
                    // текущего: когда соседний кадр становился текущим, набор
                    // анимируемых свойств менялся с undefined на springs, и
                    // react-spring переподключал анимацию — отсюда моргание в
                    // момент появления снимка. Соседям пружины безвредны:
                    // зум сбрасывается при смене кадра, а листать увеличенное
                    // нельзя — там жест панорамирует.
                    style={{
                      x: ox, y: oy,
                      // Масштаб — произведение зума и «убирания»: при свайпе
                      // вниз кадр уменьшается поверх текущего зума.
                      scale: to([sc, dismiss], (z, k) => z * k),
                      willChange: 'transform',
                    }}
                  />
                )}
              </AnimatedDiv>
            );
          })}
        </div>

        <div className="flex items-center justify-center px-4 py-3 flex-shrink-0 text-white/50 text-[11px]">
          {zoomed ? 'Двойной тап — сбросить масштаб' : 'Свайп — листать · вниз — закрыть · щипок — зум'}
        </div>
      </AnimatedDiv>
    );
  }

  const url = urls[photo.id];
  const err = errors[photo.id];
  return (
    <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-4xl w-full flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm min-w-0">
            <span className="font-medium">{photo.item}</span>
            <span className="text-[color:var(--color-muted-foreground)] ml-2">
              {index + 1} из {photos.length}
              {photo.date ? ` · ${fmtDate(photo.date)}` : ''}
            </span>
          </div>
          <button onClick={onClose} className="btn text-xs px-2 py-1">Закрыть</button>
        </div>

        <div className="flex items-center justify-center min-h-[50vh] bg-[color:var(--color-bg-secondary)] rounded-lg">
          {!url && !err && (
            <div className="text-sm text-[color:var(--color-muted-foreground)] flex items-center gap-2">
              <RefreshCw size={15} className="animate-spin" /> Загрузка из хранилища…
            </div>
          )}
          {err && <div className="text-sm text-red-500 max-w-md text-center px-4">{err}</div>}
          {url && <img src={url} alt="" className="max-h-[70vh] max-w-full object-contain" />}
        </div>

        <div className="flex items-center justify-between gap-2">
          <button onClick={() => onIndex(index - 1)} disabled={index === 0}
            className="btn text-xs px-3 py-1.5 disabled:opacity-40">← Предыдущее</button>
          <button onClick={() => onIndex(index + 1)} disabled={index >= photos.length - 1}
            className="btn text-xs px-3 py-1.5 disabled:opacity-40">Следующее →</button>
        </div>
      </div>
    </div>
  );
}
