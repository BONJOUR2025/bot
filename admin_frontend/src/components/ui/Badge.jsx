const toneClasses = {
  neutral:  'bg-[color:var(--color-control-bg)] text-[color:var(--color-text-muted)]',
  info:     'bg-[color:var(--color-info-muted)] text-[color:var(--color-info)]',
  success:  'bg-[color:var(--color-success-muted)] text-[color:var(--color-success)]',
  warning:  'bg-[color:var(--color-warning-muted)] text-[color:var(--color-warning)]',
  danger:   'bg-[color:var(--color-danger-muted)] text-[color:var(--color-danger)]',
  primary:  'bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)]',
};

export default function Badge({ children, tone = 'neutral', className = '', style }) {
  const cls = toneClasses[tone] || toneClasses.neutral;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold tracking-wide ${cls} ${className}`.trim()}
      style={style}
    >
      {children}
    </span>
  );
}
