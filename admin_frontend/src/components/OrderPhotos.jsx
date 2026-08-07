/** Фотографии заказа из Agbis и полноэкранный просмотрщик.
 *
 * Вынесено из Clients.jsx, чтобы тем же кодом пользовалась вкладка «Заказы»
 * на странице продаж: жесты, зум и полноэкранный режим на мобильном стоили
 * достаточно, чтобы не заводить им вторую копию.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { RefreshCw } from 'lucide-react';
import { useSpring, animated } from '@react-spring/web';
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
// Явная привязка вместо <AnimatedImg>: eslint не засчитывает
// member-expression в JSX как использование импорта.
const AnimatedImg = animated.img;

const fullPhotoPath = (p) => `/clients/photos/${p.id}/full?md5=${encodeURIComponent(p.md5)}`;

function PhotoViewer({ photos, index, onIndex, onClose }) {
  const { isMobile } = useViewport();
  const photo = photos[index];
  const [state, setState] = useState('loading'); // loading | ok | error
  const [error, setError] = useState(null);
  const [blobUrl, setBlobUrl] = useState(null);

  useEffect(() => {
    setState('loading'); setError(null);
    let cancelled = false;
    // Через axios, а не через <img>: только так видно текст ошибки от
    // сервера — «агент недоступен» вместо молчаливой битой картинки.
    api.get(fullPhotoPath(photo), { responseType: 'blob' })
      .then((r) => {
        if (cancelled) return;
        setState('ok');
        setBlobUrl(URL.createObjectURL(r.data));
      })
      .catch(async (e) => {
        if (cancelled) return;
        setState('error');
        // Тело ошибки тоже пришло как blob — достаём из него detail.
        let detail = 'Не удалось загрузить снимок';
        try {
          const parsed = JSON.parse(await e.response.data.text());
          if (parsed?.detail) detail = parsed.detail;
        } catch { /* оставляем общее сообщение */ }
        setError(detail);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [photo.id]);

  useEffect(() => () => { if (blobUrl) URL.revokeObjectURL(blobUrl); }, [blobUrl]);

  // Соседние снимки подгружаются тихо, чтобы листалось без пауз. Браузер
  // положит их в свой кэш, и следующий клик отрисуется сразу.
  useEffect(() => {
    [index - 1, index + 1].forEach((i) => {
      const p = photos[i];
      if (p) api.get(fullPhotoPath(p), { responseType: 'blob' }).catch(() => {});
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index]);

  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft' && index > 0) onIndex(index - 1);
      if (e.key === 'ArrowRight' && index < photos.length - 1) onIndex(index + 1);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [index, photos.length, onIndex, onClose]);

  // ── Жесты (мобильный полноэкранный режим) ─────────────────────────
  //
  // Позиция картинки живёт в spring, а не в useState: обновление состояния
  // на каждый touchmove — это ре-рендер на каждый пиксель движения, ~60 раз
  // в секунду, и никакие пороги этой дёрганости не лечат. react-spring
  // пишет transform прямо в DOM, минуя reconciliation.
  //
  // Нативный pinch браузера не используем: внутри position:fixed оверлея он
  // ведёт себя непредсказуемо, и им нельзя ни ограничить масштаб, ни
  // сбросить его при переходе к следующему снимку.
  const stageRef = useRef(null);
  const zoomRef = useRef(1);   // актуальный масштаб для обработчиков, без ре-рендера
  const lastTap = useRef(0);   // отметка времени для распознавания двойного тапа
  const [zoomed, setZoomed] = useState(false);  // только для подсказки внизу

  const [{ x, y, scale, opacity }, spring] = useSpring(() => ({
    x: 0, y: 0, scale: 1, opacity: 1,
    config: { tension: 300, friction: 30 },
  }));

  const setZoomState = useCallback((s) => {
    zoomRef.current = s;
    setZoomed(s > 1.01);
  }, []);

  // Новый снимок открывается всегда «как есть», без унаследованного зума.
  useEffect(() => {
    setZoomState(1);
    spring.start({ x: 0, y: 0, scale: 1, opacity: 1, immediate: true });
  }, [index, spring, setZoomState]);

  // Границы панорамирования: за края увеличенной картинки не пускаем.
  const clamp = useCallback((nx, ny, s) => {
    const box = stageRef.current?.getBoundingClientRect();
    if (!box) return [nx, ny];
    const maxX = Math.max(0, (box.width * (s - 1)) / 2);
    const maxY = Math.max(0, (box.height * (s - 1)) / 2);
    return [Math.min(maxX, Math.max(-maxX, nx)), Math.min(maxY, Math.max(-maxY, ny))];
  }, []);

  const bind = useGesture(
    {
      onDrag: ({ down, movement: [mx, my], velocity: [vx, vy], direction: [dx, dy], pinching, cancel, tap }) => {
        if (pinching) { cancel(); return; }
        // Двойной тап ловим здесь, а не отдельным onDoubleClick: такого
        // обработчика у useGesture нет, он молча игнорировался бы. На тач-
        // экранах DOM-событие dblclick к тому же приходит с задержкой ~300мс
        // и не везде.
        if (tap) {
          const now = Date.now();
          if (now - lastTap.current < 300) {
            lastTap.current = 0;
            const to = zoomRef.current > 1.01 ? 1 : 2.5;
            setZoomState(to);
            spring.start({ scale: to, x: 0, y: 0 });
          } else {
            lastTap.current = now;
          }
          return;
        }
        const s = zoomRef.current;

        // Увеличенная картинка — жест панорамирует её, а не листает ленту.
        if (s > 1.01) {
          const [cx, cy] = clamp(mx, my, s);
          spring.start({ x: cx, y: cy, immediate: down });
          return;
        }

        if (down) {
          spring.start({ x: mx, y: my, opacity: 1 - Math.min(Math.abs(my) / 400, 0.5), immediate: true });
          return;
        }

        // Быстрый флик закрывает/листает даже на коротком расстоянии —
        // отсюда порог по скорости рядом с порогом по расстоянию.
        const w = stageRef.current?.getBoundingClientRect().width || window.innerWidth;
        const closeByDrag = my > 110 && my > Math.abs(mx);
        const closeByFlick = vy > 0.5 && dy > 0 && Math.abs(my) > 10;
        if (closeByDrag || closeByFlick) {
          spring.start({ y: window.innerHeight, opacity: 0 });
          setTimeout(onClose, 180);
          return;
        }

        const nextByDrag = Math.abs(mx) > w * 0.35;
        const nextByFlick = vx > 0.3 && Math.abs(mx) > 10;
        if ((nextByDrag || nextByFlick) && Math.abs(mx) > Math.abs(my)) {
          const forward = dx < 0;
          const target = forward ? index + 1 : index - 1;
          if (target >= 0 && target < photos.length) { onIndex(target); return; }
        }
        spring.start({ x: 0, y: 0, opacity: 1 });
      },

      onPinch: ({ offset: [s], first, last }) => {
        const next = Math.min(4, Math.max(1, s));
        setZoomState(next);
        if (first) return;
        if (last && next <= 1.01) {
          spring.start({ x: 0, y: 0, scale: 1 });
          setZoomState(1);
          return;
        }
        const [cx, cy] = clamp(x.get(), y.get(), next);
        spring.start({ scale: next, x: cx, y: cy, immediate: !last });
      },

    },
    {
      // threshold 10px — иначе дрожание пальца при обычном тапе читается
      // как свайп. filterTaps даёт флаг tap вместо нулевого перетаскивания.
      drag: { filterTaps: true, threshold: 10, from: () => [x.get(), y.get()] },
      pinch: { scaleBounds: { min: 1, max: 4 }, rubberband: 0.2, from: () => [zoomRef.current, 0] },
    },
  );

  if (isMobile) {
    return (
      <div
        // 100dvh, а не 100vh: на мобильных 100vh уходит под адресную строку,
        // и низ картинки с подписью оказывался за краем экрана.
        className="fixed inset-0 z-50 bg-black flex flex-col"
        style={{ height: '100dvh' }}
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

        <div
          ref={stageRef}
          {...bind()}
          className="flex-1 overflow-hidden flex items-center justify-center"
          style={{ minHeight: 0, touchAction: 'none' }}
        >
          {state === 'loading' && (
            <div className="text-sm text-white/70 flex items-center gap-2">
              <RefreshCw size={15} className="animate-spin" /> Загрузка из хранилища…
            </div>
          )}
          {state === 'error' && <div className="text-sm text-red-400 text-center px-6">{error}</div>}
          {state === 'ok' && blobUrl && (
            <AnimatedImg
              src={blobUrl}
              alt=""
              draggable={false}
              className="max-h-full max-w-full object-contain select-none"
              style={{ x, y, scale, opacity, willChange: 'transform' }}
            />
          )}
        </div>

        <div className="flex items-center justify-center gap-4 px-4 py-3 flex-shrink-0 text-white/50 text-[11px]">
          {zoomed ? 'Двойной тап — сбросить масштаб' : 'Свайп — листать · вниз — закрыть · щипок — зум'}
        </div>
      </div>
    );
  }

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
          {state === 'loading' && (
            <div className="text-sm text-[color:var(--color-muted-foreground)] flex items-center gap-2">
              <RefreshCw size={15} className="animate-spin" /> Загрузка из хранилища…
            </div>
          )}
          {state === 'error' && (
            <div className="text-sm text-red-500 max-w-md text-center px-4">{error}</div>
          )}
          {state === 'ok' && blobUrl && (
            <img src={blobUrl} alt="" className="max-h-[70vh] max-w-full object-contain" />
          )}
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

