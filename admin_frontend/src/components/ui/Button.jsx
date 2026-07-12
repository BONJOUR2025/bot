const variantClasses = {
  primary:
    'border-transparent bg-[color:var(--color-primary)] text-white shadow-[var(--ui-shadow-card)] hover:bg-[color:var(--color-primary-hover)]',
  secondary:
    'border-[color:var(--color-border)] bg-[color:var(--color-control-bg)] text-[color:var(--color-text)] hover:border-[color:var(--color-border-hover)]',
  outline:
    'border-[color:var(--color-border)] bg-transparent text-[color:var(--color-text)] hover:bg-[color:var(--color-control-bg)]',
  ghost:
    'border-transparent bg-transparent text-[color:var(--color-text-muted)] hover:bg-[color:var(--color-control-bg)] hover:text-[color:var(--color-text)]',
  destructive:
    'border-transparent bg-[color:var(--color-danger)] text-white shadow-[var(--ui-shadow-card)] hover:brightness-110',
  subtle:
    'border-transparent bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] hover:brightness-125',
  success:
    'border-transparent bg-[color:var(--color-success)] text-white shadow-[var(--ui-shadow-card)] hover:brightness-110',
};

const sizeClasses = {
  sm: 'h-9 px-3 text-xs',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-6 text-base',
};

export default function Button({ children, variant = 'primary', size = 'md', className = '', ...rest }) {
  const base =
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[var(--ui-radius-btn)] border font-medium transition-all duration-150 hover:-translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ring-color)] focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50';
  const v = variantClasses[variant] || variantClasses.primary;
  const s = sizeClasses[size] || sizeClasses.md;

  return (
    <button className={`${base} ${v} ${s} ${className}`.trim()} {...rest}>
      {children}
    </button>
  );
}
