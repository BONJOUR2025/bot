import { useState, useEffect, useCallback } from 'react';
import {
  Plus, X, ArrowRight, Check, AlertTriangle, BookOpen, Sparkles,
} from 'lucide-react';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';
import StrategyModal from './StrategyModal.jsx';
import KnowledgeBaseModal from './KnowledgeBaseModal.jsx';
import ScopeBadge from './ScopeBadge.jsx';
import AiCheckPanel from './AiCheckPanel.jsx';
import useAiCheckGate from './useAiCheckGate.js';

// ── Vacancy wizard ─────────────────────────────────────────────────
const WIZARD_STEPS = [
  { key: 'basic',         label: 'Основное' },
  { key: 'dealbreakers',  label: 'Дил-брейкеры' },
  { key: 'askquestions',  label: 'Вопросы для кандидата' },
  { key: 'strategy',      label: 'Стратегия найма' },
  { key: 'questions',     label: 'Вопросы кандидатов' },
  { key: 'extra',         label: 'Особые инструкции' },
  { key: 'checklist',     label: 'Готовность' },
];

const DEAL_BREAKER_SUGGESTIONS = [
  { label: 'Локация', value: '' },
  { label: 'Формат работы', value: '' },
  { label: 'Зарплатные ожидания', value: '' },
];

// Step 1 — basic info
function StepBasic({ title, setTitle, description, setDesc, interviewLoc, setLoc, onNext }) {
  return (
    <div className="space-y-3">
      <div>
        <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Название *</label>
        <input className="input w-full" value={title} onChange={e => setTitle(e.target.value)}
          placeholder="Мастер по ремонту обуви" autoFocus onKeyDown={e => e.key === 'Enter' && onNext()} />
      </div>
      <div>
        <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Описание (необязательно)</label>
        <textarea className="input w-full min-h-[60px] resize-none" value={description}
          onChange={e => setDesc(e.target.value)} placeholder="Краткое описание вакансии..." />
      </div>
      <div>
        <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Место собеседований</label>
        <input className="input w-full" value={interviewLoc} onChange={e => setLoc(e.target.value)}
          placeholder="Адрес или ссылка на онлайн-встречу" />
      </div>
    </div>
  );
}

// Step 1.5 — deal-breakers: structured criteria the AI checks against during screening
function StepDealBreakers({ vacancyId, dealBreakers, setDealBreakers, onPatched }) {
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  function updateRow(idx, patch) {
    setDealBreakers(rows => rows.map((r, i) => i === idx ? { ...r, ...patch } : r));
  }
  function removeRow(idx) {
    setDealBreakers(rows => rows.filter((_, i) => i !== idx));
  }
  function addRow(preset) {
    setDealBreakers(rows => [...rows, preset || { label: '', value: '' }]);
  }

  async function save() {
    setSaving(true);
    try {
      const cleaned = dealBreakers.filter(d => d.label.trim() && d.value.trim());
      const res = await api.patch(`/recruitment/vacancies/${vacancyId}`, { deal_breakers: cleaned });
      onPatched?.(res.data);
      toast('Сохранено', 'success');
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally { setSaving(false); }
  }

  if (!vacancyId) {
    return <p className="text-sm text-[color:var(--color-muted-foreground)]">Сначала сохраните основное на шаге 1.</p>;
  }

  const missingSuggestions = DEAL_BREAKER_SUGGESTIONS.filter(
    sug => !dealBreakers.some(d => d.label.trim().toLowerCase() === sug.label.toLowerCase())
  );

  return (
    <div className="space-y-3">
      <p className="text-xs text-[color:var(--color-muted-foreground)]">
        Конкретные критерии, по которым кандидат либо подходит, либо нет (локация, формат работы,
        зарплата и т. п.). Они попадают в базу знаний ИИ как чёткие факты — это то, что гарантирует,
        что этап «Проверь deal-breakers» в конструкторе сценария спросит именно про них, а не про что-то
        своё.
      </p>

      {dealBreakers.length === 0 && (
        <p className="text-xs text-amber-600">Пока не указано ни одного критерия.</p>
      )}

      {dealBreakers.map((d, idx) => (
        <div key={idx} className="flex items-center gap-1.5">
          <input className="input text-sm flex-1 min-w-0" value={d.label}
            onChange={e => updateRow(idx, { label: e.target.value })}
            placeholder="Критерий, например: Локация" />
          <span className="text-xs text-[color:var(--color-muted-foreground)] flex-shrink-0">→</span>
          <input className="input text-sm flex-1 min-w-0" value={d.value}
            onChange={e => updateRow(idx, { value: e.target.value })}
            placeholder="Ожидаемое значение, например: Москва, метро Сокол" />
          <button type="button" onClick={() => removeRow(idx)} title="Удалить критерий"
            className="w-7 h-7 flex items-center justify-center rounded hover:bg-red-50 text-red-400 flex-shrink-0">
            <X size={14} />
          </button>
        </div>
      ))}

      <div className="flex items-center gap-2 flex-wrap">
        <button type="button" onClick={() => addRow()}
          className="text-xs text-[color:var(--color-primary)] flex items-center gap-1 hover:underline">
          <Plus size={13} /> Добавить критерий
        </button>
        {missingSuggestions.map(sug => (
          <button key={sug.label} type="button" onClick={() => addRow({ ...sug })}
            className="text-xs px-2 py-1 rounded-full border border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-muted)]/40">
            + {sug.label}
          </button>
        ))}
      </div>

      <button onClick={save} disabled={saving} className="btn btn-primary text-sm">
        {saving ? 'Сохранение...' : 'Сохранить критерии'}
      </button>
    </div>
  );
}

// Step 1.6 — specific questions to ask the candidate; answers go into the
// final AI-generated profile sent to the recruiter, not used as a filter.
function StepAskQuestions({ vacancyId, questions, setQuestions, onPatched }) {
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  function updateRow(idx, value) {
    setQuestions(rows => rows.map((r, i) => i === idx ? value : r));
  }
  function removeRow(idx) {
    setQuestions(rows => rows.filter((_, i) => i !== idx));
  }
  function addRow() {
    setQuestions(rows => [...rows, '']);
  }

  async function save() {
    setSaving(true);
    try {
      const cleaned = questions.filter(q => q.trim());
      const res = await api.patch(`/recruitment/vacancies/${vacancyId}`, { custom_questions: cleaned });
      onPatched?.(res.data);
      toast('Сохранено', 'success');
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally { setSaving(false); }
  }

  if (!vacancyId) {
    return <p className="text-sm text-[color:var(--color-muted-foreground)]">Сначала сохраните основное на шаге 1.</p>;
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-[color:var(--color-muted-foreground)]">
        Вопросы, которые ИИ обязательно задаст кандидату в ходе интервью — это не критерий отбора (как
        дил-брейкеры), просто конкретная информация, которую вы хотите получить. Ответы попадут в
        финальное резюме кандидата, которое бот пришлёт вам после интервью.
      </p>

      {questions.length === 0 && (
        <p className="text-xs text-amber-600">Пока не указано ни одного вопроса.</p>
      )}

      {questions.map((q, idx) => (
        <div key={idx} className="flex items-center gap-1.5">
          <input className="input text-sm flex-1 min-w-0" value={q}
            onChange={e => updateRow(idx, e.target.value)}
            placeholder="Например: Готовы ли к командировкам?" />
          <button type="button" onClick={() => removeRow(idx)} title="Удалить вопрос"
            className="w-7 h-7 flex items-center justify-center rounded hover:bg-red-50 text-red-400 flex-shrink-0">
            <X size={14} />
          </button>
        </div>
      ))}

      <button type="button" onClick={addRow}
        className="text-xs text-[color:var(--color-primary)] flex items-center gap-1 hover:underline">
        <Plus size={13} /> Добавить вопрос
      </button>

      <button onClick={save} disabled={saving} className="btn btn-primary text-sm">
        {saving ? 'Сохранение...' : 'Сохранить вопросы'}
      </button>
    </div>
  );
}

// Step 2 — strategy picker
function StepStrategy({ strategyId, onSelect, onManage }) {
  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/recruitment/strategies');
      setStrategies(res.data || []);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-3">
      <div className="rounded-lg bg-blue-50 border border-blue-100 px-3 py-2 text-xs text-blue-700">
        Это влияет на авто-напоминания, авто-сообщения hh.ru и модель ИИ для этой вакансии.
      </div>
      {loading ? (
        <div className="text-center py-6 text-sm text-[color:var(--color-muted-foreground)]">Загрузка...</div>
      ) : (
        <div className="space-y-2">
          {strategies.map(s => (
            <label key={s.id}
              className={`flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition-colors ${
                strategyId === s.id ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)]/5' : 'border-[color:var(--color-border)] hover:bg-[color:var(--color-muted)]/20'
              }`}>
              <input type="radio" name="strategy" className="mt-1" checked={strategyId === s.id}
                onChange={() => onSelect(s.id)} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{s.name}</span>
                  {s.is_builtin && (
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600">встроенная</span>
                  )}
                </div>
                {s.description && <p className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">{s.description}</p>}
                {strategyId === s.id && (
                  <div className="flex items-center gap-3 mt-1.5 text-xs text-[color:var(--color-muted-foreground)] flex-wrap">
                    <span>{s.follow_up_enabled ? `Напоминания: вкл. (через ${s.follow_up_delay_hours ?? '?'} ч.)` : 'Напоминания: выкл.'}</span>
                    <span>Авто-отказ: {s.decline_after_hours != null ? `${s.decline_after_hours} ч.` : 'никогда'}</span>
                    {s.ai_model && <span>Модель: {s.ai_model}</span>}
                  </div>
                )}
              </div>
            </label>
          ))}
        </div>
      )}
      <button type="button" onClick={onManage} className="text-xs text-[color:var(--color-primary)] hover:underline">
        Управление стратегиями
      </button>
    </div>
  );
}

// Step 3 — AI-suggested candidate questions, scoped FAQ for this vacancy
function QuestionRow({ q, vacancyId }) {
  const [answer, setAnswer] = useState('');
  const [saved, setSaved]   = useState(false);
  const [saving, setSaving] = useState(false);
  const gate = useAiCheckGate();
  const { toast } = useToast();

  function handleChange(e) {
    setAnswer(e.target.value);
    setSaved(false);
    gate.invalidate();
  }

  async function save() {
    if (!answer.trim() || !gate.isConfirmable(answer)) return;
    setSaving(true);
    try {
      await api.post('/recruitment/knowledge-base', {
        scope: 'vacancy', vacancy_id: vacancyId, category: q.category || null,
        question: q.question, answer: answer.trim(), confirmed: true,
      });
      setSaved(true);
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally { setSaving(false); }
  }

  return (
    <div className="rounded-xl border border-[color:var(--color-border)] p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium">{q.question}</p>
        {saved && <span className="flex items-center gap-1 text-xs text-emerald-600 flex-shrink-0"><Check size={13} /> сохранено</span>}
      </div>
      <textarea className="input w-full min-h-[60px] resize-y text-sm" value={answer} onChange={handleChange}
        placeholder="Ответ для кандидата..." disabled={saved} />
      {!saved && answer.trim() && (
        <AiCheckPanel
          gate={gate}
          text={answer}
          scope="vacancy"
          vacancyId={vacancyId}
          fieldLabel={q.question}
          onConfirm={save}
          confirming={saving}
        />
      )}
    </div>
  );
}

function FreeFormQuestionRow({ vacancyId, onRemove }) {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer]     = useState('');
  const [saved, setSaved]       = useState(false);
  const [saving, setSaving]     = useState(false);
  const gate = useAiCheckGate();
  const { toast } = useToast();

  function handleChange(e) {
    setAnswer(e.target.value);
    setSaved(false);
    gate.invalidate();
  }

  async function save() {
    if (!question.trim() || !answer.trim() || !gate.isConfirmable(answer)) return;
    setSaving(true);
    try {
      await api.post('/recruitment/knowledge-base', {
        scope: 'vacancy', vacancy_id: vacancyId, category: null,
        question: question.trim(), answer: answer.trim(), confirmed: true,
      });
      setSaved(true);
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally { setSaving(false); }
  }

  return (
    <div className="rounded-xl border border-dashed border-[color:var(--color-border)] p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <input className="input flex-1 text-sm" value={question} onChange={e => { setQuestion(e.target.value); setSaved(false); }}
          placeholder="Свой вопрос..." disabled={saved} />
        {!saved && <button type="button" onClick={onRemove} className="text-[color:var(--color-muted-foreground)] hover:text-red-500"><X size={14} /></button>}
        {saved && <span className="flex items-center gap-1 text-xs text-emerald-600 flex-shrink-0"><Check size={13} /> сохранено</span>}
      </div>
      <textarea className="input w-full min-h-[60px] resize-y text-sm" value={answer} onChange={handleChange}
        placeholder="Ответ для кандидата..." disabled={saved} />
      {!saved && answer.trim() && question.trim() && (
        <AiCheckPanel
          gate={gate}
          text={answer}
          scope="vacancy"
          vacancyId={vacancyId}
          fieldLabel={question}
          onConfirm={save}
          confirming={saving}
        />
      )}
    </div>
  );
}

function StepQuestions({ vacancyId, title, description, vacancyTitle, onOpenKb }) {
  const [suggestions, setSuggestions] = useState(null);
  const [loading, setLoading] = useState(false);
  const [extraRows, setExtraRows] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!title.trim() || suggestions !== null) return;
    setLoading(true);
    api.post('/recruitment/ai/suggest-questions', { title, description })
      .then(r => setSuggestions(r.data.questions || []))
      .catch(e => setError(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title]);

  const grouped = {};
  for (const q of (suggestions || [])) {
    const cat = q.category || 'Общее';
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(q);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <ScopeBadge scope="vacancy" vacancyTitle={vacancyTitle || title} />
        {vacancyId && (
          <button type="button" onClick={onOpenKb} className="text-xs text-[color:var(--color-primary)] hover:underline flex items-center gap-1">
            <BookOpen size={13} /> Открыть базу знаний вакансии
          </button>
        )}
      </div>

      {!vacancyId ? (
        <p className="text-sm text-[color:var(--color-muted-foreground)]">Сначала сохраните основное на шаге 1.</p>
      ) : loading ? (
        <div className="text-center py-6 text-sm text-[color:var(--color-muted-foreground)] flex items-center justify-center gap-2">
          <Sparkles size={14} className="animate-pulse" /> ИИ подбирает вероятные вопросы кандидатов...
        </div>
      ) : error ? (
        <p className="text-xs text-red-500">{error}</p>
      ) : (
        <>
          {Object.entries(grouped).map(([cat, qs]) => (
            <div key={cat}>
              <p className="text-xs font-semibold text-[color:var(--color-muted-foreground)] uppercase tracking-wide mb-2">{cat}</p>
              <div className="space-y-2">
                {qs.map((q, i) => (
                  <QuestionRow key={cat + i} q={q} vacancyId={vacancyId} />
                ))}
              </div>
            </div>
          ))}

          <div>
            <p className="text-xs font-semibold text-[color:var(--color-muted-foreground)] uppercase tracking-wide mb-2">Дополнительные вопросы</p>
            <div className="space-y-2">
              {extraRows.map(id => (
                <FreeFormQuestionRow key={id} vacancyId={vacancyId}
                  onRemove={() => setExtraRows(prev => prev.filter(x => x !== id))} />
              ))}
              <button type="button" onClick={() => setExtraRows(prev => [...prev, Date.now()])}
                className="text-xs text-[color:var(--color-primary)] hover:underline flex items-center gap-1">
                <Plus size={13} /> Добавить свой вопрос
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// Step 4 — extra_instructions, highest priority, vacancy-scoped
function StepExtra({ vacancyId, vacancyTitle, extraInstructions, setExtraInstructions, onPatched }) {
  const [saving, setSaving] = useState(false);
  const gate = useAiCheckGate();
  const { toast } = useToast();

  function handleChange(e) {
    setExtraInstructions(e.target.value);
    gate.invalidate();
  }

  async function save() {
    if (!gate.isConfirmable(extraInstructions)) return;
    setSaving(true);
    try {
      const res = await api.patch(`/recruitment/vacancies/${vacancyId}`, {
        extra_instructions: extraInstructions, confirmed: true,
      });
      onPatched?.(res.data);
      toast('Сохранено', 'success');
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally { setSaving(false); }
  }

  if (!vacancyId) {
    return <p className="text-sm text-[color:var(--color-muted-foreground)]">Сначала сохраните основное на шаге 1.</p>;
  }

  return (
    <div className="space-y-3">
      <ScopeBadge scope="vacancy" vacancyTitle={vacancyTitle} />
      <p className="text-xs text-[color:var(--color-muted-foreground)]">
        Наивысший приоритет — учитывается даже при противоречии с базой знаний.
      </p>
      <textarea className="input w-full min-h-[100px] resize-y text-sm" value={extraInstructions}
        onChange={handleChange} placeholder="Например: никогда не называть точную дату выхода, только «после собеседования»" />
      {extraInstructions.trim() && (
        <AiCheckPanel
          gate={gate}
          text={extraInstructions}
          scope="vacancy"
          vacancyId={vacancyId}
          fieldLabel="особые инструкции для вакансии"
          onConfirm={save}
          confirming={saving}
        />
      )}
    </div>
  );
}

// Step 5 — readiness checklist
function StepChecklist({ vacancyId }) {
  const [checklist, setChecklist] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!vacancyId) return;
    setLoading(true);
    try {
      const res = await api.get(`/recruitment/vacancies/${vacancyId}/checklist`);
      setChecklist(res.data);
    } finally { setLoading(false); }
  }, [vacancyId]);

  useEffect(() => { load(); }, [load]);

  const LABELS = {
    api_key: 'API-ключ ИИ настроен',
    knowledge_base: 'Есть записи базы знаний',
    interview_location: 'Указано место собеседований',
    strategy: 'Выбрана стратегия найма',
  };

  if (!vacancyId) return <p className="text-sm text-[color:var(--color-muted-foreground)]">Сначала сохраните основное на шаге 1.</p>;
  if (loading || !checklist) return <div className="text-center py-6 text-sm text-[color:var(--color-muted-foreground)]">Загрузка...</div>;

  return (
    <div className="space-y-3">
      <div className={`rounded-lg px-3 py-2 text-sm font-medium flex items-center gap-2 ${
        checklist.ready ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-amber-50 text-amber-700 border border-amber-200'
      }`}>
        {checklist.ready ? <Check size={14} /> : <AlertTriangle size={14} />}
        {checklist.ready ? 'Вакансия готова к найму' : 'Вакансия пока не полностью готова — это не блокирует сохранение'}
      </div>
      <div className="space-y-1.5">
        {checklist.items.map(item => (
          <div key={item.key} className="flex items-center gap-2 text-sm">
            {item.done ? <Check size={14} className="text-emerald-500" /> : <X size={14} className="text-amber-500" />}
            <span className={item.done ? '' : 'text-[color:var(--color-muted-foreground)]'}>{item.label || LABELS[item.key] || item.key}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function VacancyModal({ vacancy, onClose, onSave, zIndex }) {
  const isEdit = !!vacancy;
  const [step, setStep] = useState('basic');
  const [vacancyId, setVacancyId] = useState(vacancy?.id || null);
  const [vacancyTitle, setVacancyTitle] = useState(vacancy?.title || '');

  const [title, setTitle]         = useState(vacancy?.title || '');
  const [description, setDesc]    = useState(vacancy?.description || '');
  const [interviewLoc, setLoc]    = useState(vacancy?.interview_location || '');
  const [strategyId, setStrategyId] = useState(vacancy?.strategy_id || null);
  const [extraInstructions, setExtraInstructions] = useState(vacancy?.extra_instructions || '');
  const [dealBreakers, setDealBreakers] = useState(vacancy?.deal_breakers || []);
  const [customQuestions, setCustomQuestions] = useState(vacancy?.custom_questions || []);
  const [saving, setSaving] = useState(false);
  const [showStrategyMgmt, setShowStrategyMgmt] = useState(false);
  const [showKb, setShowKb] = useState(false);

  async function saveBasicAndStrategy(nextStep) {
    if (!title.trim()) return;
    setSaving(true);
    try {
      const payload = { title, description, interview_location: interviewLoc, strategy_id: strategyId };
      const res = vacancyId
        ? await api.patch(`/recruitment/vacancies/${vacancyId}`, payload)
        : await api.post('/recruitment/vacancies', payload);
      setVacancyId(res.data.id);
      setVacancyTitle(res.data.title);
      onSave(res.data);
      if (nextStep) setStep(nextStep);
    } finally { setSaving(false); }
  }

  // Selecting a strategy is a one-click radio action, not a form submit —
  // it has to persist immediately, otherwise jumping to another step (via
  // the step pills, not just "Далее") silently drops the selection.
  async function handleSelectStrategy(id) {
    setStrategyId(id);
    if (!vacancyId) return;
    const res = await api.patch(`/recruitment/vacancies/${vacancyId}`, { strategy_id: id });
    onSave(res.data);
  }

  function handlePatched(data) {
    setDealBreakers(data.deal_breakers || []);
    setCustomQuestions(data.custom_questions || []);
    onSave(data);
  }

  const stepIdx = WIZARD_STEPS.findIndex(s => s.key === step);
  const canJumpFreely = isEdit || !!vacancyId;

  return (
    <div className="modal-backdrop" style={zIndex ? { zIndex } : undefined} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-2xl w-full flex flex-col overflow-hidden" style={{ maxHeight: '90vh' }}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-semibold">{isEdit ? 'Редактировать вакансию' : 'Новая вакансия'}</h3>
          <button onClick={onClose} className="text-xl text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] leading-none">&times;</button>
        </div>

        {/* Step indicator */}
        <div className="flex items-center gap-1 mb-4 overflow-x-auto pb-1">
          {WIZARD_STEPS.map((s, i) => {
            const clickable = canJumpFreely && !!vacancyId;
            const active = s.key === step;
            return (
              <button
                key={s.key}
                type="button"
                disabled={!clickable && i !== 0}
                onClick={() => setStep(s.key)}
                className={`flex-shrink-0 flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                  active ? 'bg-[color:var(--color-primary)] text-white' : 'bg-[color:var(--color-muted)]/50 text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-muted)]'
                }`}
              >
                <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${active ? 'bg-white/25' : 'bg-[color:var(--color-muted)]'}`}>{i + 1}</span>
                {s.label}
              </button>
            );
          })}
        </div>

        <div className="flex-1 overflow-y-auto pr-1">
          {step === 'basic' && (
            <StepBasic
              title={title} setTitle={setTitle}
              description={description} setDesc={setDesc}
              interviewLoc={interviewLoc} setLoc={setLoc}
              onNext={() => saveBasicAndStrategy('dealbreakers')}
            />
          )}
          {step === 'dealbreakers' && (
            <StepDealBreakers vacancyId={vacancyId} dealBreakers={dealBreakers}
              setDealBreakers={setDealBreakers} onPatched={handlePatched} />
          )}
          {step === 'askquestions' && (
            <StepAskQuestions vacancyId={vacancyId} questions={customQuestions}
              setQuestions={setCustomQuestions} onPatched={handlePatched} />
          )}
          {step === 'strategy' && (
            <StepStrategy strategyId={strategyId} onSelect={handleSelectStrategy} onManage={() => setShowStrategyMgmt(true)} />
          )}
          {step === 'questions' && (
            <StepQuestions vacancyId={vacancyId} title={title} description={description} vacancyTitle={vacancyTitle || title}
              onOpenKb={() => setShowKb(true)} />
          )}
          {step === 'extra' && (
            <StepExtra vacancyId={vacancyId} vacancyTitle={vacancyTitle || title}
              extraInstructions={extraInstructions} setExtraInstructions={setExtraInstructions}
              onPatched={onSave} />
          )}
          {step === 'checklist' && (
            <StepChecklist vacancyId={vacancyId} />
          )}
        </div>

        <div className="flex justify-between items-center gap-2 mt-5 pt-3 border-t border-[color:var(--color-border)]">
          <button onClick={onClose} className="btn btn-secondary">Закрыть</button>
          <div className="flex items-center gap-2">
            {stepIdx > 0 && (
              <button onClick={() => setStep(WIZARD_STEPS[stepIdx - 1].key)} className="btn btn-secondary text-sm">
                Назад
              </button>
            )}
            {step === 'basic' ? (
              <button onClick={() => saveBasicAndStrategy(isEdit ? null : 'dealbreakers')} disabled={saving || !title.trim()} className="btn btn-primary text-sm flex items-center gap-1.5">
                {saving ? 'Сохранение...' : isEdit ? 'Сохранить' : <>Далее <ArrowRight size={14} /></>}
              </button>
            ) : stepIdx < WIZARD_STEPS.length - 1 ? (
              <button onClick={() => setStep(WIZARD_STEPS[stepIdx + 1].key)} className="btn btn-primary text-sm flex items-center gap-1.5">
                Далее <ArrowRight size={14} />
              </button>
            ) : (
              <button onClick={onClose} className="btn btn-primary text-sm">Готово</button>
            )}
          </div>
        </div>
      </div>

      {showStrategyMgmt && (
        <StrategyModal onClose={() => setShowStrategyMgmt(false)} zIndex={(zIndex || 60) + 5} />
      )}
      {showKb && vacancyId && (
        <KnowledgeBaseModal scope="vacancy" vacancyId={vacancyId} vacancyTitle={vacancyTitle || title} onClose={() => setShowKb(false)} />
      )}
    </div>
  );
}
