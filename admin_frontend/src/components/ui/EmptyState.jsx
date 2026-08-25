import { Inbox } from 'lucide-react';

const KIND_CODE = {
  empty: 'Нет данных',
  loading: 'Загрузка',
  error: 'Данные недоступны',
};

/**
 * Состояние поверхности данных: пусто, загрузка, ошибка.
 *
 * Раньше это была отдельная композиция «иконка в кружке + заголовок +
 * подсказка», не связанная ни с чем в системе, а страницы вдобавок
 * писали свои пустые состояния голым текстом. Теперь компонент рисует
 * тот же операционный вид, что и таблицы (.fui-datastate): моношиный
 * код состояния, техническая черта, объяснение обычным текстом.
 *
 * Подпись состояния и формулировка разделены намеренно. Код («Нет
 * данных») говорит, ЧТО со стороны системы, и одинаков везде; title
 * остаётся тем, что написала страница («Работ за период нет»), поэтому
 * ни одна из трёх десятков точек вызова не переписывается.
 *
 * Иконка встала на место маркера состояния: она несёт смысл раздела,
 * а держать её в отдельном кружке над кодом значило бы городить пятый
 * ярус в блоке, который по смыслу должен быть тихим.
 */
export default function EmptyState({
  title = 'Нет данных',
  hint,
  icon: Icon = Inbox,
  action,
  compact = false,
  kind = 'empty',
  className = '',
}) {
  const code = KIND_CODE[kind] ?? KIND_CODE.empty;
  const showTitle = title && title !== code;

  return (
    <div
      className={`fui-datastate${kind !== 'empty' ? ` fui-datastate--${kind}` : ''}${
        compact ? ' fui-datastate--compact' : ''
      } ${className}`.trim()}
    >
      <span className="fui-datastate__code fui-datastate__code--icon">
        <Icon size={compact ? 13 : 14} strokeWidth={1.5} aria-hidden />
        {code}
      </span>
      <span className="fui-datastate__rule" />
      {showTitle && <span className="fui-datastate__title">{title}</span>}
      {hint && <span className="fui-datastate__text">{hint}</span>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
