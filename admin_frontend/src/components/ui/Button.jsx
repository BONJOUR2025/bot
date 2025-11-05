const baseClasses =
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg border font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--background)] disabled:pointer-events-none disabled:opacity-50';

const variantClasses = {
  primary:
    'border-transparent bg-[color:var(--primary)] text-[color:var(--primary-foreground)] shadow-sm hover:-translate-y-0.5 hover:shadow-md hover:brightness-110',
  secondary:
    'border-transparent bg-[color:var(--secondary)] text-[color:var(--secondary-foreground)] hover:-translate-y-0.5 hover:brightness-105',
  outline:
    'border border-border bg-[color:var(--background)] text-[color:var(--foreground)] hover:bg-[color:var(--accent)] hover:text-[color:var(--accent-foreground)]',
  ghost:
    'border-transparent bg-transparent text-[color:var(--muted-foreground)] hover:bg-[color:var(--accent)] hover:text-[color:var(--accent-foreground)]',
  destructive:
    'border-transparent bg-[color:var(--destructive)] text-[color:var(--destructive-foreground)] hover:-translate-y-0.5 hover:brightness-110',
  subtle:
    'border-transparent bg-[color:var(--muted)] text-[color:var(--muted-foreground)] hover:bg-[color:var(--accent)] hover:text-[color:var(--accent-foreground)]',
};

const sizeClasses = {
  sm: 'h-9 px-3 text-xs',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-6 text-base',
};

export default function Button({ children, variant = 'primary', size = 'md', className = '', ...rest }) {
  const variantClass = variantClasses[variant] || variantClasses.primary;
  const sizeClass = sizeClasses[size] || sizeClasses.md;

  return (
    <button className={`${baseClasses} ${variantClass} ${sizeClass} ${className}`.trim()} {...rest}>
      {children}
    </button>
  );
}
