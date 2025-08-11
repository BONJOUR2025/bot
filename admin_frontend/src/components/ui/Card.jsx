export default function Card({ children, style, ...rest }) {
  return (
    <div className="panel" style={{ padding: "16px", ...style }} {...rest}>
      {children}
    </div>
  );
}

