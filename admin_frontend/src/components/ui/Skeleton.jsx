export default function Skeleton({ className = '', style, variant = 'text' }) {
  const variantClass =
    variant === 'title' ? 'skeleton-title' :
    variant === 'card'  ? 'skeleton-card' :
    'skeleton-text';

  return <div className={`skeleton ${variantClass} ${className}`} style={style} />;
}

export function SkeletonCard() {
  return (
    <div className="app-card" style={{ gap: '1rem' }}>
      <Skeleton variant="title" />
      <Skeleton />
      <Skeleton style={{ width: '80%' }} />
    </div>
  );
}

/**
 * Заглушка под ряд карточек-показателей.
 *
 * Нужна там, где раньше стояло центрированное «Загрузка…»: текст занимал
 * одну строку, а приходящий на его место блок — несколько сотен пикселей,
 * поэтому страница подпрыгивала в момент загрузки. Заглушка держит
 * примерно ту же высоту и ту же сетку, что и реальные карточки.
 */
export function SkeletonStats({ count = 4 }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="ui-shell ui-shell--sm">
          <div className="ui-core app-card p-5">
            <Skeleton style={{ width: '55%', height: '0.7rem' }} />
            <Skeleton style={{ width: '75%', height: '1.5rem', marginTop: '0.75rem' }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="flex gap-4">
          {Array.from({ length: cols }, (_, c) => (
            <Skeleton key={c} style={{ flex: 1 }} />
          ))}
        </div>
      ))}
    </div>
  );
}
