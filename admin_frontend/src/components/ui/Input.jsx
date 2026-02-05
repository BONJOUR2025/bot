export default function Input({ label, helperText, className = '', ...props }) {
  return (
    <label className="flex w-full flex-col gap-1.5 text-sm text-[color:var(--color-text-muted)]">
      {label && <span className="font-medium text-[color:var(--color-text)]">{label}</span>}
      <input
        {...props}
        className={`w-full rounded-xl border border-[color:var(--color-control-border)] bg-[color:var(--color-control-bg)] px-3.5 py-2.5 text-sm text-[color:var(--color-text)] transition-all duration-150 placeholder:text-[color:var(--color-control-placeholder)] focus:border-[color:var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[color:var(--ring-color)] ${className}`.trim()}
      />
      {helperText && <span className="text-xs text-[color:var(--color-text-faint)]">{helperText}</span>}
    </label>
  );
}
