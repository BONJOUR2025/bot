import { useCallback, useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';

/** Сканер бирки камерой в браузере.
 *
 *  В приложении сканирует системный сканер Google (мост BonjourApp), у него и
 *  автофокус, и подсветка. В браузере такого нет, поэтому берём камеру через
 *  getUserMedia и распознаём встроенным BarcodeDetector (Chrome на Android).
 *  Там, где его нет — Safari, старые браузеры, — сканер не предлагается вовсе:
 *  кнопка, которая открывает чёрный прямоугольник, хуже ручного ввода.
 *
 *  Результат отдаётся тем же событием `bonjour-scan`, что и приложение, —
 *  страница «Скан» не знает, откуда пришла бирка. */

const FORMATS = ['code_128', 'code_39', 'code_93', 'itf', 'ean_13', 'codabar', 'qr_code'];

export function canScanInBrowser() {
  return (
    typeof window !== 'undefined' &&
    'BarcodeDetector' in window &&
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia
  );
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
    // eslint-disable-next-line no-undef
    const detector = new BarcodeDetector({ formats: FORMATS });

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
      .then((stream) => {
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
