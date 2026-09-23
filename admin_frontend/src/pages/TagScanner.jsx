import { useEffect, useRef, useState } from 'react';
import { ScanBarcode } from 'lucide-react';
import { OrderSearch, OrderView } from './employee/WorkshopOrder.jsx';

/** Сканер бирок: бирка → вся карточка заказа (GET /api/workshop/orders/*).
 *
 *  Тот же поиск и та же карточка, что во вкладке «Цех», но без обзора цеха:
 *  экран для стойки с ручным сканером. Сканер печатает бирку как клавиатура
 *  и жмёт Enter, поэтому поле ввода держим наготове — даже если перед этим
 *  щёлкнули по фото или карточке, первая цифра бирки вернёт фокус в поле.
 *  Услуга, чья это бирка, в карточке подсвечена. */

function isEditable(el) {
  return !!el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
}

export default function TagScanner() {
  const inputRef = useRef(null);
  const [found, setFound] = useState(null);

  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey || !/^\d$/.test(e.key)) return;
      if (isEditable(document.activeElement) || document.body.classList.contains('photo-open')) return;
      const input = inputRef.current;
      if (!input) return;
      // Фокус переводим до того, как браузер вставит символ, — цифра
      // попадёт уже в поле и заменит выделенную прежнюю бирку.
      input.focus();
      input.select();
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, []);

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-12">
      <div>
        <span className="ui-eyebrow mb-3">Цех</span>
        <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)]">
          Сканер бирок
        </h2>
        <p className="text-sm text-[color:var(--color-muted-foreground)] mt-2 max-w-[62ch]">
          Отсканируйте бирку ручным сканером или камерой — откроется весь заказ: изделия, фото, услуги,
          входы и выходы мастеров, комментарии и накладные. Номер заказа тоже подойдёт.
        </p>
      </div>

      <OrderSearch
        inputRef={inputRef}
        scanMode
        onOpen={(orderId, serviceId) => setFound({ orderId, serviceId, at: Date.now() })}
      />

      {found ? (
        <OrderView key={`${found.orderId}-${found.at}`} orderId={found.orderId} highlightServiceId={found.serviceId} />
      ) : (
        <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]">
          <ScanBarcode size={28} className="mx-auto mb-2 opacity-60" />
          Отсканируйте бирку — заказ откроется здесь
        </div>
      )}
    </div>
  );
}
