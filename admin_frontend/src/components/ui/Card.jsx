export default function Card({ title, description, actions, children, className = '', style, ...rest }) {
  return (
    <section
      className={`rounded-[var(--ui-radius-card)] border border-[color:var(--color-border)] bg-[color:var(--color-surface)] shadow-[var(--ui-shadow-card)] backdrop-blur-[var(--ui-blur)] transition-shadow duration-200 hover:shadow-[var(--ui-shadow-card-hover)] ${className}`.trim()}
      style={style}
      {...rest}
    >
      {(title || description || actions) && (
        <header className="flex flex-col gap-2 border-b border-[color:var(--color-border)] px-6 pb-4 pt-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            {title && <h3 className="text-lg font-semibold leading-tight text-[color:var(--color-text)]">{title}</h3>}
            {description && <p className="text-sm text-[color:var(--color-text-muted)]">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="space-y-4 px-6 py-5">{children}</div>
    </section>
  );
}
