export default function Card({ title, children }) {
  return (
    <div className="bg-white rounded-2xl shadow p-6 space-y-4">
      {title && <h3 className="text-lg font-semibold text-gray-800">{title}</h3>}
      {children}
    </div>
  );
}
