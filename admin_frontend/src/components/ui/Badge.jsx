export default function Badge({ children, tone = 'neutral', style }) {
  const paletteMap = {
    neutral: { background: 'rgba(255, 255, 255, 0.08)', color: 'var(--color-text)' },
    success: { background: 'rgba(62, 207, 142, 0.15)', color: 'var(--color-success)' },
    warning: { background: 'rgba(249, 185, 90, 0.15)', color: 'var(--color-warning)' },
    danger: { background: 'rgba(255, 107, 107, 0.15)', color: 'var(--color-danger)' },
    info: { background: 'rgba(61, 213, 243, 0.16)', color: 'var(--color-accent)' },
  };
  const palette = paletteMap[tone] || paletteMap.neutral;

  return (
    <span className="badge" style={{ ...palette, ...style }}>
      {children}
    </span>
  );
}

