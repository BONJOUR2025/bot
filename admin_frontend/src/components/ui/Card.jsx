export default function Card({ title, description, actions, children, className = '', style, ...rest }) {
  return (
    <section
      className={`rounded-2xl border border-border bg-[color:var(--card)] text-[color:var(--card-foreground)] shadow-sm transition-shadow duration-150 hover:shadow-md ${className}`.trim()}
      style={style}
      {...rest}
    >
      {(title || description || actions) && (
        <header className="flex flex-col gap-2 border-b border-border px-6 pb-4 pt-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            {title && <h3 className="text-lg font-semibold leading-tight">{title}</h3>}
            {description && <p className="text-sm text-[color:var(--muted-foreground)]">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="space-y-4 px-6 py-5">{children}</div>
    </section>
  );
}
