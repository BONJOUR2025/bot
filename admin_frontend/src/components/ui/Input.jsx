export default function Input({ label, ...props }) {
  return (
    <div className="space-y-1">
      {label && <label className="text-sm text-muted">{label}</label>}
      <input
        {...props}
        className="w-full rounded-lg border-gray-300 shadow-sm focus:border-brand focus:ring-brand transition"
      />
    </div>
  );
}




