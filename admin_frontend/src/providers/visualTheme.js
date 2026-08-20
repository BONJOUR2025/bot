// ============================================================================
// Выбор визуального мира приложения.
//
// Миров три, и они живут одновременно в tokens.css / globals.css:
//
//   glass   — Ethereal Glass (класс .visual-glass). Текущий стандарт.
//   refresh — Tactical Telemetry (класс .visual-refresh). Предыдущий.
//   legacy  — исходная indigo-SaaS тема (без класса вообще).
//
// Управляется VITE_VISUAL_THEME в admin_frontend/.env.production.
//
// Почему отдельный модуль, а не константа в ThemeProvider: флаг читает не
// только провайдер, но и компоненты, которым нужно менять разметку, а не
// только цвет (ProgressBar, Card, Button). Раньше каждый проверял env сам,
// и проверки разошлись: ThemeProvider считал `VITE_VISUAL_REFRESH !== "0"`
// (то есть при незаданной переменной тема ВКЛЮЧЕНА), а ProgressBar.jsx —
// `=== "1"` (при незаданной ВЫКЛЮЧЕНА). В дев-сборке без .env это давало
// брутализм с индиговым прогресс-баром. Теперь резолвер один.
// ============================================================================

const VALID = new Set(['glass', 'refresh', 'legacy']);

function resolve() {
  const named = import.meta.env.VITE_VISUAL_THEME;
  if (typeof named === 'string' && VALID.has(named.trim())) return named.trim();

  // Обратная совместимость со старым булевым флагом: сборки и .env, где
  // прописан только VITE_VISUAL_REFRESH, продолжают работать как раньше.
  const legacyFlag = import.meta.env.VITE_VISUAL_REFRESH;
  if (legacyFlag === '0') return 'legacy';
  if (legacyFlag === '1') return 'refresh';

  return 'glass';
}

/** 'glass' | 'refresh' | 'legacy' — фиксируется на этапе сборки. */
export const VISUAL_THEME = resolve();

/** Класс на <html> для выбранного мира ('' для legacy). */
export const VISUAL_THEME_CLASS =
  VISUAL_THEME === 'glass' ? 'visual-glass' : VISUAL_THEME === 'refresh' ? 'visual-refresh' : '';

/** Все классы миров — чтобы провайдер снимал чужие, а не только свой. */
export const ALL_VISUAL_CLASSES = ['visual-glass', 'visual-refresh'];

export const isGlass = VISUAL_THEME === 'glass';
export const isRefresh = VISUAL_THEME === 'refresh';
export const isLegacy = VISUAL_THEME === 'legacy';
