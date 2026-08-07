/** Фотографии заказа из Agbis и полноэкранный просмотрщик.
 *
 * Вынесено из Clients.jsx, чтобы тем же кодом пользовалась вкладка «Заказы»
 * на странице продаж: жесты, зум и полноэкранный режим на мобильном стоили
 * достаточно, чтобы не заводить им вторую копию.
 */
import { useState, useEffect, useRef } from 'react';
import { RefreshCw } from 'lucide-react';
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

const ZOOM_MAX = 5;
const ZOOM_DOUBLE_TAP = 2.5;
// Порог горизонтального свайпа для смены снимка и вертикального — для
// закрытия. В долях ширины/высоты экрана, чтобы одинаково ощущалось и на
// маленьком телефоне, и на планшете.
const SWIPE_X_RATIO = 0.18;
const SWIPE_Y_RATIO = 0.22;

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

  // ── Жесты (только мобильный полноэкранный режим) ──────────────────
  // Реализованы вручную, а не нативным pinch браузера: внутри
  // position:fixed оверлея нативный зум ведёт себя непредсказуемо (то
  // масштабирует всю страницу под оверлеем, то не срабатывает вовсе), и
  // им нельзя ограничить масштаб или сбросить его при смене снимка.
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [drag, setDrag] = useState({ x: 0, y: 0 });   // текущий незавершённый свайп
  const [animating, setAnimating] = useState(false);
  const g = useRef({});
  const lastTap = useRef(0);
  const stageRef = useRef(null);

  // Новый снимок открывается всегда «как есть», без унаследованного зума.
  useEffect(() => { setZoom(1); setOffset({ x: 0, y: 0 }); setDrag({ x: 0, y: 0 }); }, [index]);

  const dist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);

  // Не даём картинке уехать за пределы экрана при панорамировании.
  function clampOffset(next, scale) {
    const box = stageRef.current?.getBoundingClientRect();
    if (!box) return next;
    const maxX = Math.max(0, (box.width * (scale - 1)) / 2);
    const maxY = Math.max(0, (box.height * (scale - 1)) / 2);
    return {
      x: Math.min(maxX, Math.max(-maxX, next.x)),
      y: Math.min(maxY, Math.max(-maxY, next.y)),
    };
  }

  function onTouchStart(e) {
    setAnimating(false);
    if (e.touches.length === 2) {
      g.current = { mode: 'pinch', startDist: dist(e.touches), startZoom: zoom };
      return;
    }
    if (e.touches.length === 1) {
      const t = e.touches[0];
      // Двойной тап — быстрый зум туда и обратно.
      const now = Date.now();
      if (now - lastTap.current < 300) {
        lastTap.current = 0;
        const to = zoom > 1 ? 1 : ZOOM_DOUBLE_TAP;
        setAnimating(true);
        setZoom(to);
        setOffset({ x: 0, y: 0 });
        g.current = { mode: 'none' };
        return;
      }
      lastTap.current = now;
      g.current = {
        mode: zoom > 1 ? 'pan' : 'swipe',
        startX: t.clientX, startY: t.clientY,
        baseOffset: { ...offset },
      };
    }
  }

  function onTouchMove(e) {
    const st = g.current;
    if (!st.mode || st.mode === 'none') return;

    if (st.mode === 'pinch' && e.touches.length === 2) {
      const next = Math.min(ZOOM_MAX, Math.max(1, st.startZoom * (dist(e.touches) / st.startDist)));
      setZoom(next);
      setOffset((o) => clampOffset(o, next));
      return;
    }
    if (e.touches.length !== 1) return;
    const t = e.touches[0];
    const dx = t.clientX - st.startX;
    const dy = t.clientY - st.startY;

    if (st.mode === 'pan') {
      setOffset(clampOffset({ x: st.baseOffset.x + dx, y: st.baseOffset.y + dy }, zoom));
    } else {
      setDrag({ x: dx, y: dy });
    }
  }

  function onTouchEnd() {
    const st = g.current;
    g.current = {};

    if (st.mode === 'pinch') {
      // Отпустили ниже единицы — возвращаем в исходное положение.
      if (zoom <= 1.02) { setAnimating(true); setZoom(1); setOffset({ x: 0, y: 0 }); }
      return;
    }
    if (st.mode !== 'swipe') return;

    const { x, y } = drag;
    const thresholdX = window.innerWidth * SWIPE_X_RATIO;
    const thresholdY = window.innerHeight * SWIPE_Y_RATIO;

    setAnimating(true);
    // Вертикальный свайп вниз закрывает — привычный жест для галерей.
    if (Math.abs(y) > Math.abs(x) && y > thresholdY) { onClose(); return; }
    if (x <= -thresholdX && index < photos.length - 1) { onIndex(index + 1); }
    else if (x >= thresholdX && index > 0) { onIndex(index - 1); }
    setDrag({ x: 0, y: 0 });
  }

  if (isMobile) {
    const zoomed = zoom > 1;
    return (
      <div
        // 100dvh, а не 100vh: на мобильных 100vh уходит под адресную строку,
        // и низ картинки с кнопками оказывался за краем экрана.
        className="fixed inset-0 z-50 bg-black flex flex-col"
        style={{ height: '100dvh', touchAction: 'none' }}
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
          className="flex-1 overflow-hidden flex items-center justify-center"
          style={{ minHeight: 0 }}
          onTouchStart={onTouchStart}
          onTouchMove={onTouchMove}
          onTouchEnd={onTouchEnd}
          onTouchCancel={onTouchEnd}
        >
          {state === 'loading' && (
            <div className="text-sm text-white/70 flex items-center gap-2">
              <RefreshCw size={15} className="animate-spin" /> Загрузка из хранилища…
            </div>
          )}
          {state === 'error' && <div className="text-sm text-red-400 text-center px-6">{error}</div>}
          {state === 'ok' && blobUrl && (
            <img
              src={blobUrl}
              alt=""
              draggable={false}
              className="max-h-full max-w-full object-contain select-none"
              style={{
                transform: `translate(${offset.x + drag.x}px, ${offset.y + (zoomed ? 0 : drag.y)}px) scale(${zoom})`,
                transition: animating ? 'transform 180ms ease-out' : 'none',
                // Пока не увеличено, свайп слегка «уводит» картинку —
                // жест ощущается отзывчивым, а не глухим.
                opacity: !zoomed && Math.abs(drag.y) > 40 ? 0.6 : 1,
              }}
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

