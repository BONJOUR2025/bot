/* Подготовка значения и его длина — в общем модуле: дашборд рисует
   показатели другой композицией, но подгонять число под ширину прибора
   обе композиции обязаны одинаково. */
import { breakableNumber, metricLen } from '../../utils/metricValue.js';

/**
 * Карточка показателя.
 *
 * До этого её определение было скопировано в пяти страницах байт в байт
 * (Employees, Payouts, PayoutsControl, Incentives, CashMovements) и ещё в
 * трёх — с расхождениями. Из-за этого одинаковые по смыслу блоки
 * разъезжались: где-то цифра была жирной, где-то нет, где-то у карточки
 * была цветная кромка слева.
 *
 * `accent` задаёт принадлежность к разделу отчёта, а не оценку значения,
 * поэтому красит иконку и её подложку, но не саму цифру. Раскрашенное
 * значение читается как вердикт («красное — плохо»), хотя accent обычно
 * означает всего лишь «это про кассу» или «это про выплаты».
 */
export default function Kpi({
  label,
  value,
  sub,
  accent = 'var(--color-primary)',
  icon: Icon,
  className = '',
  ...rest
}) {
  const display = breakableNumber(value);
  /* Длина значения в символах — единственное, чего не хватает CSS, чтобы
     самому подобрать кегль под ширину карточки. Шрифт значения моно-
     ширинный (Geist Mono), у него ширина символа строго пропорциональна
     кеглю (замерено: 0.59 × font-size), так что длины достаточно —
     измерять текст в JS не нужно. Дальше всё делает clamp() с cqw
     (см. .ui-metric--kpi): кегль ужимается ровно настолько, чтобы сумма
     осталась в одну строку, и упирается в прежние 1.5rem там, где место
     есть, — то есть на десктопе вид не меняется. */
  const len = metricLen(display);

  return (
    <div className={`ui-shell ui-shell--sm ${className}`.trim()} {...rest}>
      <div className="ui-core app-card p-5">
        {/* Иконку делит строка только с подписью, а не со значением.
            Раньше значение лежало в той же колонке, что и подпись, и на
            узком экране (две карточки в ряд на 375px) на него оставалось
            46px из 94px — сумма рвалась посреди числа. Иконка занимает
            место лишь на высоте подписи, ниже карточка всё равно пустая,
            поэтому значение и нижняя подпись занимают всю ширину.
            min-h-9 = высота иконки: гарантирует, что значение начинается
            под ней, а не наезжает. На десктопе вид не меняется. */}
        <div className="flex min-h-9 items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="ui-label ui-label--fixed">{label}</div>
          </div>
          {Icon && (
            <span
              className="grid h-9 w-9 shrink-0 place-items-center rounded-full"
              style={{
                color: accent,
                background: `color-mix(in oklab, ${accent} 12%, transparent)`,
              }}
            >
              <Icon size={18} strokeWidth={1.4} />
            </span>
          )}
        </div>
        {/* Обёртка нужна только как container для cqw: элемент не может
            спросить свою же ширину, ему нужен контейнер-родитель. */}
        <div className="ui-metric-fit mt-1.5">
          <div
            className="ui-metric ui-metric--kpi text-[color:var(--color-text)]"
            style={len ? { '--kpi-len': len } : undefined}
          >
            {display}
          </div>
        </div>
        {sub && (
          <div className="mt-1.5 text-xs text-[color:var(--color-muted-foreground)]">{sub}</div>
        )}
      </div>
    </div>
  );
}
