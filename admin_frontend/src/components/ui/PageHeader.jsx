/**
 * Шапка страницы: надзаголовок, крупный заголовок, подпись и кнопки действий.
 *
 * Единый блок вместо того, чтобы каждая из 40+ страниц собирала свой из
 * «h2.text-2xl + div с кнопками». Даёт одинаковый ритм и, главное, одинаковую
 * иерархию: сначала контекст (надзаголовок), потом название, потом пояснение.
 *
 * `eyebrow` — короткий контекст, который сообщает что-то настоящее: период
 * отчёта, количество записей, источник данных. Не украшение: если сказать
 * нечего, его лучше не передавать вовсе.
 */
export default function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className = '',
  ...rest
}) {
  return (
    <div
      className={`ui-reveal mb-8 flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between ${className}`.trim()}
      {...rest}
    >
      <div className="min-w-0 max-w-[64ch]">
        {eyebrow && <span className="ui-eyebrow mb-4">{eyebrow}</span>}
        <h1 className="text-2xl font-semibold leading-tight text-[color:var(--color-text)] sm:text-[2.6rem]">
          {title}
        </h1>
        {description && (
          <p className="mt-3 max-w-[56ch] text-sm text-[color:var(--color-text-muted)] sm:text-[15px]">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
