import { Inbox } from 'lucide-react';

/**
 * Состояние пустоты.
 *
 * До этого по страницам было раскидано 54 повтора строки «Нет данных».
 * Она не отвечает ни на один вопрос, который в этот момент возникает:
 * данных нет вообще, или их отсеяли фильтры, или период выбран не тот,
 * или что-то нужно сначала завести. Поэтому здесь два уровня текста:
 * `title` называет факт, `hint` объясняет причину или следующий шаг.
 *
 * `action` — кнопка, если из этого места действительно можно что-то
 * сделать (завести первую запись, сбросить фильтры). Если сделать
 * нечего, кнопку лучше не показывать, чем показывать неработающую.
 */
export default function EmptyState({
  title = 'Нет данных',
  hint,
  icon: Icon = Inbox,
  action,
  compact = false,
  className = '',
}) {
  return (
    <div
      className={`flex flex-col items-center justify-center text-center ${
        compact ? 'gap-2 py-6' : 'gap-3 py-12'
      } ${className}`.trim()}
    >
      <span
        className={`grid place-items-center rounded-full border border-[color:var(--color-border)] bg-[color:var(--color-control-bg)] text-[color:var(--color-text-faint)] ${
          compact ? 'h-9 w-9' : 'h-12 w-12'
        }`}
      >
        <Icon size={compact ? 16 : 20} strokeWidth={1.3} />
      </span>
      <div>
        <div
          className={`font-medium text-[color:var(--color-text-muted)] ${
            compact ? 'text-sm' : 'text-[15px]'
          }`}
        >
          {title}
        </div>
        {hint && (
          <div className="mx-auto mt-1 max-w-[46ch] text-xs text-[color:var(--color-text-faint)]">
            {hint}
          </div>
        )}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
