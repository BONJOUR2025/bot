import { createContext, useContext, useEffect, useMemo, useState } from "react";

const VISUAL_FLAG = import.meta.env.VITE_VISUAL_REFRESH === "1";
const STORAGE_KEY = "theme";
const VALID_MODES = new Set(["light", "dark", "auto"]);

const ThemeContext = createContext({ mode: "auto", theme: "light", setMode: () => {} });

// Lets any component read/toggle the theme without prop-drilling.
export const useTheme = () => useContext(ThemeContext);

function systemPrefersDark() {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export default function ThemeProvider({ children }) {
  // mode: what the user picked — 'light' | 'dark' | 'auto'.
  const [mode, setModeState] = useState(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return VALID_MODES.has(saved) ? saved : "auto";
  });
  // systemDark: live OS preference, only actually used while mode === 'auto'.
  const [systemDark, setSystemDark] = useState(systemPrefersDark);

  const setMode = (next) => {
    localStorage.setItem(STORAGE_KEY, next);
    setModeState(next);
  };

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const onChange = (e) => setSystemDark(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  // theme: the actual light/dark used for styling, resolving 'auto' live.
  const theme = mode === "auto" ? (systemDark ? "dark" : "light") : mode;

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
        // Style.Dark = dark icons, for a LIGHT background; Style.Light =
        // light icons, for a DARK background (mirrors iOS's own
        // UIStatusBarStyle.darkContent / .lightContent). This was inverted
        // before, making status bar icons nearly invisible in both themes.
        StatusBar.setStyle({ style: theme === "light" ? Style.Dark : Style.Light }).catch(() => {});
      });
    });
  }, [theme]);

  const value = useMemo(() => ({ mode, theme, setMode }), [mode, theme]);
  // Provide via context; still support the existing render-prop usage in App.
  return (
    <ThemeContext.Provider value={value}>
      {typeof children === "function" ? children(value) : children}
    </ThemeContext.Provider>
  );
}
