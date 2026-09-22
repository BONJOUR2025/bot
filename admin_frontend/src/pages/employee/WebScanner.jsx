import { useCallback, useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';

/** Сканер бирки камерой в браузере.
 *
 *  В приложении сканирует системный сканер Google (мост BonjourApp), у него и
 *  автофокус, и подсветка. В браузере камеру берём через getUserMedia, а
 *  распознаём встроенным BarcodeDetector, если он есть и умеет Code 128
 *  (Chrome на Android и macOS). Во всех остальных браузерах — Safari на
 *  iPhone, Chrome на Windows, Firefox — работает ZXing, собранный в
 *  WebAssembly (около мегабайта, грузится с нашего сервера).
 *
 *  Скорость. Первая версия отдавала ZXing весь кадр раз в 250 мс, со всеми
 *  форматами вплоть до QR и в режиме «искать изо всех сил» — в Safari бирка
 *  находилась за несколько секунд, тогда как сканер Google в приложении
 *  ловит её мгновенно. Теперь:
 *  - камера просит Full HD: без этого Safari отдаёт 640×480, штрихкод выходит
 *    мелким, и бирку приходится подносить так близко, что камера iPhone
 *    перестаёт фокусироваться;
 *  - распознаётся только полоса в центре кадра, где рамка, не шире 1280 px;
 *  - только линейные форматы, как на бирках; QR — самое дорогое в поиске —
 *    не ищем;
 *  - без пауз: следующий кадр берётся, как только готов предыдущий ответ;
 *  - каждая пятая попытка — весь кадр с поворотом, на случай если бирку
 *    держат вертикально;
 *  - модуль ZXing грузится заранее, при открытии экрана «Скан», а не при
 *    нажатии кнопки.
 *
 *  Результат отдаётся тем же событием `bonjour-scan`, что и приложение, —
 *  страница «Скан» не знает, откуда пришла бирка. */

// Как в нативном приложении (MainActivity), но без QR: на бирках его нет.
const NATIVE_FORMATS = ['code_128', 'code_39', 'code_93', 'itf', 'ean_13', 'codabar'];
const ZXING_FORMATS = ['Code128', 'Code39', 'Code93', 'ITF', 'EAN13', 'Codabar'];
const BAND_MAX_WIDTH = 1280;
const FULL_FRAME_EVERY = 5;

export function canScanInBrowser() {
  // Камера в браузере доступна только по https (и на localhost).
  return (
    typeof window !== 'undefined' &&
    window.isSecureContext !== false &&
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia
  );
}

async function nativeDetector() {
  if (typeof window === 'undefined' || !('BarcodeDetector' in window)) return null;
  try {
    // На Windows и Linux Chrome объявляет BarcodeDetector, но список
    // форматов у него пустой — такой детектор ничего не найдёт.
    const supported = await window.BarcodeDetector.getSupportedFormats();
    const formats = NATIVE_FORMATS.filter((f) => supported.includes(f));
    return formats.includes('code_128') ? new window.BarcodeDetector({ formats }) : null;
  } catch {
    return null;
  }
}

let zxingPromise = null;
function loadZXing() {
  if (!zxingPromise) {
    zxingPromise = Promise.all([
      import('zxing-wasm/reader'),
      import('zxing-wasm/reader/zxing_reader.wasm?url'),
    ]).then(async ([zxing, { default: wasmUrl }]) => {
      // Без locateFile библиотека тянет .wasm с jsDelivr — лишняя внешняя
      // зависимость у экрана, которым мастер пользуется весь день.
      await zxing.prepareZXingModule({
        overrides: { locateFile: (path, prefix) => (path.endsWith('.wasm') ? wasmUrl : prefix + path) },
        fireImmediately: true,
      });
      return zxing;
    });
    zxingPromise.catch(() => { zxingPromise = null; });
  }
  return zxingPromise;
}

/** Загрузить распознавание заранее, пока мастер ещё не нажал «Сканировать». */
export function preloadWebScanner() {
  if (!canScanInBrowser()) return;
  nativeDetector().then((d) => { if (!d) loadZXing().catch(() => {}); });
}

/** Функция «кадр → строка штрихкода или null» для выбранного движка. */
async function makeReader() {
  const native = await nativeDetector();
  if (native) {
    return async (video) => {
      const codes = await native.detect(video);
      return codes.map((c) => c.rawValue || '');
    };
  }
  const zxing = await loadZXing();
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  let attempt = 0;
  return async (video) => {
    const vw = video.videoWidth;
    const vh = video.videoHeight;
    if (!vw || !vh) return [];
    attempt += 1;
    const full = attempt % FULL_FRAME_EVERY === 0;
    // Полоса по центру — там, где рамка на экране.
    const sw = full ? vw : Math.round(vw * 0.9);
    const sh = full ? vh : Math.round(vh * 0.45);
    const scale = Math.min(1, BAND_MAX_WIDTH / sw);
    canvas.width = Math.round(sw * scale);
    canvas.height = Math.round(sh * scale);
    ctx.drawImage(video, (vw - sw) / 2, (vh - sh) / 2, sw, sh, 0, 0, canvas.width, canvas.height);
    const image = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const results = await zxing.readBarcodes(image, {
      formats: ZXING_FORMATS,
      tryHarder: full,
      tryRotate: full,
      tryInvert: false,
      tryDownscale: false,
      maxNumberOfSymbols: 1,
    });
    return results.filter((r) => r.isValid).map((r) => r.text || '');
  };
}

export default function WebScanner({ onClose }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [error, setError] = useState('');

  const finish = useCallback((detail) => {
    window.dispatchEvent(new CustomEvent('bonjour-scan', { detail }));
    onClose();
  }, [onClose]);

  useEffect(() => {
    let alive = true;
    const readerReady = makeReader().catch(() => {
      if (alive) setError('Не удалось загрузить распознавание штрихкодов. Введите номер бирки вручную.');
      return null;
    });

    navigator.mediaDevices
      .getUserMedia({
        // Full HD: по умолчанию Safari даёт 640×480, и штрихкод читается
        // только вплотную. Больше не нужно — 4K только замедлит распознавание.
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      })
      .then(async (stream) => {
        if (!alive) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const [track] = stream.getVideoTracks();
        // Непрерывный автофокус там, где браузер позволяет им управлять.
        try {
          if (track?.getCapabilities?.().focusMode?.includes('continuous')) {
            await track.applyConstraints({ advanced: [{ focusMode: 'continuous' }] });
          }
        } catch {
          // Не поддерживается — камера фокусируется сама.
        }
        const video = videoRef.current;
        if (!video) return;
        video.srcObject = stream;
        video.play().catch(() => {});
        const read = await readerReady;
        if (!read || !alive) return;

        const next = (fn) => (
          typeof video.requestVideoFrameCallback === 'function'
            ? video.requestVideoFrameCallback(() => fn())
            : requestAnimationFrame(() => fn())
        );
        const loop = async () => {
          if (!alive || !videoRef.current) return;
          try {
            const values = await read(videoRef.current);
            const value = values.find((v) => v.replace(/\D/g, '').length >= 14);
            if (value) {
              finish({ value, error: null, cancelled: false });
              return;
            }
          } catch {
            // Кадр мог не успеть отрисоваться — пробуем следующий.
          }
          next(loop);
        };
        next(loop);
      })
      .catch((err) => {
        if (!alive) return;
        setError(
          err?.name === 'NotAllowedError'
            ? 'Доступ к камере не разрешён. Разрешите его в настройках браузера или введите номер бирки вручную.'
            : 'Камера недоступна. Введите номер бирки вручную.',
        );
      });

    return () => {
      alive = false;
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, [finish]);

  return (
    <div className="web-scan" role="dialog" aria-label="Сканирование бирки">
      <button type="button" className="web-scan__close" onClick={onClose} aria-label="Закрыть">
        <X size={22} />
      </button>
      {error ? (
        <p className="web-scan__error">{error}</p>
      ) : (
        <>
          <video ref={videoRef} className="web-scan__video" muted playsInline />
          <div className="web-scan__frame" aria-hidden="true" />
          <p className="web-scan__hint">Наведите камеру на штрихкод бирки</p>
        </>
      )}
    </div>
  );
}
