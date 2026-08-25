import { useCallback, useEffect, useRef, useState } from 'react';
import { useViewport } from '../../providers/ViewportProvider.jsx';
import EmptyState from './EmptyState.jsx';

/**
 * columns: Array of:
 *   { label, key, render, headerClass, cellClass, mobileHide, isAction, primary,
 *     numeric, status }
 *
 * - label:       column header text
 * - key:         row[key] fallback if no render
 * - render:      (row) => ReactNode
 * - mobileHide:  hide this column in card mode
 * - isAction:    renders at the bottom of the card (buttons)
 * - primary:     renders as card title (bold, top)
 * - numeric:     величина, а не текст — моноширинный набор, табличные
 *                цифры, выключка вправо. Раньше каждая страница
 *                описывала это сама: из 24 денежных колонок только семь
 *                имели tabular-nums, и разряды в соседних строках не
 *                выстраивались.
 * - status:      ячейка состояния (не переносится)
 *
 * rowState: (row) => 'selected' | 'active' | 'warning' | 'error' | 'disabled'
 *   Роль строки вместо самодельной раскраски. Страницы задавали её
 *   классами вроде bg-amber-50/60 и bg-red-50 — светлыми литералами,
 *   которые в тёмной теме давали белёсую строку (глобальный патч ловит
 *   bg-amber-50, но не bg-amber-50/60 с прозрачностью).
 *
 * updatedKey: (row) => any
 *   Значение-отпечаток строки. Когда оно меняется, по строке один раз
 *   проходит подсветка: данные обновились. Ни одной бесконечной
 *   анимации — сто строк остаются статичными.
 */
const ROW_STATES = new Set(['selected', 'active', 'warning', 'error', 'disabled']);

/** Одноразовая подсветка строк, чьи данные изменились между рендерами. */
function useUpdatedRows(data, keyFn, updatedKey) {
  const prev = useRef(null);
  const [hot, setHot] = useState(() => new Set());

  useEffect(() => {
    if (!updatedKey) return undefined;
    const now = new Map(data.map((r) => [keyFn(r), updatedKey(r)]));
    if (prev.current) {
      const changed = new Set();
      now.forEach((v, k) => {
        if (prev.current.has(k) && prev.current.get(k) !== v) changed.add(k);
      });
      if (changed.size) {
        setHot(changed);
        // Подсветка живёт ровно столько, сколько анимация, и снимается:
        // класс, оставшийся на строке, превратил бы разовое событие в
        // постоянное состояние.
        const t = setTimeout(() => setHot(new Set()), 1000);
        prev.current = now;
        return () => clearTimeout(t);
      }
    }
    prev.current = now;
    return undefined;
  }, [data, keyFn, updatedKey]);

  return hot;
}

/**
 * Горизонтальная прокрутка таблицы обозначается растворением края —
 * тем же приёмом, что у ленты этапов в подборе персонала. Класс
 * вешается только с той стороны, куда действительно можно прокрутить.
 */
function useEdgeFade() {
  const ref = useRef(null);
  const [edge, setEdge] = useState({ left: false, right: false });

  const sync = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    setEdge({
      left: el.scrollLeft > 4,
      right: el.scrollLeft + el.clientWidth < el.scrollWidth - 4,
    });
  }, []);

  useEffect(() => {
    sync();
    const el = ref.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => ro.disconnect();
  }, [sync]);

  return { ref, edge, sync };
}

/** Пусто / загрузка / ошибка — один операционный вид на три случая. */
function DataState({ kind, title, text, action }) {
  return (
    <div className={`fui-datastate${kind ? ` fui-datastate--${kind}` : ''}`}>
      <span className="fui-datastate__code">{title}</span>
      <span className="fui-datastate__rule" />
      {text && <span className="fui-datastate__text">{text}</span>}
      {action}
    </div>
  );
}

export default function ResponsiveTable({
  columns,
  data,
  keyFn,
  rowClass,
  rowState,
  updatedKey,
  loading = false,
  error = null,
  onRetry,
  emptyText = 'Нет данных',
  /** Вторая строка: почему пусто и что делать. См. EmptyState. */
  emptyHint,
  emptyIcon,
  emptyAction,
}) {
  const { isMobile } = useViewport();
  const hot = useUpdatedRows(data, keyFn, updatedKey);
  const { ref: scrollRef, edge, sync } = useEdgeFade();

  const stateOf = (row) => {
    const s = rowState?.(row);
    return s && ROW_STATES.has(s) ? s : null;
  };
  const rowCls = (row) => {
    const s = stateOf(row);
    return [
      'fui-row',
      s ? `fui-row--${s}` : '',
      hot.has(keyFn(row)) ? 'fui-row--updated' : '',
      rowClass?.(row) || '',
    ].filter(Boolean).join(' ');
  };
  const cellCls = (col) => [
    col.numeric ? 'fui-cell--numeric' : '',
    col.status ? 'fui-cell--status' : '',
    col.isAction ? 'fui-cell--action' : '',
    col.cellClass || '',
  ].filter(Boolean).join(' ');

  if (loading) {
    return (
      <DataState
        kind="loading"
        title="Загрузка"
        text="Данные запрошены, ожидается ответ источника"
      />
    );
  }
  if (error) {
    return (
      <DataState
        kind="error"
        title="Ошибка канала данных"
        text={typeof error === 'string' ? error : 'Не удалось получить данные'}
        action={
          onRetry ? (
            <button
              type="button"
              onClick={onRetry}
              className="fui-press mt-1 inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-[color:var(--color-border)] px-4 text-sm text-[color:var(--color-text)] transition-colors hover:bg-[color:var(--color-control-bg-hover)]"
            >
              Повторить
            </button>
          ) : null
        }
      />
    );
  }

  if (isMobile) {
    if (data.length === 0) {
      return (
        <EmptyState title={emptyText} hint={emptyHint} icon={emptyIcon} action={emptyAction} />
      );
    }

    return (
      <div className="space-y-3">
        {data.map((row) => {
          const primaryCol = columns.find((c) => c.primary);
          const actionCol = columns.find((c) => c.isAction);
          const bodyColumns = columns.filter((c) => !c.mobileHide && !c.isAction && !c.primary);

          return (
            <div
              key={keyFn(row)}
              className={`overflow-hidden rounded-[var(--ui-radius-card)] border border-[color:var(--color-border)] bg-[color:var(--color-table-bg)] shadow-[var(--ui-shadow-table)] ${rowCls(row)}`}
            >
              {primaryCol && (
                <div className="border-b border-[color:var(--color-border)] bg-[color:var(--color-table-header)] px-4 py-3 text-sm font-medium text-[color:var(--color-text-primary)]">
                  {primaryCol.render ? primaryCol.render(row) : row[primaryCol.key]}
                </div>
              )}
              <div className="space-y-1.5 px-4 py-2">
                {bodyColumns.map((col, ci) => (
                  <div key={col.key ?? ci} className="flex items-start justify-between gap-2 text-sm">
                    <span className="shrink-0 text-[color:var(--color-muted-foreground)]">{col.label}</span>
                    <span
                      className={`text-right text-[color:var(--color-text-primary)] ${
                        col.numeric ? 'fui-cell--numeric' : ''
                      }`}
                    >
                      {col.render ? col.render(row) : row[col.key] ?? '—'}
                    </span>
                  </div>
                ))}
              </div>
              {actionCol && (
                <div className="flex min-w-0 justify-end gap-2 border-t border-[color:var(--color-border)] px-4 py-2">
                  {actionCol.render(row)}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    /* Рамка и скругление — на внешнем узле, прокрутка и растворение
       края — на внутреннем. Если растворять край на том же элементе,
       что несёт рамку, маска гасит и её: у таблицы пропадали бы углы. */
    <div className="overflow-hidden rounded-[var(--ui-radius-card)] border border-[color:var(--color-border)] bg-[color:var(--color-table-bg)] shadow-[var(--ui-shadow-table)]">
      <div
        ref={scrollRef}
        onScroll={sync}
        className={`overflow-auto ui-hscroll${edge.left ? ' is-fade-left' : ''}${edge.right ? ' is-fade-right' : ''}`}
      >
        {/* overflow-visible: global `table { overflow: hidden }` (globals.css) clips any sticky
            column a caller adds via headerClass/cellClass once horizontal scroll moves it away
            from its natural position. The wrapping div's overflow-auto still clips to the
            rounded corners, so this doesn't affect the visual rounding. */}
        <table className="w-full min-w-max overflow-visible text-sm text-[color:var(--color-table-text)]">
          <thead className="fui-thead bg-[color:var(--color-table-header)]">
            <tr>
              {columns.map((col, ci) => (
                <th
                  key={col.key ?? ci}
                  className={`whitespace-nowrap p-2 text-left ${col.numeric ? 'text-right' : ''} ${col.headerClass || ''}`}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[color:var(--color-border)]">
            {data.map((row) => (
              <tr key={keyFn(row)} className={rowCls(row)}>
                {columns.map((col, ci) => (
                  <td key={col.key ?? ci} className={`p-2 ${cellCls(col)}`}>
                    {col.render ? col.render(row) : row[col.key] ?? ''}
                  </td>
                ))}
              </tr>
            ))}
            {data.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="p-0">
                  <EmptyState
                    title={emptyText}
                    hint={emptyHint}
                    icon={emptyIcon}
                    action={emptyAction}
                  />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
