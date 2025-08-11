export default function Button({
  children,
  variant = "primary",
  size = "md",
  ...rest
}) {
  const styles = {
    primary:  { background: "var(--primary)",  color: "#fff" },
    secondary:{ background: "var(--surface)",  color: "var(--txt)", border: "var(--border)" },
    ghost:    { background: "transparent",     color: "var(--txt)", border: "var(--border)" },
    danger:   { background: "var(--danger)",   color: "#fff" },
  }[variant];

  const heights = { sm: "36px", md: "44px", lg: "52px" };

  return (
    <button
      className="btn"
      style={{ ...styles, height: heights[size] || heights.md, boxShadow: "var(--shadow-sm)" }}
      {...rest}
    >
      {children}
    </button>
  );
}

