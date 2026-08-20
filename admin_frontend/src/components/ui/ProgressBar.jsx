import { useEffect, useRef, useState } from 'react';

import { isLegacy } from '../../providers/visualTheme.js';

// Индиговый градиент со свечением — деталь только исходной темы. И
// Tactical Telemetry, и Ethereal Glass рисуют полосу плоско, цветом
// --color-primary, поэтому проверяем «это legacy?», а не «это refresh?».
const LEGACY_BAR = isLegacy;

export function TopProgressBar({ active }) {
  const [pct, setPct] = useState(0);
  const [mounted, setMounted] = useState(false);
  const [fadingOut, setFadingOut] = useState(false);
  const timers = useRef([]);

  const clear = () => { timers.current.forEach(clearTimeout); timers.current = []; };
  const later = (fn, ms) => { const t = setTimeout(fn, ms); timers.current.push(t); return t; };

  useEffect(() => {
    clear();
    if (active) {
      setMounted(true);
      setFadingOut(false);
      setPct(8);
      later(() => setPct(32), 380);
      later(() => setPct(56), 950);
      later(() => setPct(74), 2600);
      later(() => setPct(88), 6500);
    } else if (mounted) {
      setPct(100);
      later(() => setFadingOut(true), 240);
      later(() => { setMounted(false); setFadingOut(false); setPct(0); }, 600);
    }
    return clear;
  }, [active]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!mounted) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0, left: 0, right: 0,
        zIndex: 9999,
        height: 3,
        pointerEvents: 'none',
        overflow: 'hidden',
        opacity: fadingOut ? 0 : 1,
        transition: fadingOut ? 'opacity 0.36s ease-out' : 'none',
      }}
    >
      {/* Main bar */}
      <div
        style={{
          height: '100%',
          width: `${pct}%`,
          background: LEGACY_BAR
            ? 'linear-gradient(90deg, #6366f1 0%, #8b5cf6 55%, #a78bfa 100%)'
            : 'var(--color-primary)',
          boxShadow: LEGACY_BAR
            ? '0 0 14px rgba(99,102,241,0.75), 0 0 4px rgba(99,102,241,0.95)'
            : 'none',
          borderRadius: LEGACY_BAR ? '0 2px 2px 0' : 'var(--radius-full)',
          transition: active
            ? 'width 1.5s cubic-bezier(0.08, 0.65, 0.12, 1)'
            : 'width 0.28s ease-out',
          position: 'relative',
        }}
      >
        {/* Бегущий блик — глянцевая деталь исходной темы. И брутализм, и
            стекло рисуют полосу без него: в первом случае он противоречит
            плоскости, во втором — забирает внимание у ambient-свечения. */}
        {LEGACY_BAR && (
          <div
            style={{
              position: 'absolute',
              top: 0,
              right: -24,
              width: 48,
              height: '100%',
              background: 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.65) 50%, transparent 100%)',
              animation: active ? 'pb-shine 1.8s ease-in-out infinite' : 'none',
            }}
          />
        )}
      </div>
      <style>{`
        @keyframes pb-shine {
          0%   { opacity: 0; transform: translateX(-60px); }
          30%  { opacity: 1; }
          70%  { opacity: 1; }
          100% { opacity: 0; transform: translateX(60px); }
        }
      `}</style>
    </div>
  );
}
