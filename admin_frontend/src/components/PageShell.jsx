function cx(...args) {
  return args
    .flatMap((arg) => {
      if (!arg) return [];
      if (typeof arg === 'string') return [arg];
      if (typeof arg === 'object') {
        return Object.entries(arg)
          .filter(([, value]) => Boolean(value))
          .map(([key]) => key);
      }
      return [];
    })
    .join(' ');
}

export function PageShell({ title, subtitle, actions, badge, children, className }) {
  return (
    <div className={cx('page-shell', className)}>
      <div className="page-hero">
        <div className="page-hero__meta">
          {badge && <span className="pill pill--accent">{badge}</span>}
          <div className="page-hero__titles">
            <h1>{title}</h1>
            {subtitle && <p className="page-hero__subtitle">{subtitle}</p>}
          </div>
        </div>
        {actions && <div className="page-hero__actions">{actions}</div>}
      </div>
      <div className="page-shell__content">{children}</div>
    </div>
  );
}

export function PageSection({ title, description, actions, children, columns = 1, bleed = false }) {
  const bodyClass = cx('page-section__body', {
    'page-section__body--grid': columns && columns > 1,
    'page-section__body--bleed': bleed,
  });

  return (
    <section className="page-section">
      {(title || description || actions) && (
        <div className="page-section__header">
          <div className="page-section__titles">
            {title && <h2>{title}</h2>}
            {description && <p className="page-section__description">{description}</p>}
          </div>
          {actions && <div className="page-section__actions">{actions}</div>}
        </div>
      )}
      <div className={bodyClass} style={{ '--columns': columns }}>
        {children}
      </div>
    </section>
  );
}

export function GlassPanel({ tone = 'default', padded = true, className, children }) {
  return (
    <div
      className={cx(
        'glass-panel',
        `glass-panel--${tone}`,
        { 'glass-panel--padded': padded },
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Toolbar({ children, align = 'start' }) {
  return <div className={cx('page-toolbar', `page-toolbar--${align}`)}>{children}</div>;
}

export function StatGrid({ children }) {
  return <div className="page-stat-grid">{children}</div>;
}

export function StatCard({ title, value, hint, icon }) {
  return (
    <div className="stat-card stat-card--glow">
      <div className="stat-card__icon">{icon}</div>
      <div>
        <div className="stat-card__label">{title}</div>
        <div className="stat-card__value">{value}</div>
        {hint && <div className="stat-card__hint">{hint}</div>}
      </div>
    </div>
  );
}

