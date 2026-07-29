import { lazy, Suspense, useEffect, useState } from 'react';
import { Upload, Trash2, Plus, X, ChevronDown, ChevronUp, ArrowLeftRight, Pencil } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import Modal from '../components/Modal.jsx';
import { FootCard, SIDE_LABEL } from '../components/FootScanCard.jsx';

// three.js + fiber + drei are a large bundle (~270kB gzipped) that most
// visits to this page never need (the 3D scene is an opt-in checkbox) --
// code-split so it only downloads when a user actually requests it.
const Viewer3D = lazy(() => import('../components/Viewer3D.jsx'));

/** A production last is a graded family: one model number issued across
 * several sizes and width grades. The library mirrors that -- a section per
 * model, and inside it a size x fullness grid -- rather than a flat list where
 * twenty scans of the same last look like twenty different lasts. */
function groupByModel(lasts) {
  const groups = new Map();
  for (const l of lasts) {
    const key = (l.article || l.model || '').trim() || 'Без номера';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(l);
  }
  return [...groups.entries()]
    .map(([code, items]) => {
      // Sizes sort numerically where they are numbers, so 5 does not land
      // after 40; fullness grades are usually letters and sort naturally.
      const sizes = [...new Set(items.map((i) => (i.size || '').trim() || '—'))]
        .sort((a, b) => (parseFloat(a) || 0) - (parseFloat(b) || 0) || a.localeCompare(b));
      const fullnesses = [...new Set(items.map((i) => (i.fullness || '').trim() || '—'))]
        .sort((a, b) => a.localeCompare(b, 'ru', { numeric: true }));
      const cell = new Map();
      for (const i of items) {
        cell.set(`${(i.size || '').trim() || '—'}|${(i.fullness || '').trim() || '—'}`, i);
      }
      return { code, items, sizes, fullnesses, cell };
    })
    .sort((a, b) => a.code.localeCompare(b.code, 'ru', { numeric: true }));
}

const LAST_EDIT_FIELDS = ['article', 'size', 'fullness', 'model', 'material'];

function LastEditForm({ last, articles, onCancel, onSave }) {
  const [form, setForm] = useState(() => ({
    article: last.article || '', size: last.size || '', fullness: last.fullness || '',
    model: last.model || '', material: last.material || '', note: last.note || '',
    side: last.side || '', heel_height_mm: last.heel_height_mm ?? '', toe_spring_mm: last.toe_spring_mm ?? '',
  }));
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave(last.id, form);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="space-y-3" onSubmit={handleSubmit}>
      <label className="block text-sm">
        Номер колодки
        <select className="input w-full mt-1" required value={form.article}
          onChange={(e) => setForm(f => ({ ...f, article: e.target.value }))}>
          <option value="" disabled>Выберите номер…</option>
          {/* the last's current article stays selectable even if it somehow
              isn't (yet) in the registry, so editing never blanks the field */}
          {!articles.some(a => a.code === form.article) && form.article && (
            <option value={form.article}>{form.article}</option>
          )}
          {articles.map((a) => (
            <option key={a.id} value={a.code}>{a.code}{a.name ? ` — ${a.name}` : ''}</option>
          ))}
        </select>
      </label>
      {LAST_EDIT_FIELDS.filter((f) => f !== 'article').map((field) => (
        <label key={field} className="block text-sm">
          {{ size: 'Размер', fullness: 'Полнота', model: 'Модель', material: 'Материал' }[field]}
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
      <label className="block text-sm">
        Заметка
        <textarea className="input w-full mt-1" rows={2} value={form.note}
          onChange={(e) => setForm(f => ({ ...f, note: e.target.value }))} />
      </label>
      <div className="flex justify-end gap-2">
        <button type="button" className="btn" onClick={onCancel} disabled={saving}>Отмена</button>
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? 'Сохраняю…' : 'Сохранить'}
        </button>
      </div>
    </form>
  );
}

function LastDetail({ last, articles, onClose, onDelete, onSave }) {
  const [editing, setEditing] = useState(false);
  useEffect(() => { setEditing(false); }, [last?.id]);
  if (!last) return null;

  if (editing) {
    return (
      <div className="modal-card max-w-lg w-full space-y-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold">Редактировать колодку {last.article || last.model || '—'}</h3>
          <button type="button" className="btn" onClick={onClose}><X size={16} /></button>
        </div>
        <LastEditForm
          last={last}
          articles={articles}
          onCancel={() => setEditing(false)}
          onSave={async (id, form) => { await onSave(id, form); setEditing(false); }}
        />
      </div>
    );
  }

  const rows = [
    ['Длина', last.length_mm], ['Ширина', last.width_mm], ['Высота', last.height_mm],
    ['Обхват пучков', last.ball_girth_mm], ['Обхват подъёма', last.instep_girth_mm],
    ['Линия пучков от пятки', last.ball_line_mm],
  ];
  return (
    <div className="modal-card max-w-lg w-full space-y-3" onClick={(e) => e.stopPropagation()}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">
            Колодка {last.article || last.model || '—'}
          </h3>
          <div className="text-xs text-[color:var(--color-text-muted)]">
            размер {last.size || '—'} · полнота {last.fullness || '—'}
            {last.side ? ` · ${last.side === 'left' ? 'левая' : 'правая'}` : ''}
          </div>
        </div>
        <button type="button" className="btn" onClick={onClose}><X size={16} /></button>
      </div>

      {last.note && <p className="text-xs text-[color:var(--color-text-muted)]">{last.note}</p>}

      <div className="space-y-1">
        {rows.map(([label, v]) => (
          <div key={label} className="flex justify-between text-xs">
            <span className="text-[color:var(--color-text-muted)]">{label}</span>
            <span>{v ?? '—'}{v != null ? ' мм' : ''}</span>
          </div>
        ))}
        {last.material && (
          <div className="flex justify-between text-xs">
            <span className="text-[color:var(--color-text-muted)]">Материал</span><span>{last.material}</span>
          </div>
        )}
      </div>

      {last.scan_file_url && (
        <a href={last.scan_file_url} className="text-xs underline text-[color:var(--color-text-muted)]"
           target="_blank" rel="noreferrer">Скачать .stl</a>
      )}

      <div className="flex justify-end gap-2">
        <button type="button" className="btn flex items-center gap-1.5" onClick={() => setEditing(true)}>
          <Pencil size={15} /> Редактировать
        </button>
        <button type="button" className="btn text-[color:var(--color-danger)] flex items-center gap-1.5"
                onClick={() => onDelete(last.id)}>
          <Trash2 size={15} /> Удалить эту колодку
        </button>
      </div>
    </div>
  );
}

function LastFamily({ group, onOpen }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="app-card p-4 space-y-3">
      <button type="button" className="flex w-full items-center justify-between gap-2"
              onClick={() => setOpen((v) => !v)}>
        <div className="text-left">
          <h4 className="font-semibold">Колодка {group.code}</h4>
          <div className="text-xs text-[color:var(--color-text-muted)]">
            {group.items.length} шт · размеры {group.sizes.join(', ')} · полноты {group.fullnesses.join(', ')}
          </div>
        </div>
        {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>

      {open && (
        <div className="overflow-x-auto">
          <table className="text-xs">
            <thead>
              <tr>
                <th className="text-left font-medium text-[color:var(--color-text-muted)]">размер \ полнота</th>
                {group.fullnesses.map((f) => <th key={f} className="px-2 font-medium">{f}</th>)}
              </tr>
            </thead>
            <tbody>
              {group.sizes.map((sz) => (
                <tr key={sz}>
                  <td className="font-medium">{sz}</td>
                  {group.fullnesses.map((f) => {
                    const item = group.cell.get(`${sz}|${f}`);
                    return (
                      <td key={f} className="px-1 py-0.5 text-center">
                        {item ? (
                          <button type="button"
                                  title={`Размер ${sz}, полнота ${f} — открыть параметры`}
                                  className="btn text-xs w-full"
                                  onClick={() => onOpen(item)}>
                            {item.ball_girth_mm ? `${item.ball_girth_mm}` : '✓'}
                          </button>
                        ) : (
                          <span className="text-[color:var(--color-text-faint)]">—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-1 text-[11px] text-[color:var(--color-text-muted)]">
            В ячейке — обхват пучков, мм. Нажмите, чтобы открыть параметры колодки.
          </div>
        </div>
      )}
    </div>
  );
}

/** A single row in the article-number registry -- click to rename/relabel.
 * Renaming cascades on the backend (LastRepository.rename_article) so
 * existing scans filed under the old number stay grouped correctly. */
function ArticleRow({ article, onEdit }) {
  return (
    <button type="button" onClick={() => onEdit(article)}
            className="flex w-full items-center justify-between gap-2 rounded border border-[color:var(--color-border)] px-3 py-2 text-left text-sm hover:bg-[color:var(--color-surface-hover,rgba(0,0,0,0.03))]">
      <div>
        <span className="font-medium">{article.code}</span>
        {article.name && <span className="ml-2 text-[color:var(--color-text-muted)]">{article.name}</span>}
      </div>
      <Pencil size={14} className="text-[color:var(--color-text-muted)]" />
    </button>
  );
}

function ArticleEditModal({ article, isOpen, onClose, onSave, onDelete }) {
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const isNew = !article?.id;

  useEffect(() => {
    setCode(article?.code || '');
    setName(article?.name || '');
    setNote(article?.note || '');
  }, [article]);

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave({ id: article?.id, code, name, note });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <form className="modal-card w-full max-w-sm p-4 space-y-3" onSubmit={handleSubmit}>
        <div className="flex justify-between items-center">
          <h3 className="font-semibold">{isNew ? 'Новый номер колодки' : `Номер колодки ${article.code}`}</h3>
          <button type="button" className="btn" onClick={onClose}><X size={16} /></button>
        </div>
        <label className="block text-sm">
          Номер
          <input type="text" required className="input w-full mt-1" value={code}
            onChange={(e) => setCode(e.target.value)} />
        </label>
        <label className="block text-sm">
          Название (необязательно)
          <input type="text" className="input w-full mt-1" value={name}
            onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="block text-sm">
          Заметка
          <textarea className="input w-full mt-1" rows={2} value={note}
            onChange={(e) => setNote(e.target.value)} />
        </label>
        {!isNew && (
          <p className="text-xs text-[color:var(--color-text-muted)]">
            Переименование номера обновит его во всех уже добавленных колодках этой модели.
          </p>
        )}
        <div className="flex items-center justify-between gap-2">
          {!isNew ? (
            <button type="button" className="btn text-[color:var(--color-danger)] flex items-center gap-1.5"
                    onClick={() => onDelete(article.id)}>
              <Trash2 size={15} /> Удалить
            </button>
          ) : <span />}
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Сохраняю…' : 'Сохранить'}
          </button>
        </div>
      </form>
    </Modal>
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
  FIT_REQUIRES_DIFFERENT_FULLNESS: 'bg-sky-100 text-sky-900 border-sky-300',
  FIT_STRUCTURALLY_INCOMPATIBLE: 'bg-red-100 text-red-900 border-red-300',
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

function MatchCard({ match, onOpenImage, sharedTier }) {
  const [open, setOpen] = useState(true);
  const { last, per_foot } = match;
  return (
    <div className="app-card p-4 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-start gap-3">
          {match.tier != null && (
            <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[color:var(--color-bg-secondary)] text-sm font-semibold">
              {match.tier}
            </span>
          )}
        <div>
          {/* Size and fullness both belong in the heading: one model is
              graded across several of each, so a card headed by the article
              alone is indistinguishable from its five neighbours in the
              results list. */}
          <h4 className="font-semibold">
            {last.article || last.model || 'Без названия'}
            {last.size ? <span className="ml-1.5">· {last.size}</span> : null}
            {last.fullness
              ? <span className="ml-1.5">· полнота {last.fullness}</span>
              : <span className="ml-1.5 font-normal text-[color:var(--color-text-muted)]">· полнота не указана</span>}
          </h4>
          <div className="text-xs text-[color:var(--color-text-muted)]">
            {[last.model, last.material,
              last.side && (last.side === 'left' ? 'левая' : 'правая'),
              last.length_mm && `длина ${last.length_mm} мм`,
              last.ball_girth_mm && `обхват пучков ${last.ball_girth_mm} мм`,
            ].filter(Boolean).join(' · ') || '—'}
          </div>
          {/* Same tier means the difference between these lasts is smaller
              than the measurement can resolve -- saying "1st, 2nd" there would
              invent a winner. */}
          {sharedTier && (
            <div className="mt-1 text-[11px] text-[color:var(--color-text-muted)]">
              делит место с другими — разница между ними меньше точности измерения
            </div>
          )}
        </div>
        </div>
        <div className="flex items-center gap-2">
          {per_foot.map((pf, i) => (
            <span key={i} className="flex flex-col items-end gap-0.5">
              <span
                className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${HEADLINE_STYLE[pf.fit_result?.fit_class] || HEADLINE_STYLE.FIT_INDETERMINATE}`}>
                {pf.fit_result?.explanation?.headline || '—'}
              </span>
              {/* Within one verdict the list still has to say which is closer:
                  the worst single reading, in mm outside acceptable. */}
              {pf.fit_result?.worst_deviation_mm != null && (
                <span className="text-[11px] text-[color:var(--color-text-muted)]">
                  худшее отклонение {pf.fit_result.worst_deviation_mm} мм
                </span>
              )}
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
    article: '', size: '', fullness: '', model: '', material: '', note: '', side: '',
    heel_height_mm: '', toe_spring_mm: '',
  });
  const [addFile, setAddFile] = useState(null);

  const [matching, setMatching] = useState(false);
  const [matchResult, setMatchResult] = useState(null);
  const [matchFileLeft, setMatchFileLeft] = useState(null);
  const [matchFileRight, setMatchFileRight] = useState(null);
  const [swapSides, setSwapSides] = useState(false);
  const [lightbox, setLightbox] = useState(null);
  const [detailLast, setDetailLast] = useState(null);

  const [articles, setArticles] = useState([]);
  const [editingArticle, setEditingArticle] = useState(null); // {} for "new"

  async function loadArticles() {
    try {
      const res = await api.get('last-articles');
      setArticles(res.data.articles);
    } catch (err) {
      console.error(err);
    }
  }

  useEffect(() => { loadArticles(); }, []);

  async function handleSaveArticle({ id, code, name, note }) {
    try {
      const fd = new FormData();
      fd.append('code', code); fd.append('name', name); fd.append('note', note);
      if (id) {
        await api.patch(`last-articles/${id}`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      } else {
        await api.post('last-articles', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      }
      toast('Номер колодки сохранён', 'success');
      setEditingArticle(null);
      loadArticles();
      loadLasts();
    } catch (err) {
      console.error(err);
      toast(err.response?.data?.detail === 'code_already_exists' ? 'Такой номер уже есть' : 'Не удалось сохранить номер', 'error');
    }
  }

  async function handleDeleteArticle(id) {
    if (!window.confirm('Удалить этот номер из списка? Уже добавленные колодки не удалятся.')) return;
    try {
      await api.delete(`last-articles/${id}`);
      setEditingArticle(null);
      loadArticles();
    } catch (err) {
      console.error(err);
      toast('Не удалось удалить номер', 'error');
    }
  }

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
    if (!addFile) { toast('Выберите файл .stl колодки', 'error'); return; }
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
        article: '', size: '', fullness: '', model: '', material: '', note: '', side: '',
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

  async function handleSaveLast(id, form) {
    try {
      const fd = new FormData();
      Object.entries(form).forEach(([k, v]) => {
        if ((k === 'heel_height_mm' || k === 'toe_spring_mm') && v === '') return;
        fd.append(k, v);
      });
      const res = await api.patch(`lasts/${id}`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setLasts(prev => prev.map(l => (l.id === id ? res.data : l)));
      setDetailLast(res.data);
      toast('Колодка обновлена', 'success');
    } catch (err) {
      console.error(err);
      toast(err.response?.data?.detail || 'Не удалось сохранить изменения', 'error');
    }
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
    runMatchStl(matchFileLeft, matchFileRight, next);
  }

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Номера колодок ({articles.length})</h3>
          <button type="button" className="btn flex items-center gap-1.5" onClick={() => setEditingArticle({})}>
            <Plus size={16} /> Новый номер
          </button>
        </div>
        <p className="text-sm text-[color:var(--color-text-muted)]">
          Список номеров моделей колодок (например, 4977) — источник для выпадающего списка при добавлении колодки.
          Нажмите на номер, чтобы переименовать или удалить его из списка.
        </p>
        {articles.length === 0 ? (
          <div className="rounded border border-dashed border-[color:var(--color-border)] bg-[color:var(--color-surface)] p-4 text-center text-sm text-[color:var(--color-text-muted)]">
            Список пуст — добавьте первый номер колодки.
          </div>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {articles.map((a) => (
              <ArticleRow key={a.id} article={a} onEdit={setEditingArticle} />
            ))}
          </div>
        )}
      </section>

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
          <div className="space-y-3">
            {groupByModel(lasts).map((g) => (
              <LastFamily key={g.code} group={g} onOpen={setDetailLast} />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h3 className="font-semibold">Подбор колодки по скану стопы</h3>
        <p className="text-sm text-[color:var(--color-text-muted)]">
          Загрузите скан стопы клиента — система «вложит» стопу в каждую колодку, проверит посадку по всей длине
          (пятка, свод, подъём, пучки, носок) и объяснит по-человечески, где и чем колодка неудобна.
        </p>

        <div className="app-card p-4 space-y-3">
          <div className="font-medium text-sm">Загрузите .stl — отдельно левая и правая стопа</div>
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
                <h4 className="font-medium text-sm text-[color:var(--color-text-muted)]">
                Результат подбора (лучшее сверху) — сортировка по вердикту, затем по худшему отклонению
              </h4>
              </div>
              {matchResult.matches.map((m) => (
                <MatchCard key={m.last.id} match={m}
                  sharedTier={matchResult.matches.filter((o) => o.tier === m.tier).length > 1}
                  onOpenImage={(src, alt) => setLightbox({ src, alt })} />
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
            Файл скана (.stl)
            <input type="file" accept=".stl" required className="block w-full mt-1"
              onChange={(e) => setAddFile(e.target.files?.[0] || null)} />
          </label>
          <label className="block text-sm">
            Номер колодки
            <select className="input w-full mt-1" required value={form.article}
              onChange={(e) => setForm(f => ({ ...f, article: e.target.value }))}>
              <option value="" disabled>Выберите номер…</option>
              {articles.map((a) => (
                <option key={a.id} value={a.code}>{a.code}{a.name ? ` — ${a.name}` : ''}</option>
              ))}
            </select>
            {articles.length === 0 && (
              <span className="block text-xs text-[color:var(--color-text-muted)] mt-1">
                Список номеров пуст — сначала добавьте номер в разделе «Номера колодок» выше.
              </span>
            )}
          </label>
          {['size', 'fullness', 'model', 'material'].map((field) => (
            <label key={field} className="block text-sm">
              {{ size: 'Размер', fullness: 'Полнота', model: 'Модель', material: 'Материал' }[field]}
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

      <Modal isOpen={!!detailLast} onClose={() => setDetailLast(null)}>
        <LastDetail
          last={detailLast}
          articles={articles}
          onClose={() => setDetailLast(null)}
          onSave={handleSaveLast}
          onDelete={(id) => { setDetailLast(null); handleDelete(id); }}
        />
      </Modal>

      <ArticleEditModal
        article={editingArticle}
        isOpen={!!editingArticle}
        onClose={() => setEditingArticle(null)}
        onSave={handleSaveArticle}
        onDelete={handleDeleteArticle}
      />
    </div>
  );
}
