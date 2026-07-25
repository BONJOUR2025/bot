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





const SEVERITY_STYLE = {
  critical: { dot: 'bg-red-500', box: 'border-red-300 bg-red-50', text: 'text-red-900' },
  warning: { dot: 'bg-amber-500', box: 'border-amber-300 bg-amber-50', text: 'text-amber-900' },
  neutral: { dot: 'bg-slate-400', box: 'border-slate-300 bg-slate-50', text: 'text-slate-800' },
  good: { dot: 'bg-emerald-500', box: 'border-emerald-200 bg-emerald-50', text: 'text-emerald-900' },
};

const HEADLINE_STYLE = {
  FIT_GOOD: 'bg-emerald-100 text-emerald-900 border-emerald-300',
  FIT_LOCAL_TIGHTNESS: 'bg-amber-100 text-amber-900 border-amber-300',
  FIT_LOCAL_LOOSENESS: 'bg-amber-100 text-amber-900 border-amber-300',
  FIT_REQUIRES_LAST_MODIFICATION: 'bg-red-100 text-red-900 border-red-300',
  FIT_INDETERMINATE: 'bg-slate-100 text-slate-800 border-slate-300',
};

/** One finding: the measured fact, what it plausibly means, and what to check.
 * Kept as three separate lines on purpose -- the audit (§21) objects to
 * verdicts that fuse a measurement and its consequence into one confident
 * sentence. */
function FindingRow({ f }) {
  const st = SEVERITY_STYLE[f.severity] || SEVERITY_STYLE.neutral;
  const isProblem = f.severity === 'critical' || f.severity === 'warning';
  if (!isProblem) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <span className={`h-2 w-2 shrink-0 rounded-full ${st.dot}`} />
        <span className="text-[color:var(--color-text-muted)]">{f.title}</span>
      </div>
    );
  }
  return (
    <div className={`rounded border p-2.5 space-y-1 ${st.box}`}>
      <div className={`flex items-center gap-2 text-sm font-medium ${st.text}`}>
        <span className={`h-2 w-2 shrink-0 rounded-full ${st.dot}`} />
        {f.title}
      </div>
      <div className={`text-xs ${st.text} opacity-90`}>{f.fact}</div>
      <div className={`text-xs ${st.text}`}><span className="font-medium">Что это значит: </span>{f.effect}</div>
      {f.check && (
        <div className="text-[11px] text-[color:var(--color-text-muted)]">
          <span className="font-medium">Проверить: </span>{f.check}
        </div>
      )}
    </div>
  );
}

function FootFit({ pf, onOpenImage }) {
  const { fit_result: fr, foot_side } = pf;
  const [showDetails, setShowDetails] = useState(false);
  if (!fr) return null;
  if (fr.error) {
    return (
      <div className="pt-3 border-t border-[color:var(--color-border)] text-sm text-[color:var(--color-text-muted)]">
        {SIDE_LABEL[foot_side] || 'Стопа'}: не удалось посчитать — {fr.error}
      </div>
    );
  }
  const ex = fr.explanation || {};
  const findings = ex.findings || [];
  const problems = findings.filter((f) => f.severity === 'critical' || f.severity === 'warning');
  const rest = findings.filter((f) => f.severity !== 'critical' && f.severity !== 'warning');
  const footprint = fr.footprint_png_base64
    ? `data:image/png;base64,${fr.footprint_png_base64}` : null;

  return (
    <div className="space-y-3 pt-3 border-t border-[color:var(--color-border)]">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{SIDE_LABEL[foot_side] || 'Стопа'}</span>
        <span className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${HEADLINE_STYLE[fr.fit_class] || HEADLINE_STYLE.FIT_INDETERMINATE}`}>
          {ex.headline || fr.fit_class}
        </span>
        <span className="text-xs text-[color:var(--color-text-muted)]">
          уверенность {Math.round((fr.confidence || 0) * 100)}%
        </span>
      </div>

      {ex.summary && <p className="text-sm">{ex.summary}</p>}

      {problems.length > 0 && <div className="space-y-2">{problems.map((f, i) => <FindingRow key={i} f={f} />)}</div>}

      {rest.length > 0 && (
        <div className="space-y-1">
          <div className="text-[11px] font-medium text-[color:var(--color-text-muted)]">Без замечаний:</div>
          {rest.map((f, i) => <FindingRow key={i} f={f} />)}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {footprint && (
          <button type="button" className="cursor-zoom-in" onClick={() => onOpenImage(footprint, 'След стопы и след колодки')}>
            <img src={footprint} alt="след стопы и колодки" className="w-full rounded border border-[color:var(--color-border)]" />
          </button>
        )}
      </div>

      {fr.visualization && (
        <Suspense fallback={<p className="text-xs text-[color:var(--color-text-muted)]">Загружаю 3D-просмотрщик…</p>}>
          <Viewer3D geometry={fr.visualization} title={`3D-сцена — ${SIDE_LABEL[foot_side] || 'стопа'}`} />
        </Suspense>
      )}

      <button type="button" className="text-xs text-[color:var(--color-text-muted)] underline"
              onClick={() => setShowDetails((v) => !v)}>
        {showDetails ? 'Скрыть подробности измерений' : 'Подробности измерений и оговорки'}
      </button>
      {showDetails && (
        <div className="rounded border border-[color:var(--color-border)] p-2 space-y-1 text-[11px] text-[color:var(--color-text-muted)]">
          {(ex.caveats || []).map((c, i) => <div key={i}>• {c}</div>)}
        </div>
      )}
    </div>
  );
}

function MatchCard({ match, onOpenImage }) {
  const [open, setOpen] = useState(true);
  const { last, per_foot } = match;
  return (
    <div className="app-card p-4 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h4 className="font-semibold">{last.article || last.model || 'Без названия'}</h4>
          <div className="text-xs text-[color:var(--color-text-muted)]">
            {[last.model, last.size && `размер ${last.size}`, last.material].filter(Boolean).join(' · ') || '—'}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {per_foot.map((pf, i) => (
            <span key={i}
                  className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${HEADLINE_STYLE[pf.fit_result?.fit_class] || HEADLINE_STYLE.FIT_INDETERMINATE}`}>
              {pf.fit_result?.explanation?.headline || '—'}
            </span>
          ))}
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

  async function runMatchStl(left, right, swap) {
    if (!left && !right) return;
    setMatching(true);
    setMatchResult(null);
    try {
      const fd = new FormData();
      if (left) fd.append('file_left', left);
      if (right) fd.append('file_right', right);
      fd.append('swap_sides', swap ? 'true' : 'false');
      // Always the current engine with its geometry: the UI no longer asks
      // the user to pick an analysis, it just shows the best one available.
      fd.append('engine', 'fit_v3');
      fd.append('include_geometry', 'true');
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
    runMatchStl(left, right, false);
  }


  function handleSwapSides() {
    const next = !swapSides;
    setSwapSides(next);
    if (matchFile) runMatch(matchFile, next);
    else runMatchStl(matchFileLeft, matchFileRight, next);
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
