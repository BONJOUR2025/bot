# Пример: в PowerShell из admin_frontend
#   powershell -ExecutionPolicy Bypass -File .\install_patch1.ps1

param(
  [string]$SrcDir = "src",
  [string]$EnvFile = ".env"
)

function Ensure-Dir($p) { if(-not (Test-Path $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null } }

$styles = Join-Path $SrcDir "styles"
$providers = Join-Path $SrcDir "providers"
$components = Join-Path $SrcDir "components"
$ui = Join-Path $components "ui"

Ensure-Dir $styles
Ensure-Dir $providers
Ensure-Dir $components
Ensure-Dir $ui

# --- файлы патча ---
@"
:root {
  --bg:#0b0d12; --panel:#121620; --surface:#151a26; --txt:#e7eaf0; --muted:#9aa3b2;
  --primary:#5b8cff; --success:#3ecf8e; --warning:#f5b759; --danger:#ff6b6b; --info:#6fb3ff;
  --radius-xs:6px; --radius-sm:10px; --radius-md:14px; --radius-lg:18px;
  --gap-1:4px; --gap-2:8px; --gap-3:12px; --gap-4:16px; --gap-6:24px; --gap-8:32px;
  --shadow-sm:0 4px 12px rgba(0,0,0,.18); --shadow-md:0 8px 24px rgba(0,0,0,.22); --shadow-lg:0 16px 40px rgba(0,0,0,.28);
  --transition-fast:120ms ease; --transition:180ms ease; --transition-slow:260ms ease;
  --control-h:44px; --control-r:12px; --border:1px solid rgba(255,255,255,.06);
}
.theme-light {
  --bg:#f6f7fb; --panel:#fff; --surface:#f2f4f8; --txt:#1b2430; --muted:#6b7483;
  --primary:#3d6bff; --success:#1dbd7d; --warning:#e5a84a; --danger:#ef5454; --info:#3e8eff;
  --border:1px solid rgba(0,0,0,.08);
}
"@ | Set-Content -Encoding UTF8 (Join-Path $styles "tokens.css")

@"
*{box-sizing:border-box} html,body,#root{height:100%}
body{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,""Helvetica Neue"",Arial,""Noto Sans"",""Apple Color Emoji"",""Segoe UI Emoji"";-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
.app-container{max-width:1440px;margin:0 auto;padding:var(--gap-6)}
.panel{background:var(--panel);border:var(--border);border-radius:var(--radius-lg);box-shadow:var(--shadow-sm)}
.h1{font-size:28px;font-weight:600;line-height:1.2} .h2{font-size:22px;font-weight:600;line-height:1.25} .muted{color:var(--muted)}
.btn{display:inline-flex;align-items:center;justify-content:center;height:var(--control-h);border-radius:var(--control-r);padding:0 var(--gap-4);gap:var(--gap-2);font-weight:600;cursor:pointer;border:none;transition:transform var(--transition-fast),opacity var(--transition-fast),box-shadow var(--transition)}
.btn:disabled{opacity:.6;pointer-events:none}
.badge{display:inline-flex;align-items:center;gap:6px;height:24px;border-radius:999px;padding:0 10px;font-size:12px;font-weight:600;letter-spacing:.2px}
.row{display:flex;gap:var(--gap-3);align-items:center} .grid{display:grid;gap:var(--gap-4)} .shadow-hover:hover{box-shadow:var(--shadow-md)}
"@ | Set-Content -Encoding UTF8 (Join-Path $styles "globals.css")

@"
import { useEffect, useMemo, useState } from "react";
const VISUAL_FLAG = import.meta.env.VITE_VISUAL_REFRESH === "1";
export default function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");
  useEffect(() => {
    const root = document.documentElement;
    if (VISUAL_FLAG) root.classList.add("visual-refresh"); else root.classList.remove("visual-refresh");
    if (theme === "light") root.classList.add("theme-light"); else root.classList.remove("theme-light");
    localStorage.setItem("theme", theme);
  }, [theme]);
  const value = useMemo(() => ({ theme, setTheme }), [theme]);
  return children(value);
}
"@ | Set-Content -Encoding UTF8 (Join-Path $providers "ThemeProvider.jsx")

@"
export default function ThemeSwitch({ theme, onChange }) {
  const next = theme === ""dark"" ? ""light"" : ""dark"";
  return (
    <button className=""btn"" title={`Switch to ${next}`} onClick={() => onChange(next)}
      style={{background:""var(--surface)"",color:""var(--txt)"",border:""var(--border)""}}>
      {theme === ""dark"" ? ""🌙 Dark"" : ""☀️ Light""}
    </button>
  );
}
"@ | Set-Content -Encoding UTF8 (Join-Path $components "ThemeSwitch.jsx")

@"
export default function Button({ children, variant = ""primary"", size = ""md"", ...rest }) {
  const styles = {
    primary:{background:""var(--primary)"",color:"#fff"},
    secondary:{background:""var(--surface)"",color:""var(--txt)"",border:""var(--border)""},
    ghost:{background:""transparent"",color:""var(--txt)"",border:""var(--border)""},
    danger:{background:""var(--danger)"",color:"#fff"},
  }[variant];
  const heights = { sm:""36px"", md:""44px"", lg:""52px"" };
  return <button className=""btn"" style={{...styles,height:heights[size]||heights.md,boxShadow:""var(--shadow-sm)""}} {...rest}>{children}</button>;
}
"@ | Set-Content -Encoding UTF8 (Join-Path $ui "Button.jsx")

@"
export default function Card({ children, style, ...rest }) {
  return <div className=""panel"" style={{padding:""16px"",...style}} {...rest}>{children}</div>;
}
"@ | Set-Content -Encoding UTF8 (Join-Path $ui "Card.jsx")

@"
export default function Badge({ children, tone = ""neutral"", style }) {
  const tones = {
    neutral:{background:""rgba(255,255,255,.08)"",color:""var(--txt)""},
    success:{background:""rgba(62,207,142,.18)"",color:""var(--success)""},
    warning:{background:""rgba(245,183,89,.18)"",color:""var(--warning)""},
    danger:{background:""rgba(255,107,107,.18)"",color:""var(--danger)""},
    info:{background:""rgba(111,179,255,.18)"",color:""var(--info)""},
  }[tone]||{};
  return <span className=""badge"" style={{...tones,...style}}>{children}</span>;
}
"@ | Set-Content -Encoding UTF8 (Join-Path $ui "Badge.jsx")

@"
export { default as Button } from ""./Button.jsx"";
export { default as Card } from ""./Card.jsx"";
export { default as Badge } from ""./Badge.jsx"";
"@ | Set-Content -Encoding UTF8 (Join-Path $ui "index.js")

# --- правим main.jsx/tsx ---
$mainJs = Join-Path $SrcDir "main.jsx"
$mainTs = Join-Path $SrcDir "main.tsx"
$main = $null
if (Test-Path $mainJs) { $main = $mainJs }
elseif (Test-Path $mainTs) { $main = $mainTs }
else { Write-Error "Не найден src/main.jsx|tsx"; exit 1 }

Copy-Item $main "$main.bak" -Force

$content = Get-Content $main -Raw

if ($content -notmatch 'styles/tokens.css') {
  $imports = @'
import "./styles/tokens.css";
import "./styles/globals.css";
import ThemeProvider from "./providers/ThemeProvider.jsx";
import ThemeSwitch from "./components/ThemeSwitch.jsx";
'@
  # вставляем импорты после первой строки import
  $content = $content -replace '(^import .+\n)', "`$1$imports"
}

# оборачиваем рендер
if ($content -match '<App\s*/>') {
  $content = $content -replace '(<App\s*/>)', @'
<ThemeProvider>
  {({ theme, setTheme }) => (
    <>
      <div style={{position:"fixed",top:16,right:16,zIndex:9999}}>
        <ThemeSwitch theme={theme} onChange={setTheme} />
      </div>
      <App />
    </>
  )}
</ThemeProvider>
'@
}

Set-Content -Encoding UTF8 $main $content

# --- .env ---
if (-not (Test-Path $EnvFile)) { New-Item -ItemType File -Path $EnvFile -Force | Out-Null }
$envText = Get-Content $EnvFile -Raw
if ($envText -notmatch 'VITE_VISUAL_REFRESH') {
  Add-Content $EnvFile "VITE_VISUAL_REFRESH=1"
}

Write-Host "Done. Backup created: $($main).bak"
Write-Host "Next: npm i && npm run dev"
