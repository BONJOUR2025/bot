import Card from './Card.jsx';

const deltaTone = {
  up: 'text-[color:var(--color-success)]',
  down: 'text-[color:var(--color-danger)]',
  flat: 'text-[color:var(--color-text-muted)]',
};

/**
 * Показатель: подпись, крупное число, изменение к прошлому периоду.
 *
 * Сводка должна читаться раньше детали, поэтому число набрано моноширинным
 * начертанием с табличными цифрами (.ui-metric) — в ряду из нескольких
 * карточек разряды выстраиваются по вертикали и величины сравниваются
 * взглядом, без чтения.
 *
 * `direction` описывает направление изменения, а не его оценку: падение
 * расходов — это тоже 'down', но зелёное. Поэтому цвет берётся из `tone`,
 * если он задан, и только иначе выводится из направления.
 */
export default function Stat({
  label,
  value,
  delta,
  direction = 'flat',
  tone,
  hint,
  children,
  className = '',
  ...rest
}) {
  const toneCls = deltaTone[tone || direction] || deltaTone.flat;

  return (
    <Card compact className={`ui-reveal ${className}`.trim()} {...rest}>
      <span className="ui-label block">{label}</span>
      <div className="ui-metric mt-3 text-[color:var(--color-text)]">{value}</div>
      {delta && <div className={`mt-2 text-xs font-medium ${toneCls}`}>{delta}</div>}
      {hint && <div className="mt-1 text-xs text-[color:var(--color-text-faint)]">{hint}</div>}
      {children}
    </Card>
  );
}
