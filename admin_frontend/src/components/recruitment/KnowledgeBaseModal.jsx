import { useState, useEffect, useCallback } from 'react';
import { Plus, Pencil, Trash2, Loader2 } from 'lucide-react';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';
import ScopeBadge from './ScopeBadge.jsx';
import AiCheckPanel from './AiCheckPanel.jsx';
import useAiCheckGate from './useAiCheckGate.js';

// entry: null (new) | object (edit)
function EntryForm({ entry, scope, vacancyId, vacancyTitle, onClose, onSaved }) {
  const { toast } = useToast();
  const [category, setCategory] = useState(entry?.category || '');
  const [question, setQuestion] = useState(entry?.question || '');
  const [answer, setAnswer]     = useState(entry?.answer || '');
  const [saving, setSaving]     = useState(false);
  const gate = useAiCheckGate();

  function handleAnswerChange(e) {
    setAnswer(e.target.value);
    gate.invalidate();
  }

  async function save() {
    if (!question.trim() || !answer.trim()) return;
    if (!gate.isConfirmable(answer)) return;
    setSaving(true);
    try {
      const payload = { scope, vacancy_id: scope === 'vacancy' ? vacancyId : null, category: category.trim() || null, question: question.trim(), answer: answer.trim(), confirmed: true };
      const res = entry
        ? await api.patch(`/recruitment/knowledge-base/${entry.id}`, payload)
        : await api.post('/recruitment/knowledge-base', payload);
      onSaved(res.data);
      onClose();
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally { setSaving(false); }
  }

  return (
    <div className="modal-backdrop" style={{ zIndex: 95 }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-md w-full">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-semibold">{entry ? 'Редактировать запись' : 'Новая запись базы знаний'}</h3>
          <button onClick={onClose} className="text-xl text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] leading-none">&times;</button>
        </div>
        <div className="mb-3"><ScopeBadge scope={scope} vacancyTitle={vacancyTitle} /></div>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Категория (необязательно)</label>
            <input className="input w-full" value={category} onChange={e => setCategory(e.target.value)} placeholder="График работы" />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Вопрос *</label>
            <input className="input w-full" value={question} onChange={e => setQuestion(e.target.value)} placeholder="Какой график работы?" autoFocus />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Ответ *</label>
            <textarea className="input w-full min-h-[80px] resize-y text-sm" value={answer} onChange={handleAnswerChange} placeholder="5/2, с 9:00 до 18:00" />
          </div>
          <AiCheckPanel
            gate={gate}
            text={answer}
            scope={scope}
            vacancyId={vacancyId}
            fieldLabel={question || 'запись базы знаний'}
            onConfirm={save}
            confirming={saving}
          />
        </div>
      </div>
    </div>
  );
}

function EntryRow({ entry, onEdit, onDelete }) {
  return (
    <div className="rounded-xl border border-[color:var(--color-border)] p-3 space-y-1.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <ScopeBadge scope={entry.scope} vacancyTitle={entry.vacancy_title} />
            {entry.category && (
              <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-[color:var(--color-bg-secondary)] text-[color:var(--color-muted-foreground)]">
                {entry.category}
              </span>
            )}
          </div>
          <p className="text-sm font-medium">{entry.question}</p>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5 whitespace-pre-wrap">{entry.answer}</p>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <button onClick={() => onEdit(entry)} className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-[color:var(--color-muted)] text-[color:var(--color-muted-foreground)]">
            <Pencil size={13} />
          </button>
          <button onClick={() => onDelete(entry)} className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-red-50 text-red-400">
            <Trash2 size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}

// scope: "global" -> manage global entries only (with browse of all vacancy entries optionally hidden);
// scope: "vacancy" -> manage entries for the given vacancyId (vacancyTitle required for badges).
export default function KnowledgeBaseModal({ scope, vacancyId, vacancyTitle, onClose }) {
  const { toast } = useToast();
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(null); // null | 'new' | entry

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = scope === 'vacancy' ? { scope: 'vacancy', vacancy_id: vacancyId } : { scope: 'global' };
      const res = await api.get('/recruitment/knowledge-base', { params });
      setEntries(res.data || []);
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally { setLoading(false); }
  }, [scope, vacancyId, toast]);

  useEffect(() => { load(); }, [load]);

  function handleSaved(saved) {
    setEntries(prev => {
      const exists = prev.find(e => e.id === saved.id);
      return exists ? prev.map(e => e.id === saved.id ? saved : e) : [saved, ...prev];
    });
  }

  async function handleDelete(entry) {
    if (!window.confirm(`Удалить запись «${entry.question}»?`)) return;
    try {
      await api.delete(`/recruitment/knowledge-base/${entry.id}`);
      setEntries(prev => prev.filter(e => e.id !== entry.id));
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    }
  }

  return (
    <div className="modal-backdrop" style={{ zIndex: 80 }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-xl w-full flex flex-col overflow-hidden" style={{ maxHeight: '85vh' }}>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-base font-semibold">
            {scope === 'global' ? 'Общая база знаний' : `База знаний вакансии «${vacancyTitle}»`}
          </h3>
          <button onClick={onClose} className="text-xl text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] leading-none">&times;</button>
        </div>
        <div className="mb-3"><ScopeBadge scope={scope} vacancyTitle={vacancyTitle} /></div>
        <p className="text-xs text-[color:var(--color-muted-foreground)] mb-3">
          {scope === 'global'
            ? 'Эти записи доступны ИИ-ассистенту по всем вакансиям. Не добавляйте здесь детали конкретной вакансии — для этого используйте базу знаний внутри вакансии.'
            : 'Эти записи доступны ИИ-ассистенту только при общении по этой вакансии и никогда не попадут в ответы по другим вакансиям.'}
        </p>
        <div className="flex-1 overflow-y-auto space-y-2">
          {loading ? (
            <div className="text-center py-8 text-sm text-[color:var(--color-muted-foreground)]">
              <Loader2 size={18} className="animate-spin inline" />
            </div>
          ) : entries.length === 0 ? (
            <div className="text-center py-8 text-sm text-[color:var(--color-muted-foreground)]">Записей пока нет</div>
          ) : entries.map(e => (
            <EntryRow key={e.id} entry={e} onEdit={setForm} onDelete={handleDelete} />
          ))}
        </div>
        <div className="flex justify-end mt-4">
          <button onClick={() => setForm('new')} className="btn btn-primary text-sm flex items-center gap-1.5">
            <Plus size={15} /> Новая запись
          </button>
        </div>
      </div>

      {form && (
        <EntryForm
          entry={form === 'new' ? null : form}
          scope={scope}
          vacancyId={vacancyId}
          vacancyTitle={vacancyTitle}
          onClose={() => setForm(null)}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}
