/**
 * Group employees by position, sorted alphabetically within each group and
 * by position name across groups. Used to fill every employee <select> in
 * the admin panel the same way, so a dropdown with dozens of names doesn't
 * read as an unsorted flat list.
 *
 * `nameFn` picks the display name per employee (some pages toggle between
 * `name` and `full_name`); defaults to `name || full_name`.
 */
export function groupEmployeesByPosition(employees, nameFn) {
  const displayName = nameFn || ((e) => e.name || e.full_name || '');
  const groups = {};
  for (const e of employees || []) {
    const key = e.position || 'Без должности';
    (groups[key] = groups[key] || []).push(e);
  }
  return Object.entries(groups)
    .sort(([a], [b]) => a.localeCompare(b, 'ru'))
    .map(([position, list]) => [
      position,
      [...list].sort((a, b) => displayName(a).localeCompare(displayName(b), 'ru')),
    ]);
}

export default groupEmployeesByPosition;
