import { lazy, Suspense, useEffect, useState } from 'react';
import { Upload, Trash2, Plus, X, ChevronDown, ChevronUp, ArrowLeftRight } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import Modal from '../components/Modal.jsx';
import { FootCard, SIDE_LABEL } from '../components/FootScanCard.jsx';

// three.js + fiber + drei are a large bundle (~270kB gzipped) that most
// visits to this page never need (the 3D scene is an opt-in checkbox) --
// code-split so it only downloads when a user actually requests it.
const Viewer3D = lazy(() => import('../components/Viewer3D.jsx'));

function LastCard({ last, onDelete }) {
  const title = last.article || last.model || 'Без названия';
  const sub = [last.model, last.size && `размер ${last.size}`, last.material].filter(Boolean).join(' · ') || '—';
  return (
    <div className="app-card p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">{title}</h3>
          <div className="text-xs text-[color:var(--color-text-muted)]">{sub}</div>
        </div>
        <button type="button" className="btn text-[color:var(--color-danger)]" title="Удалить" onClick={() => onDelete(last.id)}>
          <Trash2 size={16} />
        </button>
      </div>
      {last.note && <p className="text-xs text-[color:var(--color-text-muted)]">{last.note}</p>}
      <div className="grid grid-cols-4 gap-2 text-center text-xs">
        <div><div className="font-semibold text-sm">{last.length_mm ?? '—'}</div>длина</div>
        <div><div className="font-semibold text-sm">{last.ball_girth_mm ?? '—'}</div>пучки</div>
        <div><div className="font-semibold text-sm">{last.instep_girth_mm ?? '—'}</div>подъём</div>
        <div><div className="font-semibold text-sm">{last.width_mm ?? '—'}</div>ширина</div>
      </div>
    </div>
  );
}

const VERDICT_STYLE = {
  good: { label: 'Хорошо подойдёт', cls: 'bg-green-100 text-green-800 border-green-300' },
  ok: { label: 'Подойдёт с минимальным запасом', cls: 'bg-blue-100 text-blue-800 border-blue-300' },
  uncertain: { label: 'Неопределённо — нужна примерка', cls: 'bg-gray-100 text-gray-700 border-gray-300' },
  loose: { label: 'Подойдёт, но свободна', cls: 'bg-amber-100 text-amber-800 border-amber-300' },
  not_fit: { label: 'Не подойдёт', cls: 'bg-red-100 text-red-800 border-red-300' },
};

const ZONE_DOT = {
  too_tight: 'bg-red-500', tight_ok: 'bg-amber-500', ideal: 'bg-green-500',
  loose_ok: 'bg-amber-400', too_loose: 'bg-amber-500', uncertain: 'bg-gray-400',
};

const PATTERN_LABEL = {
  NARROW_HIGH: 'Узкая и высокая — сдавливает с боков, свободно сверху',
  WIDE_LOW: 'Широкая и низкая — давит сверху, свободно по бокам',
  MEDIAL_CONFLICT_DORSAL_VOID: 'Конфликт с внутренней стороны при свободном верхе',
  BALL_TIGHT_INSTEP_LOOSE: 'Тесно в пучках, свободно в подъёме',
  HEEL_VOID_MIDFOOT_TIGHT: 'Свободно в пятке, тесно в своде',
  GENERAL_OVERSIZE: 'В целом свободнее стопы по всей длине',
};

function pct(v) {
  return v == null ? '—' : `${Math.round(v * 100)}%`;
}

function SurfaceResult({ sr }) {
  if (!sr) return null;
  if (sr.error) {
    return (
      <div className="rounded border border-[color:var(--color-border)] p-2 text-xs text-[color:var(--color-text-muted)]">
        3D-анализ по сетке (hybrid_v2, экспериментально): не удалось посчитать — {sr.error}
      </div>
    );
  }
  const reg = sr.registration;
  return (
    <div className="rounded border border-[color:var(--color-border)] p-2 space-y-1.5 text-xs">
      <div className="font-medium">3D-анализ по сетке (hybrid_v2, экспериментально)</div>
      <div>
        Паттерн: {sr.dominant_pattern ? (PATTERN_LABEL[sr.dominant_pattern] || sr.dominant_pattern) : 'не выявлен'}
      </div>
      <div className="flex flex-wrap gap-x-3 text-[color:var(--color-text-muted)]">
        <span>Теснота: {pct(sr.risks?.tightness_risk)}</span>
        <span>Свобода: {pct(sr.risks?.looseness_risk)}</span>
        <span>Риск фиксации пятки: {pct(sr.risks?.retention_risk)}</span>
      </div>
      <div className="text-[color:var(--color-text-muted)]">
        Совмещение стопы с колодкой: уверенность {pct(reg?.registration_confidence)}
        {reg && ` (коррекция ${reg.translation_mm} мм / ${reg.rotation_deg}°)`}
      </div>
      {sr.pose_confidence == null && (
        <div className="text-[color:var(--color-text-muted)]">
          Поза не учтена — у колодки не заданы высота каблука и носочный подъём.
        </div>
      )}
    </div>
  );
}

function FitBadge({ overall }) {
  const s = VERDICT_STYLE[overall] || VERDICT_STYLE.ok;
  return <span className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${s.cls}`}>{s.label}</span>;
}

function GirthRow({ label, pair }) {
  if (!pair) return null;
  const sign = pair.ease_mm > 0 ? '+' : '';
  return (
    <div className="flex justify-between text-xs">
      <span className="text-[color:var(--color-text-muted)]">{label}</span>
      <span>стопа {pair.foot_mm} → колодка {pair.last_mm} (запас {sign}{pair.ease_mm} мм)</span>
    </div>
  );
}

function FootFit({ pf, onOpenImage }) {
  const { fit, foot_side } = pf;
  return (
    <div className="space-y-3 pt-3 border-t border-[color:var(--color-border)]">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{SIDE_LABEL[foot_side] || 'Стопа'}</span>
        <FitBadge overall={fit.overall} />
        <span className="text-xs text-[color:var(--color-text-muted)]">совпадение {fit.overlap_pct}%</span>
      </div>
      <p className="text-sm">{fit.overall_text}</p>

      {fit.hard_fail_reasons?.length > 0 && (
        <div className="rounded border border-red-300 bg-red-50 p-2 text-xs text-red-800">
          <div className="font-medium mb-1">Жёсткие критерии отказа (не усредняются с другими зонами):</div>
          <ul className="list-disc list-inside space-y-0.5">
            {fit.hard_fail_reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {fit.images?.top && (
          <button type="button" className="cursor-zoom-in" onClick={() => onOpenImage(fit.images.top, 'Стопа в колодке — вид сверху')}>
            <img src={fit.images.top} alt="сверху" className="w-full rounded border border-[color:var(--color-border)]" />
          </button>
        )}
        {fit.images?.side && (
          <button type="button" className="cursor-zoom-in" onClick={() => onOpenImage(fit.images.side, 'Стопа в колодке — вид сбоку')}>
            <img src={fit.images.side} alt="сбоку" className="w-full rounded border border-[color:var(--color-border)]" />
          </button>
        )}
      </div>
      <p className="text-[11px] text-[color:var(--color-text-muted)]">
        Серым показана колодка, синим — контур стопы. Красные точки — где стопа выходит за габарит колодки (тесно).
      </p>

      <div className="space-y-1">
        <GirthRow label="Длина" pair={fit.length && { foot_mm: fit.length.foot_mm, last_mm: fit.length.last_mm, ease_mm: fit.length.ease_mm }} />
        <GirthRow label="Обхват пучков" pair={fit.girths?.ball} />
        <GirthRow label="Обхват подъёма" pair={fit.girths?.instep} />
        {fit.ball_line && (
          <div className={`flex justify-between text-xs ${fit.ball_line.flagged ? 'text-amber-700 font-medium' : ''}`}>
            <span className={fit.ball_line.flagged ? '' : 'text-[color:var(--color-text-muted)]'}>
              Линия сгиба (пучки){fit.ball_line.flagged ? ' ⚠️' : ''}
            </span>
            <span>
              стопа {fit.ball_line.foot_mm} мм → колодка {fit.ball_line.last_mm} мм от пятки
              (смещение {fit.ball_line.diff_mm > 0 ? '+' : ''}{fit.ball_line.diff_mm} мм)
            </span>
          </div>
        )}
      </div>

      <div className="space-y-1.5">
        {fit.zones.map((z) => (
          <div key={z.zone} className="flex gap-2 text-xs">
            <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${ZONE_DOT[z.verdict] || 'bg-gray-400'}`} />
            <div>
              <span className="font-medium">{z.label}.</span>{' '}
              <span className="text-[color:var(--color-text-muted)]">{z.explanation}</span>
            </div>
          </div>
        ))}
      </div>

      {fit.instep_sections?.length > 0 && (
        <div className="text-[11px] text-[color:var(--color-text-muted)]">
          <div className="mb-1">
            Запас в подъёме по сечениям (% длины стопы от пятки) — по высоте / по обхвату, мм:
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {fit.instep_sections.map((s) => (
              <span key={s.pct} className={s.height_ease_mm < 0 ? 'text-red-600 font-medium' : ''}>
                I{s.pct}: {s.height_ease_mm > 0 ? '+' : ''}{s.height_ease_mm} / {s.girth_ease_mm > 0 ? '+' : ''}{s.girth_ease_mm}
              </span>
            ))}
          </div>
        </div>
      )}

      <SurfaceResult sr={pf.surface_result} />
      {pf.surface_result?.visualization && (
        <Suspense fallback={<p className="text-xs text-[color:var(--color-text-muted)]">Загружаю 3D-просмотрщик…</p>}>
          <Viewer3D
            geometry={pf.surface_result.visualization}
            title={`3D-сцена — ${SIDE_LABEL[foot_side] || 'стопа'}`}
          />
        </Suspense>
      )}
    </div>
  );
}

const LIMITING_SIDE_LABEL = { left: 'левая', right: 'правая' };

function MatchCard({ match, onOpenImage }) {
  const [open, setOpen] = useState(true);
  const { last, per_foot, bilateral } = match;
  return (
    <div className="app-card p-4 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h4 className="font-semibold">{last.article || last.model || 'Без названия'}</h4>
          <div className="text-xs text-[color:var(--color-text-muted)]">
            {[last.model, last.size && `размер ${last.size}`, last.material].filter(Boolean).join(' · ') || '—'}
          </div>
          {bilateral && (
            <div className="text-xs text-[color:var(--color-text-muted)] mt-1">
              Ограничивающая сторона: <span className="font-medium">{LIMITING_SIDE_LABEL[bilateral.limiting_side] || bilateral.limiting_side}</span>
              {bilateral.patterns?.includes('BILATERAL_LAST_MISMATCH') && (
                <span className="text-amber-700"> · обе стопы тесны — вероятно, дело в форме колодки, а не в асимметрии</span>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {per_foot.map((pf, i) => <FitBadge key={i} overall={pf.fit.overall} />)}
          <button type="button" className="btn" onClick={() => setOpen(o => !o)}>
            {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </div>
      {open && per_foot.map((pf, i) => <FootFit key={i} pf={pf} onOpenImage={onOpenImage} />)}
    </div>
  );
}

export default function LastLibrary() {
  const { toast } = useToast();
  const [lasts, setLasts] = useState([]);
  const [loadingList, setLoadingList] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    article: '', size: '', model: '', material: '', note: '', side: '',
    heel_height_mm: '', toe_spring_mm: '',
  });
  const [addFile, setAddFile] = useState(null);

  const [matching, setMatching] = useState(false);
  const [matchResult, setMatchResult] = useState(null);
  const [matchFile, setMatchFile] = useState(null);
  const [matchFileLeft, setMatchFileLeft] = useState(null);
  const [matchFileRight, setMatchFileRight] = useState(null);
  const [swapSides, setSwapSides] = useState(false);
  const [useHybrid, setUseHybrid] = useState(false);
  const [useGeometry, setUseGeometry] = useState(false);
  const [lightbox, setLightbox] = useState(null);

  async function loadLasts() {
    setLoadingList(true);
    try {
      const res = await api.get('lasts');
      setLasts(res.data.lasts);
    } catch (err) {
      console.error(err);
      toast('Не удалось загрузить библиотеку колодок', 'error');
    } finally {
      setLoadingList(false);
    }
  }

  useEffect(() => { loadLasts(); }, []);

  async function handleAddSubmit(e) {
    e.preventDefault();
    if (!addFile) { toast('Выберите файл .scm или .stl колодки', 'error'); return; }
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append('file', addFile);
      Object.entries(form).forEach(([k, v]) => {
        // heel_height_mm/toe_spring_mm are optional float fields on the
        // backend (Form(None)) -- an empty string fails float parsing there,
        // so only send them when actually filled in.
        if ((k === 'heel_height_mm' || k === 'toe_spring_mm') && v === '') return;
        fd.append(k, v);
      });
      await api.post('lasts', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast('Колодка добавлена', 'success');
      setAddOpen(false);
      setForm({
        article: '', size: '', model: '', material: '', note: '', side: '',
        heel_height_mm: '', toe_spring_mm: '',
      });
      setAddFile(null);
      loadLasts();
    } catch (err) {
      console.error(err);
      toast(err.response?.data?.detail || 'Не удалось разобрать файл колодки', 'error');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm('Удалить колодку из библиотеки?')) return;
    try {
      await api.delete(`lasts/${id}`);
      setLasts(prev => prev.filter(l => l.id !== id));
    } catch (err) {
      console.error(err);
      toast('Не удалось удалить колодку', 'error');
    }
  }

  async function runMatch(file, swap) {
    if (!file) return;
    setMatching(true);
    setMatchResult(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('swap_sides', swap ? 'true' : 'false');
      const res = await api.post('lasts/match', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setMatchResult(res.data);
      if (!res.data.matches.length) {
        toast(lasts.length ? 'Не удалось сопоставить с колодками' : 'Библиотека колодок пуста', 'error');
      }
    } catch (err) {
      console.error(err);
      toast(err.response?.data?.detail || 'Не удалось разобрать файл стопы', 'error');
    } finally {
      setMatching(false);
    }
  }

  function handleMatchFile(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.scm')) { toast('Ожидается файл .scm', 'error'); return; }
    setMatchFile(file);
    setMatchFileLeft(null);
    setMatchFileRight(null);
    setSwapSides(false);
    runMatch(file, false);
  }

  async function runMatchStl(left, right, swap, hybrid, geometry) {
    if (!left && !right) return;
    setMatching(true);
    setMatchResult(null);
    try {
      const fd = new FormData();
      if (left) fd.append('file_left', left);
      if (right) fd.append('file_right', right);
      fd.append('swap_sides', swap ? 'true' : 'false');
      fd.append('engine', hybrid ? 'hybrid_v2' : 'slice_v1');
      fd.append('include_geometry', hybrid && geometry ? 'true' : 'false');
      const res = await api.post('lasts/match', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setMatchResult(res.data);
      if (!res.data.matches.length) {
        toast(lasts.length ? 'Не удалось сопоставить с колодками' : 'Библиотека колодок пуста', 'error');
      }
    } catch (err) {
      console.error(err);
      toast(err.response?.data?.detail || 'Не удалось разобрать файл стопы', 'error');
    } finally {
      setMatching(false);
    }
  }

  function handleMatchStlFile(side, file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.stl')) { toast('Ожидается файл .stl', 'error'); return; }
    setMatchFile(null);
    const left = side === 'left' ? file : matchFileLeft;
    const right = side === 'right' ? file : matchFileRight;
    setMatchFileLeft(left);
    setMatchFileRight(right);
    setSwapSides(false);
    runMatchStl(left, right, false, useHybrid, useGeometry);
  }

  function handleToggleHybrid(checked) {
    setUseHybrid(checked);
    if (!checked) setUseGeometry(false);
    if (matchFileLeft || matchFileRight) runMatchStl(matchFileLeft, matchFileRight, swapSides, checked, checked && useGeometry);
  }

  function handleToggleGeometry(checked) {
    setUseGeometry(checked);
    if (matchFileLeft || matchFileRight) runMatchStl(matchFileLeft, matchFileRight, swapSides, useHybrid, checked);
  }

  function handleSwapSides() {
    const next = !swapSides;
    setSwapSides(next);
    if (matchFile) runMatch(matchFile, next);
    else runMatchStl(matchFileLeft, matchFileRight, next, useHybrid, useGeometry);
  }

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Библиотека колодок ({lasts.length})</h3>
          <button type="button" className="btn btn-primary flex items-center gap-1.5" onClick={() => setAddOpen(true)}>
            <Plus size={16} /> Добавить колодку
          </button>
        </div>
        {loadingList ? (
          <p className="text-sm text-[color:var(--color-text-muted)]">Загрузка…</p>
        ) : lasts.length === 0 ? (
          <div className="rounded border border-dashed border-[color:var(--color-border)] bg-[color:var(--color-surface)] p-6 text-center text-[color:var(--color-text-muted)]">
            Библиотека пуста — добавьте первую колодку.
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {lasts.map(last => <LastCard key={last.id} last={last} onDelete={handleDelete} />)}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h3 className="font-semibold">Подбор колодки по скану стопы</h3>
        <p className="text-sm text-[color:var(--color-text-muted)]">
          Загрузите скан стопы клиента — система «вложит» стопу в каждую колодку, проверит посадку по всей длине
          (пятка, свод, подъём, пучки, носок) и объяснит по-человечески, где и чем колодка неудобна.
        </p>
        <label className="app-card flex flex-col items-center justify-center gap-2 border-2 border-dashed border-[color:var(--color-border)] p-8 text-center cursor-pointer">
          <Upload size={24} className="text-[color:var(--color-text-muted)]" />
          <div className="font-medium">Загрузить скан стопы (.scm)</div>
          <input type="file" accept=".scm" className="hidden" onChange={(e) => handleMatchFile(e.target.files?.[0])} />
        </label>

        <div className="app-card p-4 space-y-3">
          <div className="font-medium text-sm">Или загрузите .stl — отдельно левая и правая стопа</div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col items-center justify-center gap-1.5 border-2 border-dashed border-[color:var(--color-border)] rounded p-4 text-center cursor-pointer text-sm">
              <Upload size={18} className="text-[color:var(--color-text-muted)]" />
              <span className="truncate max-w-full">{matchFileLeft ? matchFileLeft.name : 'Левая стопа (.stl)'}</span>
              <input type="file" accept=".stl" className="hidden" onChange={(e) => handleMatchStlFile('left', e.target.files?.[0])} />
            </label>
            <label className="flex flex-col items-center justify-center gap-1.5 border-2 border-dashed border-[color:var(--color-border)] rounded p-4 text-center cursor-pointer text-sm">
              <Upload size={18} className="text-[color:var(--color-text-muted)]" />
              <span className="truncate max-w-full">{matchFileRight ? matchFileRight.name : 'Правая стопа (.stl)'}</span>
              <input type="file" accept=".stl" className="hidden" onChange={(e) => handleMatchStlFile('right', e.target.files?.[0])} />
            </label>
          </div>
          <label className="flex items-center gap-2 text-xs text-[color:var(--color-text-muted)] cursor-pointer">
            <input type="checkbox" checked={useHybrid} onChange={(e) => handleToggleHybrid(e.target.checked)} />
            Добавить 3D-анализ по сетке (hybrid_v2, экспериментально) — работает только если и стопа, и
            колодка загружены как .stl, и колодка тоже сохранена из .stl
          </label>
          {useHybrid && (
            <label className="flex items-center gap-2 text-xs text-[color:var(--color-text-muted)] cursor-pointer pl-5">
              <input type="checkbox" checked={useGeometry} onChange={(e) => handleToggleGeometry(e.target.checked)} />
              Показать интерактивную 3D-сцену (тяжелее и медленнее — грузит полную геометрию)
            </label>
          )}
        </div>

        {matching && <p className="text-sm text-[color:var(--color-text-muted)]">Сравниваю с библиотекой…</p>}

        {matchResult && (
          <div className="space-y-6">
            {matchResult.feet.length === 2 && (
              <div className="flex justify-end">
                <button
                  type="button"
                  className="btn flex items-center gap-1.5 text-sm"
                  disabled={matching}
                  title="Если стороны определились неверно"
                  onClick={handleSwapSides}
                >
                  <ArrowLeftRight size={14} /> Поменять стороны местами
                </button>
              </div>
            )}
            <div className="grid gap-4 lg:grid-cols-2">
              {matchResult.feet.map((foot, i) => (
                <FootCard key={i} foot={foot} index={i} onOpenImage={(src, alt) => setLightbox({ src, alt })} />
              ))}
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <h4 className="font-medium text-sm text-[color:var(--color-text-muted)]">Результат подбора (лучшее сверху)</h4>
                {useHybrid && matchResult.engine !== 'hybrid_v2' && (
                  <span className="text-xs text-amber-700" title="Возможные причины: скан стопы загружен как .scm, или ни у одной колодки в подборке нет .stl-файла">
                    3D-анализ не подключился — используется только базовый расчёт
                  </span>
                )}
              </div>
              {matchResult.matches.map((m) => (
                <MatchCard key={m.last.id} match={m} onOpenImage={(src, alt) => setLightbox({ src, alt })} />
              ))}
            </div>
          </div>
        )}
      </section>

      <Modal isOpen={addOpen} onClose={() => setAddOpen(false)}>
        <form className="modal-card w-full max-w-md p-4 space-y-3" onSubmit={handleAddSubmit}>
          <div className="flex justify-between items-center">
            <h3 className="font-semibold">Добавить колодку</h3>
            <button type="button" className="btn" onClick={() => setAddOpen(false)}><X size={16} /></button>
          </div>
          <p className="text-xs text-[color:var(--color-text-muted)]">
            Достаточно одного скана колодки — левая и правая зеркально одинаковы, система сама развернёт под нужную стопу.
          </p>
          <label className="block text-sm">
            Файл скана (.scm или .stl)
            <input type="file" accept=".scm,.stl" required className="block w-full mt-1"
              onChange={(e) => setAddFile(e.target.files?.[0] || null)} />
          </label>
          {['article', 'model', 'size', 'material'].map((field) => (
            <label key={field} className="block text-sm">
              {{ article: 'Артикул', model: 'Модель', size: 'Размер', material: 'Материал' }[field]}
              <input type="text" className="input w-full mt-1" value={form[field]}
                onChange={(e) => setForm(f => ({ ...f, [field]: e.target.value }))} />
            </label>
          ))}
          <label className="block text-sm">
            Сторона колодки
            <select className="input w-full mt-1" value={form.side}
              onChange={(e) => setForm(f => ({ ...f, side: e.target.value }))}>
              <option value="">Определить автоматически</option>
              <option value="left">Левая</option>
              <option value="right">Правая</option>
            </select>
            <span className="block text-xs text-[color:var(--color-text-muted)] mt-1">
              Обычно определяется из скана сам; если в сканах колодок этого сканера сторона не пишется в метаданных —
              укажите вручную, иначе подбор может сравнивать не с той стороной.
            </span>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              Высота каблука, мм
              <input type="number" step="0.1" className="input w-full mt-1" value={form.heel_height_mm}
                onChange={(e) => setForm(f => ({ ...f, heel_height_mm: e.target.value }))} />
            </label>
            <label className="block text-sm">
              Носочный подъём, мм
              <input type="number" step="0.1" className="input w-full mt-1" value={form.toe_spring_mm}
                onChange={(e) => setForm(f => ({ ...f, toe_spring_mm: e.target.value }))} />
            </label>
          </div>
          <span className="block text-xs text-[color:var(--color-text-muted)] -mt-2">
            Необязательно — заполните оба, чтобы сравнение учитывало позу стопы под эту колодку
            (иначе стопа и колодка сравниваются в плоском положении, как сейчас).
          </span>
          <label className="block text-sm">
            Заметка
            <textarea className="input w-full mt-1" rows={2} value={form.note}
              onChange={(e) => setForm(f => ({ ...f, note: e.target.value }))} />
          </label>
          <button type="submit" className="btn btn-primary w-full" disabled={saving}>
            {saving ? 'Сохраняю…' : 'Сохранить'}
          </button>
        </form>
      </Modal>

      <Modal isOpen={!!lightbox} onClose={() => setLightbox(null)}>
        <div className="modal-card w-fit max-w-[95vw] sm:mx-4 p-3">
          <div className="flex justify-end mb-1">
            <button type="button" className="btn" onClick={() => setLightbox(null)}><X size={16} /></button>
          </div>
          {lightbox && <img src={lightbox.src} alt={lightbox.alt} className="block max-w-full max-h-[80vh] mx-auto rounded" />}
        </div>
      </Modal>
    </div>
  );
}
