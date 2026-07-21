import { Ruler } from 'lucide-react';

// Shared between Scanner3D.jsx and LastLibrary.jsx — kept in its own module
// (not exported from Scanner3D.jsx) because Scanner3D.jsx imports
// LastLibrary.jsx for its tab, and LastLibrary.jsx needs these; re-exporting
// them from Scanner3D.jsx made that a circular import, which crashed the
// page (SIDE_LABEL, a `const`, isn't initialized yet at the point
// LastLibrary.jsx's own top-level code runs during that cycle).

export const SIDE_LABEL = { left: 'Левая стопа', right: 'Правая стопа' };

export function ViewThumb({ src, alt, label, onOpen }) {
  return (
    <div>
      <button
        type="button"
        onClick={() => onOpen(src, alt)}
        className="block w-full cursor-zoom-in"
        title="Открыть в полном размере"
      >
        <img src={src} alt={alt} className="w-full rounded border border-[color:var(--color-border)] hover:opacity-80 transition-opacity" />
      </button>
      <div className="text-center text-xs text-[color:var(--color-text-muted)] mt-1">{label}</div>
    </div>
  );
}

export function FootCard({ foot, index, onOpenImage }) {
  const label = SIDE_LABEL[foot.side] || `Стопа ${index + 1}`;
  return (
    <div className="app-card p-4 space-y-3">
      <h3 className="font-semibold flex items-center gap-2">
        <Ruler size={16} /> {label}
      </h3>
      <div className="grid grid-cols-4 gap-3 text-center">
        <div>
          <div className="text-xl font-bold">{foot.length_mm}</div>
          <div className="text-xs text-[color:var(--color-text-muted)]">длина, мм</div>
        </div>
        <div>
          <div className="text-xl font-bold">{foot.width_mm}</div>
          <div className="text-xs text-[color:var(--color-text-muted)]">ширина, мм</div>
        </div>
        <div>
          <div className="text-xl font-bold">{foot.height_mm}</div>
          <div className="text-xs text-[color:var(--color-text-muted)]">высота, мм</div>
        </div>
        <div>
          <div className="text-xl font-bold">{foot.ball_girth_mm ?? '—'}</div>
          <div className="text-xs text-[color:var(--color-text-muted)]">пучки, мм</div>
        </div>
      </div>
      <div className="text-xs text-[color:var(--color-text-muted)]">
        {foot.point_count.toLocaleString('ru-RU')} точек облака
        {foot.ball_girth_mm != null && ' · «Пучки» — геометрическая оценка (±2-5 мм), не заменяет замер лентой'}
      </div>
      {foot.views && (
        <div className="grid grid-cols-3 gap-2">
          <ViewThumb src={foot.views.top} alt={`${label} — вид сверху`} label="сверху" onOpen={onOpenImage} />
          <ViewThumb src={foot.views.side} alt={`${label} — вид сбоку`} label="сбоку" onOpen={onOpenImage} />
          <ViewThumb src={foot.views.front} alt={`${label} — вид спереди`} label="спереди" onOpen={onOpenImage} />
        </div>
      )}
    </div>
  );
}
