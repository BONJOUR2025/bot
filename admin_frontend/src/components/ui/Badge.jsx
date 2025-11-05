const palette = {
  neutral: {
    backgroundColor: 'var(--muted)',
    background: 'color-mix(in srgb, var(--muted) 40%, transparent)',
    color: 'var(--muted-foreground)',
  },
  info: {
    backgroundColor: 'var(--accent)',
    background: 'color-mix(in srgb, var(--accent) 38%, transparent)',
    color: 'var(--accent-foreground)',
  },
  success: {
    backgroundColor: 'var(--chart-2)',
    background: 'color-mix(in srgb, var(--chart-2) 30%, transparent)',
    color: 'var(--chart-2)',
  },
  warning: {
    backgroundColor: 'var(--chart-4)',
    background: 'color-mix(in srgb, var(--chart-4) 32%, transparent)',
    color: 'var(--chart-4)',
  },
  danger: {
    backgroundColor: 'var(--destructive)',
    background: 'color-mix(in srgb, var(--destructive) 32%, transparent)',
    color: 'var(--destructive)',
  },
};

export default function Badge({ children, tone = 'neutral', className = '', style }) {
  const colors = palette[tone] || palette.neutral;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium tracking-wide ${className}`.trim()}
      style={{ ...colors, ...style }}
    >
      {children}
    </span>
  );
}
