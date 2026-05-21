import { useState, useEffect, useCallback } from 'react';
import {
  Plus, X, Phone, Mail, FileText,
  Briefcase, ExternalLink, Pencil, Trash2,
} from 'lucide-react';
import api from '../api';
import { useViewport } from '../providers/ViewportProvider.jsx';

const STAGES = [
  { key: 'отклик',        label: 'Отклик',        color: 'bg-blue-100 text-blue-700',       dot: 'bg-blue-400',     border: 'border-t-blue-400'   },
  { key: 'собеседование', label: 'Собеседование',  color: 'bg-violet-100 text-violet-700',   dot: 'bg-violet-400',   border: 'border-t-violet-400' },
  { key: 'ждем',          label: 'Ожидание',       color: 'bg-amber-100 text-amber-700',     dot: 'bg-amber-400',    border: 'border-t-amber-400'  },
  { key: 'отказ',         label: 'Отказ',          color: 'bg-red-100 text-red-700',         dot: 'bg-red-400',      border: 'border-t-red-400'    },
  { key: 'нанят',         label: 'Нанят ✓',        color: 'bg-emerald-100 text-emerald-700', dot: 'bg-emerald-400',  border: 'border-t-emerald-400'},
];

const SOURCES = [
  { key: 'manual', label: 'Вручную' },
  { key: 'hh',     label: 'hh.ru'   },
  { key: 'avito',  label: 'Авито'   },
  { key: 'other',  label: 'Другое'  },
];

const stageOf   = (key) => STAGES.find(s => s.key === key) || STAGES[0];
const srcLabel  = (key) => SOURCES.find(s => s.key === key)?.label || key;
const fmtDate   = (iso) => iso ? new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }) : '';

const SRC_BADGE = {
  hh:     'bg-red-100 text-red-600',
  avito:  'bg-green-100 text-green-600',
  manual: 'bg-gray-100 text-gray-500',
  other:  'bg-gray-100 text-gray-500',
};
const srcBadgeLabel = (s) => s === 'manual' ? 'руч.' : s;

// ── Vacancy modal ──────────────────────────────────────────────────
function VacancyModal({ vacancy, onClose, onSave }) {
  const [title, setTitle]       = useState(vacancy?.title || '');
  const [description, setDesc]  = useState(vacancy?.description || '');
  const [saving, setSaving]     = useState(false);

  async function save() {
    if (!title.trim()) return;
    setSaving(true);
    try {
      const payload = { title, description };
      const res = vacancy
        ? await api.patch(`/recruitment/vacancies/${vacancy.id}`, payload)
        : await api.post('/recruitment/vacancies', payload);
      onSave(res.data);
      onClose();
    } finally { setSaving(false); }
  }

  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-md w-full">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold">{vacancy ? 'Редактировать вакансию' : 'Новая вакансия'}</h3>
          <button onClick={onClose} className="text-xl text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] leading-none">&times;</button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Название *</label>
            <input className="input w-full" value={title} onChange={e => setTitle(e.target.value)}
              placeholder="Мастер по ремонту обуви" autoFocus onKeyDown={e => e.key === 'Enter' && save()} />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Описание (необязательно)</label>
            <textarea className="input w-full min-h-[72px] resize-none" value={description}
              onChange={e => setDesc(e.target.value)} placeholder="Требования, условия..." />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="btn btn-secondary">Отмена</button>
          <button onClick={save} disabled={saving || !title.trim()} className="btn btn-primary">
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Candidate modal ────────────────────────────────────────────────
function CandidateModal({ candidate, vacancyId, initialStage, onClose, onSave }) {
  const [form, setForm] = useState({
    name:   candidate?.name   || '',
    phone:  candidate?.phone  || '',
    email:  candidate?.email  || '',
    source: candidate?.source || 'manual',
    stage:  candidate?.stage  || initialStage || 'отклик',
    notes:  candidate?.notes  || '',
  });
  const [saving, setSaving] = useState(false);
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));

  async function save() {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const res = candidate
        ? await api.patch(`/recruitment/candidates/${candidate.id}`, form)
        : await api.post('/recruitment/candidates', { ...form, vacancy_id: vacancyId });
      onSave(res.data);
      onClose();
    } finally { setSaving(false); }
  }

  return (
    <div className="modal-backdrop" style={{ zIndex: 60 }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-md w-full flex flex-col overflow-hidden">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold">{candidate ? 'Редактировать кандидата' : 'Добавить кандидата'}</h3>
          <button onClick={onClose} className="text-xl text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] leading-none">&times;</button>
        </div>
        <div className="space-y-3 overflow-y-auto flex-1">
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Имя *</label>
            <input className="input w-full" value={form.name} onChange={set('name')} placeholder="Иван Иванов" autoFocus />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Телефон</label>
              <input className="input w-full" value={form.phone} onChange={set('phone')} placeholder="+7..." />
            </div>
            <div>
              <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Email</label>
              <input className="input w-full" value={form.email} onChange={set('email')} placeholder="mail@..." />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Источник</label>
              <select className="input w-full" value={form.source} onChange={set('source')}>
                {SOURCES.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Этап</label>
              <select className="input w-full" value={form.stage} onChange={set('stage')}>
                {STAGES.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Заметки</label>
            <textarea className="input w-full min-h-[80px] resize-none" value={form.notes}
              onChange={set('notes')} placeholder="Опыт, впечатления от звонка..." />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="btn btn-secondary">Отмена</button>
          <button onClick={save} disabled={saving || !form.name.trim()} className="btn btn-primary">
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Candidate detail modal ─────────────────────────────────────────
function CandidateDetail({ candidate, onClose, onEdit, onDelete, onStageChange }) {
  const stage = stageOf(candidate.stage);

  return (
    <div className="modal-backdrop" style={{ zIndex: 60 }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-sm w-full flex flex-col overflow-hidden">
        <div className="flex items-start justify-between mb-4">
          <div className="min-w-0">
            <h3 className="text-base font-semibold">{candidate.name}</h3>
            <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full mt-1 ${stage.color}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${stage.dot}`} />
              {stage.label}
            </span>
          </div>
          <button onClick={onClose} className="text-xl text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] leading-none ml-3">&times;</button>
        </div>

        <div className="space-y-2.5 flex-1 overflow-y-auto text-sm">
          {candidate.phone && (
            <div className="flex items-center gap-2">
              <Phone size={14} className="text-[color:var(--color-muted-foreground)] flex-shrink-0" />
              <a href={`tel:${candidate.phone}`} className="text-[color:var(--color-primary)] hover:underline">{candidate.phone}</a>
            </div>
          )}
          {candidate.email && (
            <div className="flex items-center gap-2">
              <Mail size={14} className="text-[color:var(--color-muted-foreground)] flex-shrink-0" />
              <a href={`mailto:${candidate.email}`} className="text-[color:var(--color-primary)] hover:underline">{candidate.email}</a>
            </div>
          )}
          <div className="flex items-center gap-2 text-[color:var(--color-muted-foreground)]">
            <ExternalLink size={14} className="flex-shrink-0" />
            <span>{srcLabel(candidate.source)}</span>
            <span className="opacity-50">·</span>
            <span>{fmtDate(candidate.created_at)}</span>
          </div>

          {candidate.notes && (
            <div className="mt-1 p-3 rounded-xl bg-[color:var(--color-muted)]/30 border border-[color:var(--color-border)]">
              <div className="flex items-center gap-1.5 text-xs text-[color:var(--color-muted-foreground)] mb-1.5">
                <FileText size={12} /> Заметки
              </div>
              <p className="text-sm whitespace-pre-wrap">{candidate.notes}</p>
            </div>
          )}

          <div className="mt-3 pt-3 border-t border-[color:var(--color-border)]">
            <p className="text-xs text-[color:var(--color-muted-foreground)] mb-2">Перевести в этап:</p>
            <div className="flex flex-wrap gap-1.5">
              {STAGES.map(s => (
                <button
                  key={s.key}
                  onClick={() => { onStageChange(candidate.id, s.key); onClose(); }}
                  disabled={s.key === candidate.stage}
                  className={`text-xs px-2.5 py-1 rounded-full font-medium transition-opacity ${s.color} ${
                    s.key === candidate.stage ? 'opacity-40 cursor-default' : 'hover:opacity-75'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between mt-5 pt-4 border-t border-[color:var(--color-border)]">
          <button onClick={() => { onDelete(candidate.id); onClose(); }}
            className="flex items-center gap-1.5 text-sm text-red-500 hover:text-red-700">
            <Trash2 size={14} /> Удалить
          </button>
          <button onClick={() => { onClose(); onEdit(candidate); }} className="btn btn-primary text-sm flex items-center gap-1.5">
            <Pencil size={14} /> Редактировать
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Kanban card ────────────────────────────────────────────────────
function CandidateCard({ c, onClick }) {
  return (
    <button
      onClick={() => onClick(c)}
      className="w-full text-left bg-white border border-[color:var(--color-border)] rounded-xl px-3 py-2.5 shadow-sm hover:shadow-md hover:border-[color:var(--color-primary)]/40 transition-all group"
    >
      <div className="flex items-start justify-between gap-1">
        <span className="text-sm font-medium leading-snug group-hover:text-[color:var(--color-primary)] transition-colors">
          {c.name}
        </span>
        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full flex-shrink-0 mt-0.5 ${SRC_BADGE[c.source] || SRC_BADGE.other}`}>
          {srcBadgeLabel(c.source)}
        </span>
      </div>
      {c.phone && (
        <div className="flex items-center gap-1 mt-1.5 text-xs text-[color:var(--color-muted-foreground)]">
          <Phone size={10} /> {c.phone}
        </div>
      )}
      {c.notes && (
        <p className="mt-1.5 text-xs text-[color:var(--color-muted-foreground)] line-clamp-2">{c.notes}</p>
      )}
      <div className="mt-1.5 text-[10px] text-[color:var(--color-muted-foreground)] opacity-60">{fmtDate(c.created_at)}</div>
    </button>
  );
}

// ── Kanban board (desktop) ─────────────────────────────────────────
function KanbanBoard({ candidates, onCardClick, onAddClick }) {
  return (
    <div className="overflow-x-auto pb-4">
      <div className="flex gap-4 min-w-max">
        {STAGES.map(stage => {
          const cards = candidates.filter(c => c.stage === stage.key);
          return (
            <div key={stage.key} className="w-[230px] flex flex-col">
              <div className="flex items-center justify-between mb-3 px-0.5">
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${stage.dot}`} />
                  <span className="text-sm font-semibold">{stage.label}</span>
                  <span className="text-[10px] text-[color:var(--color-muted-foreground)] bg-[color:var(--color-muted)]/60 rounded-full px-1.5 py-0.5 min-w-[20px] text-center">
                    {cards.length}
                  </span>
                </div>
                <button
                  onClick={() => onAddClick(stage.key)}
                  title={`Добавить в «${stage.label}»`}
                  className="w-6 h-6 flex items-center justify-center rounded-lg text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-muted)] hover:text-[color:var(--color-foreground)] transition-colors"
                >
                  <Plus size={14} />
                </button>
              </div>

              <div className={`flex-1 rounded-xl border-t-2 ${stage.border} bg-[color:var(--color-muted)]/20 p-2 flex flex-col gap-2 min-h-[120px]`}>
                {cards.map(c => <CandidateCard key={c.id} c={c} onClick={onCardClick} />)}
                {cards.length === 0 && (
                  <button
                    onClick={() => onAddClick(stage.key)}
                    className="flex-1 flex items-center justify-center text-xs text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-primary)] cursor-pointer transition-colors rounded-lg py-4"
                  >
                    + добавить
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Mobile board (tabs + list) ─────────────────────────────────────
function MobileBoard({ candidates, onCardClick, onAddClick }) {
  const [activeStage, setActiveStage] = useState('отклик');
  const stage = stageOf(activeStage);
  const filtered = candidates.filter(c => c.stage === activeStage);

  return (
    <div className="space-y-3">
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {STAGES.map(s => {
          const count = candidates.filter(c => c.stage === s.key).length;
          const active = s.key === activeStage;
          return (
            <button
              key={s.key}
              onClick={() => setActiveStage(s.key)}
              className={`flex-shrink-0 flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full transition-all ${
                active ? s.color + ' shadow-sm' : 'bg-[color:var(--color-muted)]/40 text-[color:var(--color-muted-foreground)]'
              }`}
            >
              {s.label}
              <span className={`text-[10px] min-w-[16px] text-center rounded-full px-1 ${active ? 'bg-white/50' : ''}`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      <div className="space-y-2">
        {filtered.map(c => <CandidateCard key={c.id} c={c} onClick={onCardClick} />)}
        {filtered.length === 0 && (
          <div className="text-center py-8 text-sm text-[color:var(--color-muted-foreground)] italic">
            Нет кандидатов в этапе «{stage.label}»
          </div>
        )}
      </div>

      <button onClick={() => onAddClick(activeStage)} className="w-full btn btn-secondary text-sm flex items-center justify-center gap-2">
        <Plus size={16} /> Добавить кандидата
      </button>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────
export default function Recruitment() {
  const { isMobile } = useViewport();
  const [vacancies,    setVacancies]    = useState([]);
  const [selectedId,   setSelectedId]   = useState(null);
  const [candidates,   setCandidates]   = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [cLoading,     setCLoading]     = useState(false);
  const [showClosed,   setShowClosed]   = useState(false);
  const [error,        setError]        = useState(null);
  const [vacancyModal, setVacancyModal] = useState(null); // null | 'new' | vacancy
  const [candModal,    setCandModal]    = useState(null); // null | { candidate?, stage }
  const [detailModal,  setDetailModal]  = useState(null); // candidate
  const [showVacList,  setShowVacList]  = useState(!isMobile);

  const loadVacancies = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/recruitment/vacancies', { params: { include_closed: showClosed } });
      setVacancies(res.data);
      setSelectedId(id => id || res.data[0]?.id || null);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [showClosed]);

  useEffect(() => { loadVacancies(); }, [loadVacancies]);

  const loadCandidates = useCallback(async () => {
    if (!selectedId) { setCandidates([]); return; }
    setCLoading(true);
    try {
      const res = await api.get('/recruitment/candidates', { params: { vacancy_id: selectedId } });
      setCandidates(res.data);
    } catch (e) { setError(e.message); }
    finally { setCLoading(false); }
  }, [selectedId]);

  useEffect(() => { loadCandidates(); }, [loadCandidates]);

  async function toggleVacancy(v) {
    try {
      const res = await api.patch(`/recruitment/vacancies/${v.id}`, { is_open: !v.is_open });
      setVacancies(prev => prev.map(x => x.id === v.id ? { ...x, ...res.data } : x));
    } catch (e) { setError(e.message); }
  }

  async function deleteVacancy(id) {
    if (!window.confirm('Удалить вакансию со всеми кандидатами?')) return;
    try {
      await api.delete(`/recruitment/vacancies/${id}`);
      setVacancies(prev => prev.filter(v => v.id !== id));
      if (selectedId === id) setSelectedId(vacancies.find(v => v.id !== id)?.id || null);
    } catch (e) { setError(e.message); }
  }

  function handleVacancySaved(saved) {
    setVacancies(prev => {
      const exists = prev.find(v => v.id === saved.id);
      if (exists) return prev.map(v => v.id === saved.id ? { ...v, ...saved } : v);
      return [saved, ...prev];
    });
    setSelectedId(saved.id);
  }

  function handleCandSaved(saved) {
    setCandidates(prev => {
      const exists = prev.find(c => c.id === saved.id);
      return exists ? prev.map(c => c.id === saved.id ? saved : c) : [...prev, saved];
    });
  }

  async function deleteCandidate(id) {
    try {
      await api.delete(`/recruitment/candidates/${id}`);
      setCandidates(prev => prev.filter(c => c.id !== id));
    } catch (e) { setError(e.message); }
  }

  async function stageChange(candidateId, newStage) {
    try {
      const res = await api.patch(`/recruitment/candidates/${candidateId}`, { stage: newStage });
      setCandidates(prev => prev.map(c => c.id === candidateId ? res.data : c));
    } catch (e) { setError(e.message); }
  }

  const selected = vacancies.find(v => v.id === selectedId);

  return (
    <div className="space-y-0 -mx-6 sm:-mx-10 -mt-8" style={{ marginBottom: '-3rem' }}>
      {/* Page header */}
      <div className="px-6 sm:px-10 pt-6 pb-4 border-b border-[color:var(--color-border)] flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-bold">Подбор персонала</h1>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">CRM кандидатов по вакансиям</p>
        </div>
        <div className="flex items-center gap-2">
          {isMobile && (
            <button onClick={() => setShowVacList(v => !v)} className="btn btn-secondary text-sm">
              {showVacList ? 'Скрыть вакансии' : 'Вакансии'}
            </button>
          )}
          <button onClick={() => setVacancyModal('new')} className="btn btn-primary text-sm flex items-center gap-1.5">
            <Plus size={15} /> Вакансия
          </button>
        </div>
      </div>

      {error && (
        <div className="mx-6 sm:mx-10 mt-3 rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600 flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)}><X size={14} /></button>
        </div>
      )}

      {/* Two-panel layout */}
      <div className={`flex ${isMobile ? 'flex-col' : ''} gap-0`}>
        {/* Left — vacancy list */}
        {(!isMobile || showVacList) && (
          <aside className={`flex-shrink-0 border-b sm:border-b-0 sm:border-r border-[color:var(--color-border)] bg-[color:var(--color-muted)]/10 ${isMobile ? 'w-full' : 'w-60'}`}>
            <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
              <label className="flex items-center gap-2 text-xs text-[color:var(--color-muted-foreground)] cursor-pointer">
                <input type="checkbox" checked={showClosed} onChange={e => setShowClosed(e.target.checked)} className="rounded" />
                Показать закрытые
              </label>
            </div>
            {loading ? (
              <div className="py-8 text-center text-sm text-[color:var(--color-muted-foreground)]">Загрузка...</div>
            ) : vacancies.length === 0 ? (
              <div className="py-10 px-4 text-center">
                <Briefcase size={28} className="mx-auto mb-2 opacity-20" />
                <p className="text-sm text-[color:var(--color-muted-foreground)]">Нет вакансий</p>
                <button onClick={() => setVacancyModal('new')} className="mt-1 text-xs text-[color:var(--color-primary)] hover:underline">
                  + Создать первую
                </button>
              </div>
            ) : (
              <div className={isMobile ? 'flex overflow-x-auto gap-2 p-3' : ''}>
                {vacancies.map(v => (
                  isMobile ? (
                    <button
                      key={v.id}
                      onClick={() => { setSelectedId(v.id); setShowVacList(false); }}
                      className={`flex-shrink-0 text-left rounded-xl border px-3 py-2 text-sm transition-all ${
                        v.id === selectedId
                          ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)]/8 font-semibold'
                          : 'border-[color:var(--color-border)] bg-white'
                      }`}
                    >
                      <div className="whitespace-nowrap font-medium">{v.title}</div>
                      <div className="text-[10px] text-[color:var(--color-muted-foreground)] mt-0.5">
                        {v.candidate_count} чел. · {v.is_open ? 'Открыта' : 'Закрыта'}
                      </div>
                    </button>
                  ) : (
                    <div
                      key={v.id}
                      onClick={() => setSelectedId(v.id)}
                      className={`group relative cursor-pointer px-4 py-3 border-b border-[color:var(--color-border)]/50 transition-colors ${
                        v.id === selectedId
                          ? 'bg-[color:var(--color-primary)]/8 border-l-2 border-l-[color:var(--color-primary)]'
                          : 'hover:bg-[color:var(--color-muted)]/30'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-1">
                        <div className="min-w-0">
                          <p className={`text-sm font-medium truncate ${!v.is_open ? 'text-[color:var(--color-muted-foreground)]' : ''}`}>{v.title}</p>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${v.is_open ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>
                              {v.is_open ? 'Открыта' : 'Закрыта'}
                            </span>
                            <span className="text-[10px] text-[color:var(--color-muted-foreground)]">{v.candidate_count} чел.</span>
                          </div>
                        </div>
                        <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                          <button onClick={e => { e.stopPropagation(); setVacancyModal(v); }}
                            className="w-6 h-6 flex items-center justify-center rounded hover:bg-[color:var(--color-muted)] text-[color:var(--color-muted-foreground)]">
                            <Pencil size={11} />
                          </button>
                          <button onClick={e => { e.stopPropagation(); deleteVacancy(v.id); }}
                            className="w-6 h-6 flex items-center justify-center rounded hover:bg-red-50 text-red-400">
                            <Trash2 size={11} />
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                ))}
              </div>
            )}
          </aside>
        )}

        {/* Right — kanban / board */}
        <div className="flex-1 min-w-0">
          {/* Board header */}
          {selected && (
            <div className="px-5 py-3 border-b border-[color:var(--color-border)] flex items-center justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <h2 className="font-bold text-base truncate">{selected.title}</h2>
                {selected.description && (
                  <p className="text-xs text-[color:var(--color-muted-foreground)] truncate">{selected.description}</p>
                )}
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={() => toggleVacancy(selected)}
                  className={`text-xs font-medium px-3 py-1.5 rounded-full transition-colors ${
                    selected.is_open
                      ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200'
                      : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                  }`}
                >
                  {selected.is_open ? '● Открыта' : '○ Закрыта'}
                </button>
                <button
                  onClick={() => setCandModal({ stage: 'отклик' })}
                  className="btn btn-primary text-sm flex items-center gap-1.5"
                >
                  <Plus size={15} /> Кандидат
                </button>
              </div>
            </div>
          )}

          <div className="p-4 sm:p-5">
            {!selected ? (
              <div className="flex flex-col items-center justify-center py-20 text-[color:var(--color-muted-foreground)]">
                <Briefcase size={44} className="mb-3 opacity-20" />
                <p className="text-sm">Выберите вакансию</p>
              </div>
            ) : cLoading ? (
              <div className="text-center py-16 text-sm text-[color:var(--color-muted-foreground)]">Загрузка...</div>
            ) : isMobile ? (
              <MobileBoard
                candidates={candidates}
                onCardClick={c => setDetailModal(c)}
                onAddClick={stage => setCandModal({ stage })}
              />
            ) : (
              <KanbanBoard
                candidates={candidates}
                onCardClick={c => setDetailModal(c)}
                onAddClick={stage => setCandModal({ stage })}
              />
            )}
          </div>
        </div>
      </div>

      {/* Modals */}
      {vacancyModal && (
        <VacancyModal
          vacancy={vacancyModal === 'new' ? null : vacancyModal}
          onClose={() => setVacancyModal(null)}
          onSave={handleVacancySaved}
        />
      )}

      {candModal && selectedId && (
        <CandidateModal
          candidate={candModal.candidate}
          vacancyId={selectedId}
          initialStage={candModal.stage}
          onClose={() => setCandModal(null)}
          onSave={handleCandSaved}
        />
      )}

      {detailModal && (
        <CandidateDetail
          candidate={detailModal}
          onClose={() => setDetailModal(null)}
          onEdit={c => setCandModal({ candidate: c })}
          onDelete={deleteCandidate}
          onStageChange={stageChange}
        />
      )}
    </div>
  );
}
