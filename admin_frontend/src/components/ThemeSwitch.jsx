import { Moon, Sun } from 'lucide-react';
import { Button } from './ui';

export default function ThemeSwitch({ theme, onChange }) {
  const isDark = theme === 'dark';
  const next = isDark ? 'light' : 'dark';

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="gap-2 rounded-full border border-border bg-[color:var(--color-input-background)] px-3 py-1.5 text-xs font-medium text-[color:var(--muted-foreground)] transition hover:bg-[color:var(--accent)] hover:text-[color:var(--accent-foreground)]"
      title={isDark ? 'Переключить на светлую тему' : 'Переключить на тёмную тему'}
      aria-label={isDark ? 'Переключить на светлую тему' : 'Переключить на тёмную тему'}
      onClick={() => onChange(next)}
    >
      {isDark ? <Moon size={16} /> : <Sun size={16} />}
      <span className="hidden md:inline">{isDark ? 'Тёмная тема' : 'Светлая тема'}</span>
    </Button>
  );
}
