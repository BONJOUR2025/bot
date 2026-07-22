import { useEffect, useState } from 'react';
import { Upload, Trash2, Plus, X, ChevronDown, ChevronUp } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import Modal from '../components/Modal.jsx';
import { FootCard, SIDE_LABEL } from '../components/FootScanCard.jsx';

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
  loose: { label: 'Подойдёт, но свободна', cls: 'bg-amber-100 text-amber-800 border-amber-300' },
  not_fit: { label: 'Не подойдёт', cls: 'bg-red-100 text-red-800 border-red-300' },
};

const ZONE_DOT = {
  too_tight: 'bg-red-500', tight_ok: 'bg-amber-500', ideal: 'bg-green-500',
  loose_ok: 'bg-amber-400', too_loose: 'bg-amber-500',
};

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
  const [form, setForm] = useState({ article: '', size: '', model: '', material: '', note: '' });
  const [addFile, setAddFile] = useState(null);

  const [matching, setMatching] = useState(false);
  const [matchResult, setMatchResult] = useState(null);
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
    if (!addFile) { toast('Выберите файл .scm колодки', 'error'); return; }
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append('file', addFile);
      Object.entries(form).forEach(([k, v]) => fd.append(k, v));
      await api.post('lasts', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast('Колодка добавлена', 'success');
      setAddOpen(false);
      setForm({ article: '', size: '', model: '', material: '', note: '' });
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

  async function handleMatchFile(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.scm')) { toast('Ожидается файл .scm', 'error'); return; }
    setMatching(true);
    setMatchResult(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
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

        {matching && <p className="text-sm text-[color:var(--color-text-muted)]">Сравниваю с библиотекой…</p>}

        {matchResult && (
          <div className="space-y-6">
            <div className="grid gap-4 lg:grid-cols-2">
              {matchResult.feet.map((foot, i) => (
                <FootCard key={i} foot={foot} index={i} onOpenImage={(src, alt) => setLightbox({ src, alt })} />
              ))}
            </div>
            <div className="space-y-3">
              <h4 className="font-medium text-sm text-[color:var(--color-text-muted)]">Результат подбора (лучшее сверху)</h4>
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
            Файл скана (.scm)
            <input type="file" accept=".scm" required className="block w-full mt-1"
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
