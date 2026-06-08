import { RefreshCw, CheckCircle, XCircle } from 'lucide-react';

export function StatusDot({ ok, loading }) {
  if (loading) return <RefreshCw size={14} className="animate-spin text-[color:var(--color-muted-foreground)]" />;
  return ok
    ? <CheckCircle size={16} className="text-green-500" />
    : <XCircle size={16} className="text-red-500" />;
}

export function Section({ title, children }) {
  return (
    <div className="app-card p-5 space-y-4">
      <h3 className="font-semibold text-base">{title}</h3>
      {children}
    </div>
  );
}

export function Field({ label, hint, children }) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1">{label}</label>
      {children}
      {hint && <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">{hint}</p>}
    </div>
  );
}
