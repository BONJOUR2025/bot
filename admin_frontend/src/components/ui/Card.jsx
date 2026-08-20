/**
 * Карточка — базовая поверхность приложения.
 *
 * Рендерит вложенную пару .ui-shell > .ui-core (оболочка и ядро). В теме
 * Ethereal Glass это даёт двойной безель: полупрозрачная оболочка с
 * волосяной рамкой и непрозрачное ядро с подсветкой верхней кромки, радиусы
 * концентрические. В остальных темах обе обёртки — display:contents, то есть
 * пропадают из раскладки, и карточка выглядит ровно как раньше.
 *
 * Поэтому здесь нет ни одной проверки текущей темы: разметка одна на все три
 * мира, разводит их CSS.
 */
export default function Card({
  title,
  description,
  actions,
  children,
  className = '',
  bodyClassName = '',
  /** Убрать внутренние отступы у тела — для таблиц и медиа во всю карточку. */
  flush = false,
  /** Компактный радиус: мелкие блоки, где 32px читаются пузырём. */
  compact = false,
  style,
  ...rest
}) {
  const hasHeader = Boolean(title || description || actions);

  return (
    <div
      className={`ui-shell ${compact ? 'ui-shell--sm' : ''} ${className}`.trim()}
      style={style}
      {...rest}
    >
      <section className="ui-core rounded-[var(--ui-radius-card)] border border-[color:var(--color-border)] bg-[color:var(--color-surface)] shadow-[var(--ui-shadow-card)] backdrop-blur-[var(--ui-blur)] transition-shadow duration-200 hover:shadow-[var(--ui-shadow-card-hover)]">
        {hasHeader && (
          <header className="flex flex-col gap-2 border-b border-[color:var(--color-border)] px-6 pb-4 pt-6 sm:flex-row sm:items-start sm:justify-between">
            <div className="space-y-1">
              {title && (
                <h3 className="text-lg font-semibold leading-tight text-[color:var(--color-text)]">
                  {title}
                </h3>
              )}
              {description && (
                <p className="text-sm text-[color:var(--color-text-muted)]">{description}</p>
              )}
            </div>
            {actions && <div className="flex items-center gap-2">{actions}</div>}
          </header>
        )}
        <div className={`${flush ? '' : 'space-y-4 px-6 py-5'} ${bodyClassName}`.trim()}>
          {children}
        </div>
      </section>
    </div>
  );
}
