export default function Badge({ children, tone = "neutral", style }) {
  const tones = {
    neutral: { background: "rgba(255,255,255,.08)", color: "var(--txt)" },
    success: { background: "rgba(62,207,142,.18)",  color: "var(--success)" },
    warning: { background: "rgba(245,183,89,.18)",  color: "var(--warning)" },
    danger:  { background: "rgba(255,107,107,.18)", color: "var(--danger)" },
    info:    { background: "rgba(111,179,255,.18)", color: "var(--info)" },
  }[tone] || {};
  return (
    <span className="badge" style={{ ...tones, ...style }}>
      {children}
    </span>
  );
}

