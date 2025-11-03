export default function Button({ children, variant = 'primary', size = 'md', className = '', ...rest }) {
  const sizeClass = {
    sm: 'btn--sm',
    md: 'btn--md',
    lg: 'btn--lg',
  }[size] || 'btn--md';

  return (
    <button className={`btn btn--${variant} ${sizeClass} ${className}`.trim()} {...rest}>
      {children}
    </button>
  );
}

