export default function ThemeSwitch({ theme, onChange }) {
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      className="btn"
      title={`Switch to ${next}`}
      onClick={() => onChange(next)}
      style={{ background: "var(--surface)", color: "var(--txt)", border: "var(--border)" }}
    >
      {theme === "dark" ? "Dark" : "Light"}
    </button>
  );
}
