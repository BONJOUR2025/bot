// Shared scope badge — used everywhere AI-facing scoped data is shown,
// so the admin can never mistake vacancy-only data for global data.
// Global = blue/neutral ("for all vacancies"), vacancy-scoped = amber/orange ("this vacancy only").
export default function ScopeBadge({ scope, vacancyTitle }) {
  if (scope === 'global') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 whitespace-nowrap">
        🌐 Общее — для всех вакансий
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 whitespace-nowrap">
      📌 Только «{vacancyTitle || 'эта вакансия'}»
    </span>
  );
}
