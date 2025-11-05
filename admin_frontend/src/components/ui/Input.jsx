export default function Input({ label, helperText, className = '', ...props }) {
  return (
    <label className="flex w-full flex-col gap-1 text-sm text-[color:var(--muted-foreground)]">
      {label && <span className="font-medium text-[color:var(--foreground)]">{label}</span>}
      <input
        {...props}
        className={`w-full rounded-xl border border-border bg-[color:var(--color-input-background)] px-4 py-2.5 text-[color:var(--foreground)] shadow-sm transition focus-visible:border-[color:var(--color-sidebar-ring)] focus-visible:ring-2 focus-visible:ring-[color:var(--ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--background)] placeholder:text-[color:var(--muted-foreground)] ${className}`.trim()}
      />
      {helperText && <span className="text-xs text-[color:var(--muted-foreground)]">{helperText}</span>}
    </label>
  );
}
