import { createContext, useContext, useEffect, useMemo, useState } from "react";

const VISUAL_FLAG = import.meta.env.VITE_VISUAL_REFRESH === "1";
const STORAGE_KEY = "theme";

const ThemeContext = createContext({ theme: "light", setTheme: () => {} });

// Lets any component read/toggle the theme without prop-drilling.
export const useTheme = () => useContext(ThemeContext);

export default function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return saved;
    const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
    return prefersDark ? "dark" : "light";
  });

  // An explicit in-app choice (the toggle in Navigation.jsx) persists and
  // from then on overrides the OS setting — only the initial, un-persisted
  // detection keeps following the system live (see the matchMedia listener
  // below).
  const setTheme = (next) => {
    localStorage.setItem(STORAGE_KEY, next);
    setThemeState(next);
  };

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const onChange = (e) => {
      if (localStorage.getItem(STORAGE_KEY)) return;
      setThemeState(e.matches ? "dark" : "light");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (VISUAL_FLAG) root.classList.add("visual-refresh");
    else root.classList.remove("visual-refresh");

    if (theme === "light") root.classList.add("theme-light");
    else root.classList.remove("theme-light");

    // Only relevant inside the native iOS shell (see admin_frontend/ios) —
    // a plain browser tab has no such bridge, so this is a silent no-op
    // there. Unlike the PWA's static apple-mobile-web-app-status-bar-style
    // meta tag (read once at launch, can't react to an in-app theme
    // switch), the native status bar can be restyled at any time.
    import("@capacitor/core").then(({ Capacitor }) => {
      if (!Capacitor.isNativePlatform()) return;
      import("@capacitor/status-bar").then(({ StatusBar, Style }) => {
        StatusBar.setStyle({ style: theme === "light" ? Style.Light : Style.Dark }).catch(() => {});
      });
    });
  }, [theme]);

  const value = useMemo(() => ({ theme, setTheme }), [theme]);
  // Provide via context; still support the existing render-prop usage in App.
  return (
    <ThemeContext.Provider value={value}>
      {typeof children === "function" ? children(value) : children}
    </ThemeContext.Provider>
  );
}


