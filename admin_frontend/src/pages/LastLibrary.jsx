import { useEffect, useState } from 'react';
import { Upload, Trash2, Plus, X, ChevronDown, ChevronUp } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import Modal from '../components/Modal.jsx';
import { FootCard, ViewThumb, SIDE_LABEL } from './Scanner3D.jsx';

const BLOCK_SIDE_LABEL = { ...SIDE_LABEL, null: 'Колодка' };

function BlockStats({ block }) {
  return (
    <div className="grid grid-cols-4 gap-2 text-center text-xs">
      <div><div className="font-semibold text-sm">{block.length_mm}</div>длина</div>
      <div><div className="font-semibold text-sm">{block.width_mm}</div>ширина</div>
      <div><div className="font-semibold text-sm">{block.height_mm}</div>высота</div>
      <div><div className="font-semibold text-sm">{block.ball_girth_mm ?? '—'}</div>пучки</div>
    </div>
  );
}

function LastCard({ last, onDelete }) {
  return (
    <div className="app-card p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">{last.article || last.model || 'Без названия'}</h3>
          <div className="text-xs text-[color:var(--color-text-muted)]">
            {[last.model, last.size && `размер ${last.size}`, last.material].filter(Boolean).join(' · ') || '—'}
          </div>
        </div>
        <button type="button" className="btn btn-ghost text-[color:var(--color-danger)]" title="Удалить" onClick={() => onDelete(last.id)}>
          <Trash2 size={16} />
        </button>
      </div>
      {last.note && <p className="text-xs text-[color:var(--color-text-muted)]">{last.note}</p>}
      <div className="space-y-2">
        {last.blocks.map((block, i) => (
          <div key={i} className="rounded border border-[color:var(--color-border)] p-2">
            <div className="text-xs font-medium mb-1">{BLOCK_SIDE_LABEL[block.side] || `Колодка ${i + 1}`}</div>
            <BlockStats block={block} />
          </div>
        ))}
      </div>
    </div>
  );
}

const VERDICT_STYLE = {
  good: { label: 'Хорошо подойдёт', className: 'bg-green-100 text-green-800 border-green-300' },
  ok: { label: 'В целом подойдёт', className: 'bg-blue-100 text-blue-800 border-blue-300' },
  loose: { label: 'Свободнее нужного', className: 'bg-amber-100 text-amber-800 border-amber-300' },
  not_fit: { label: 'Не подойдёт', className: 'bg-red-100 text-red-800 border-red-300' },
};

const METRIC_VERDICT_STYLE = {
  too_tight: 'text-red-700',
  tight_ok: 'text-amber-700',
  ideal: 'text-green-700',
  loose_ok: 'text-amber-700',
  too_loose: 'text-red-700',
};

function FitBadge({ overall }) {
  const s = VERDICT_STYLE[overall] || VERDICT_STYLE.ok;
  return <span className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${s.className}`}>{s.label}</span>;
}

function MatchCard({ match }) {
  const [expanded, setExpanded] = useState(false);
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
        <button type="button" className="btn" onClick={() => setExpanded(e => !e)}>
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>
      <div className="flex flex-wrap gap-2">
        {per_foot.map((pf, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <span className="text-xs text-[color:var(--color-text-muted)]">{SIDE_LABEL[pf.foot_side] || 'Стопа'}:</span>
            <FitBadge overall={pf.fit.overall} />
          </div>
        ))}
      </div>
      {expanded && (
        <div className="space-y-3 pt-2 border-t border-[color:var(--color-border)]">
          {per_foot.map((pf, i) => (
            <div key={i} className="space-y-1">
              <div className="text-xs font-medium">{SIDE_LABEL[pf.foot_side] || 'Стопа'}</div>
              <p className="text-xs text-[color:var(--color-text-muted)]">{pf.fit.overall_text}</p>
              {pf.fit.metrics.map((m) => (
                <div key={m.metric} className={`text-xs ${METRIC_VERDICT_STYLE[m.verdict]}`}>
                  {m.label}: стопа {m.foot_mm} мм → колодка {m.last_mm} мм (запас {m.delta_mm > 0 ? '+' : ''}{m.delta_mm} мм)
                </div>
              ))}
              <div className="text-[11px] text-[color:var(--color-text-muted)]">
                Ширина (справочно, не входит в вердикт): стопа {pf.fit.width_advisory.foot_mm} мм · колодка {pf.fit.width_advisory.last_mm} мм
              </div>
            </div>
          ))}
        </div>
      )}
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
    if (!addFile) {
      toast('Выберите файл .scm колодки', 'error');
      return;
    }
    setSaving(true);
    try {
      const formData = new FormData();
      formData.append('file', addFile);
      Object.entries(form).forEach(([k, v]) => formData.append(k, v));
      await api.post('lasts', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast('Колодка добавлена в библиотеку', 'success');
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
    if (!file.name.toLowerCase().endsWith('.scm')) {
      toast('Ожидается файл .scm', 'error');
      return;
    }
    setMatching(true);
    setMatchResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('lasts/match', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      setMatchResult(res.data);
      if (!res.data.matches.length) {
        toast(lasts.length ? 'Ни одна колодка не подошла по геометрии сторон' : 'Библиотека колодок пуста', 'error');
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
          Загрузите скан стопы клиента — система сравнит его с каждой колодкой в библиотеке по длине и обхвату
          пучков (с учётом принятых в колодочном деле припусков) и покажет, какая колодка подойдёт и почему.
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
              <h4 className="font-medium text-sm text-[color:var(--color-text-muted)]">
                Результат подбора (лучшие варианты сверху)
              </h4>
              {matchResult.matches.map((m) => <MatchCard key={m.last.id} match={m} />)}
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
          <label className="block text-sm">
            Файл скана (.scm)
            <input
              type="file" accept=".scm" required className="block w-full mt-1"
              onChange={(e) => setAddFile(e.target.files?.[0] || null)}
            />
          </label>
          {['article', 'model', 'size', 'material'].map((field) => (
            <label key={field} className="block text-sm">
              {{ article: 'Артикул', model: 'Модель', size: 'Размер', material: 'Материал' }[field]}
              <input
                type="text" className="input w-full mt-1" value={form[field]}
                onChange={(e) => setForm(f => ({ ...f, [field]: e.target.value }))}
              />
            </label>
          ))}
          <label className="block text-sm">
            Заметка
            <textarea
              className="input w-full mt-1" rows={2} value={form.note}
              onChange={(e) => setForm(f => ({ ...f, note: e.target.value }))}
            />
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
          {lightbox && (
            <img src={lightbox.src} alt={lightbox.alt} className="block max-w-full max-h-[80vh] mx-auto rounded" />
          )}
        </div>
      </Modal>
    </div>
  );
}
