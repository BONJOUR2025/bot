import { Badge } from './ui/badge.jsx';

const STATUS_STYLES = {
  Ожидает: 'border-amber-400/50 bg-amber-500/10 text-amber-100',
  Одобрено: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-100',
  Выплачено: 'border-sky-400/40 bg-sky-500/10 text-sky-100',
  Отклонено: 'border-red-400/40 bg-red-500/10 text-red-100',
  Отменено: 'border-slate-500/40 bg-slate-600/10 text-slate-200',
};

export default function StatusBadge({ status }) {
  const tone = STATUS_STYLES[status] ?? 'border-border/70 bg-muted/20 text-muted-foreground';
  return (
    <Badge variant="outline" className={`h-7 px-3 text-xs font-semibold ${tone}`}>
      {status}
    </Badge>
  );
}
