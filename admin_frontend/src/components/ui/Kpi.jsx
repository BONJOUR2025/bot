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
  return (
    <div className={`ui-shell ui-shell--sm ${className}`.trim()} {...rest}>
      <div className="ui-core app-card p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="ui-label ui-label--fixed">{label}</div>
            <div className="ui-metric !text-[1.5rem] mt-1.5 truncate text-[color:var(--color-text)]">
              {value}
            </div>
            {sub && (
              <div className="mt-1.5 text-xs text-[color:var(--color-muted-foreground)]">{sub}</div>
            )}
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
      </div>
    </div>
  );
}
