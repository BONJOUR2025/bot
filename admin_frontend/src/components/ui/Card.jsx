export default function Card({ title, description, actions, children, className = '', style, ...rest }) {
  return (
    <section className={`app-card ${className}`.trim()} style={style} {...rest}>
      {(title || description || actions) && (
        <header className="app-card__header">
          <div>
            {title && <h3 className="app-card__title">{title}</h3>}
            {description && <p className="app-card__description">{description}</p>}
          </div>
          {actions && <div className="app-card__actions">{actions}</div>}
        </header>
      )}
      <div className="app-card__body">{children}</div>
    </section>
  );
}

