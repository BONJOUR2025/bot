// Shared visual primitives for the salary pages (admins/masters/managers/couriers) —
// keeps the "hero + formula + tabs + stat cards" look consistent across pages whose
// calculation logic differs.

export const fmtMoney = (v) => (v === null || v === undefined ? '—' : `${Number(v).toLocaleString('ru-RU')} ₽`);
export const fmtPct = (v) => (v === null || v === undefined ? '—' : `${(Number(v) * 100).toFixed(1)}%`);

export const TONE_VAR = {
  success: 'var(--color-success)', primary: 'var(--color-primary)',
  danger: 'var(--color-danger)', muted: 'var(--color-muted-foreground)',
};
export const TONE_TEXT = {
  success: 'text-[color:var(--color-success)]', primary: 'text-[color:var(--color-primary)]',
  danger: 'text-[color:var(--color-danger)]', muted: 'text-[color:var(--color-muted-foreground)]',
};

// ratio → semantic tone (порог 79%, цель 100%)
export const toneOf = (ratio) => {
  if (ratio == null) return 'muted';
  const p = ratio * 100;
  return p >= 100 ? 'success' : p >= 79 ? 'primary' : 'danger';
};

// One term of a payout formula (operator + labelled amount), kept on one line.
export function Term({ op, label, value, tone, strong, fmt = fmtMoney }) {
  return (
    <div className="inline-flex items-center gap-2 whitespace-nowrap">
      {op && <span className="text-[color:var(--color-muted-foreground)] text-base font-medium select-none">{op}</span>}
      <div>
        <div className="text-[10px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">{label}</div>
        <div className={`tabular-nums font-semibold ${strong ? 'text-lg' : 'text-base'} ${tone || ''}`}>{fmt(value)}</div>
      </div>
    </div>
  );
}

// A compact stat card (quality metrics / KPI tiles).
export function StatCard({ icon, label, value, sub, tone, onClick, active }) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`app-card p-4 flex items-start gap-3 text-left w-full ${onClick ? 'hover:ring-2 ring-[color:var(--color-primary)]/40 transition-all' : ''}`}
      style={active ? { outline: '2px solid var(--color-primary)' } : undefined}
    >
      <div className="mt-0.5 shrink-0 text-[color:var(--color-muted-foreground)]">{icon}</div>
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">{label}</div>
        <div className={`text-lg font-semibold leading-tight ${tone || ''}`}>{value}</div>
        {sub && <div className="text-[11px] text-[color:var(--color-muted-foreground)] mt-0.5">{sub}</div>}
      </div>
    </Tag>
  );
}

// KPI metric: plan vs fact with a progress bar and a 79% threshold marker.
export function MetricBar({ label, note, plan, fact, ratio, contribution, fmt = fmtMoney }) {
  const pctNum = ratio == null ? null : ratio * 100;
  const tone = toneOf(ratio);
  const fill = Math.min(Math.max(ratio || 0, 0), 1) * 100;
  return (
    <div className="py-3 border-t border-[color:var(--color-border)] first:border-t-0 first:pt-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium">{label}</span>
        <span className="text-sm font-semibold tabular-nums">{fmtMoney(contribution)}</span>
      </div>
      <div className="mt-2 relative h-2 rounded-full bg-[color:var(--color-bg-secondary)] overflow-visible">
        <div className="absolute inset-y-0 left-0 rounded-full transition-all" style={{ width: `${fill}%`, background: TONE_VAR[tone] }} />
        <div className="absolute -top-1 -bottom-1 w-0.5 rounded bg-[color:var(--color-muted-foreground)] opacity-50" style={{ left: '79%' }} title="Порог 79%" />
      </div>
      <div className="mt-1.5 flex items-center justify-between text-xs text-[color:var(--color-muted-foreground)]">
        <span>план {fmt(plan)} · факт <span className="text-[color:var(--color-text)] font-medium">{fmt(fact)}</span></span>
        <span className={`font-semibold ${TONE_TEXT[tone]}`}>{pctNum == null ? '—' : `${pctNum.toFixed(0)}%`}</span>
      </div>
      {note && <div className="text-[11px] text-[color:var(--color-muted-foreground)] mt-1">{note}</div>}
    </div>
  );
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="flex gap-1 p-1 rounded-xl bg-[color:var(--color-bg-secondary)] overflow-x-auto">
      {tabs.map((t) => (
        <button key={t.key} type="button" onClick={() => onChange(t.key)}
          className={`px-3 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors flex items-center gap-1.5
            ${active === t.key
              ? 'bg-[color:var(--color-surface)] text-[color:var(--color-text)] shadow-sm'
              : 'text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-text)]'}`}>
          {t.icon}{t.label}
          {t.badge != null && t.badge !== 0 && (
            <span className="ml-0.5 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-semibold bg-[color:var(--color-bg)] text-[color:var(--color-muted-foreground)]">{t.badge}</span>
          )}
        </button>
      ))}
    </div>
  );
}
