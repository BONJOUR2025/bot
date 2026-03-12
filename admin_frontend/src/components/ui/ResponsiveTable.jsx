import { useViewport } from '../../providers/ViewportProvider.jsx';

/**
 * columns: Array of:
 *   { label, key, render, headerClass, cellClass, mobileHide, isAction, primary }
 *
 * - label:       column header text
 * - key:         row[key] fallback if no render
 * - render:      (row) => ReactNode
 * - mobileHide:  hide this column in card mode
 * - isAction:    renders at the bottom of the card (buttons)
 * - primary:     renders as card title (bold, top)
 */
export default function ResponsiveTable({
  columns,
  data,
  keyFn,
  rowClass,
  emptyText = 'Нет данных',
}) {
  const { isMobile } = useViewport();

  if (isMobile) {
    if (data.length === 0) {
      return (
        <div className="py-6 text-center text-gray-500 text-sm">{emptyText}</div>
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
              className={`border rounded-xl bg-white shadow-sm overflow-hidden ${rowClass?.(row) || ''}`}
            >
              {primaryCol && (
                <div className="px-4 py-3 border-b bg-gray-50 font-medium text-sm">
                  {primaryCol.render ? primaryCol.render(row) : row[primaryCol.key]}
                </div>
              )}
              <div className="px-4 py-2 space-y-1.5">
                {bodyColumns.map((col) => (
                  <div key={col.label} className="flex justify-between items-start gap-2 text-sm">
                    <span className="text-gray-500 shrink-0">{col.label}</span>
                    <span className="text-right">
                      {col.render ? col.render(row) : row[col.key] ?? '—'}
                    </span>
                  </div>
                ))}
              </div>
              {actionCol && (
                <div className="px-4 py-2 border-t flex justify-end gap-2">
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
    <div className="overflow-auto border rounded shadow bg-white">
      <table className="min-w-max w-full text-sm">
        <thead className="bg-gray-50">
          <tr>
            {columns.map((col) => (
              <th key={col.label} className={`p-2 text-left whitespace-nowrap ${col.headerClass || ''}`}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y">
          {data.map((row) => (
            <tr key={keyFn(row)} className={`hover:bg-gray-50 ${rowClass?.(row) || ''}`}>
              {columns.map((col) => (
                <td key={col.label} className={`p-2 ${col.cellClass || ''}`}>
                  {col.render ? col.render(row) : row[col.key] ?? ''}
                </td>
              ))}
            </tr>
          ))}
          {data.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="p-4 text-center text-gray-500">
                {emptyText}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
