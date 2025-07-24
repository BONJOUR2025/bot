export default function Card({ title, children }) {
  return (
    <div className="bg-surface rounded-2xl shadow p-6 space-y-4 dark:bg-gray-800">
      {title && <h3 className="text-lg font-semibold tracking-tight">{title}</h3>}
      {children}
    </div>
  );
}
