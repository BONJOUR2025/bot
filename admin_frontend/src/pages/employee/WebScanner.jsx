import { useCallback, useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';

/** Сканер бирки камерой в браузере.
 *
 *  В приложении сканирует системный сканер Google (мост BonjourApp), у него и
 *  автофокус, и подсветка. В браузере камеру берём через getUserMedia, а
 *  распознаём встроенным BarcodeDetector, если он есть и умеет Code 128
 *  (Chrome на Android и macOS). Во всех остальных браузерах — Safari на
 *  iPhone, Chrome на Windows, Firefox — встроенного распознавания нет, и
 *  раньше кнопка скана там не показывалась вовсе: веб-версия умела только
 *  ручной ввод. Теперь там работает ZXing, собранный в WebAssembly. Он весит
 *  около мегабайта и грузится с нашего сервера только при открытии сканера.
 *
 *  Результат отдаётся тем же событием `bonjour-scan`, что и приложение, —
 *  страница «Скан» не знает, откуда пришла бирка. */

const FORMATS = ['code_128', 'code_39', 'code_93', 'itf', 'ean_13', 'codabar', 'qr_code'];

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
    const formats = FORMATS.filter((f) => supported.includes(f));
    return formats.includes('code_128') ? new window.BarcodeDetector({ formats }) : null;
  } catch {
    return null;
  }
}

let zxingReady = null;
async function zxingDetector() {
  const [{ BarcodeDetector, prepareZXingModule }, { default: wasmUrl }] = await Promise.all([
    import('barcode-detector/ponyfill'),
    import('zxing-wasm/reader/zxing_reader.wasm?url'),
  ]);
  if (!zxingReady) {
    // Без этого библиотека тянет .wasm с jsDelivr: лишняя внешняя
    // зависимость у экрана, которым мастер пользуется весь день.
    prepareZXingModule({
      overrides: { locateFile: (path, prefix) => (path.endsWith('.wasm') ? wasmUrl : prefix + path) },
    });
    zxingReady = true;
  }
  return new BarcodeDetector({ formats: FORMATS });
}

export default function WebScanner({ onClose }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const [error, setError] = useState('');

  const finish = useCallback((detail) => {
    window.dispatchEvent(new CustomEvent('bonjour-scan', { detail }));
    onClose();
  }, [onClose]);

  useEffect(() => {
    let alive = true;
    let detector = null;
    const detectorReady = nativeDetector()
      .then((d) => d || zxingDetector())
      .then((d) => { detector = d; })
      .catch(() => {
        if (alive) setError('Не удалось загрузить распознавание штрихкодов. Введите номер бирки вручную.');
      });

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
      .then(async (stream) => {
        await detectorReady;
        if (!alive) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const video = videoRef.current;
        if (!video) return;
        video.srcObject = stream;
        video.play().catch(() => {});
        const tick = async () => {
          if (!alive || !videoRef.current) return;
          if (!detector) return;
          try {
            const codes = await detector.detect(videoRef.current);
            const value = codes.find((c) => (c.rawValue || '').replace(/\D/g, '').length >= 14)?.rawValue;
            if (value) {
              finish({ value, error: null, cancelled: false });
              return;
            }
          } catch {
            // Кадр мог не успеть отрисоваться — пробуем следующий.
          }
          timerRef.current = setTimeout(tick, 250);
        };
        tick();
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
      clearTimeout(timerRef.current);
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
