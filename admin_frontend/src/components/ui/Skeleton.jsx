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
