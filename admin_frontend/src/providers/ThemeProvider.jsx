import { createContext, useContext, useEffect, useMemo, useState } from "react";

const VISUAL_FLAG = import.meta.env.VITE_VISUAL_REFRESH === "1";

const ThemeContext = createContext({ theme: "light", setTheme: () => {} });

// Lets any component read/toggle the theme without prop-drilling.
export const useTheme = () => useContext(ThemeContext);

export default function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem("theme") || "light";
  });

  useEffect(() => {
    const root = document.documentElement;
    if (VISUAL_FLAG) root.classList.add("visual-refresh");
    else root.classList.remove("visual-refresh");

    if (theme === "light") root.classList.add("theme-light");
    else root.classList.remove("theme-light");

    localStorage.setItem("theme", theme);
  }, [theme]);

  const value = useMemo(() => ({ theme, setTheme }), [theme]);
  // Provide via context; still support the existing render-prop usage in App.
  return (
    <ThemeContext.Provider value={value}>
      {typeof children === "function" ? children(value) : children}
    </ThemeContext.Provider>
  );
}


