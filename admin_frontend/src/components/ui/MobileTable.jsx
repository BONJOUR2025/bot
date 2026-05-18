/**
 * MobileTable — renders a <table> on desktop and cards on mobile.
 *
 * columns: Array<{
 *   key: string,           // row[key] is the cell value
 *   label: string,         // column header / mobile label
 *   render?: (value, row) => ReactNode,
 *   className?: string,    // <td> class
 *   headerClassName?: string,
 *   mobileTitle?: bool,    // used as the card header
 *   mobileActions?: bool,  // rendered in card footer, not as a field row
 *   mobileHide?: bool,     // skipped in mobile card body
 * }>
 *
 * rows: array of data objects
 * keyField: which field is the unique React key (default "id")
 * emptyText: shown when rows is empty
 * onRowClick: optional row click handler (desktop only)
 */
import { useViewport } from '../../providers/ViewportProvider.jsx';

export default function MobileTable({
  columns,
  rows,
  keyField = 'id',
  emptyText = 'Нет данных',
  className = '',
  tableClassName = '',
  onRowClick,
}) {
  const { isMobile } = useViewport();

  if (!rows || rows.length === 0) {
    return (
      <p className="py-4 text-sm text-gray-500 italic">{emptyText}</p>
    );
  }

  const titleCol   = columns.find(c => c.mobileTitle);
  const actionCol  = columns.find(c => c.mobileActions);
  const bodyColumns = columns.filter(c => !c.mobileActions && !c.mobileTitle && !c.mobileHide);

  /* ── Mobile: cards ─────────────────────────────────────────────── */
  if (isMobile) {
    return (
      <div className={`space-y-3 ${className}`}>
        {rows.map((row, i) => {
          const rowKey = row[keyField] ?? i;
          const titleVal = titleCol
            ? (titleCol.render ? titleCol.render(row[titleCol.key], row) : row[titleCol.key])
            : null;

          return (
            <div
              key={rowKey}
              className="border rounded-xl bg-white shadow-sm overflow-hidden"
            >
              {titleVal != null && (
                <div className="px-4 py-3 border-b bg-gray-50 text-sm font-medium text-gray-800">
                  {titleVal}
                </div>
              )}
              <div className="px-4 py-2 space-y-1.5 text-sm">
                {bodyColumns.map(col => {
                  const val = col.render ? col.render(row[col.key], row) : row[col.key];
                  if (val == null || val === '') return null;
                  return (
                    <div key={col.key} className="flex justify-between items-start gap-3">
                      <span className="text-gray-500 shrink-0">{col.label}</span>
                      <span className="text-right text-gray-800">{val}</span>
                    </div>
                  );
                })}
              </div>
              {actionCol && (
                <div className="px-4 py-2 border-t flex justify-end gap-3">
                  {actionCol.render ? actionCol.render(row[actionCol.key], row) : null}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  /* ── Desktop: table ────────────────────────────────────────────── */
  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className={`w-full text-sm ${tableClassName}`}>
        <thead>
          <tr>
            {columns.map(col => (
              <th
                key={col.key}
                className={`px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide border-b ${col.headerClassName ?? ''}`}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {rows.map((row, i) => (
            <tr
              key={row[keyField] ?? i}
              className={`hover:bg-gray-50 transition-colors ${onRowClick ? 'cursor-pointer' : ''}`}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map(col => (
                <td key={col.key} className={`px-4 py-2.5 ${col.className ?? ''}`}>
                  {col.render ? col.render(row[col.key], row) : (row[col.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
