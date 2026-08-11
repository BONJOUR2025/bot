import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Plus, X, Phone, Mail, FileText,
  Briefcase, ExternalLink, Pencil, Trash2, Settings,
  CheckSquare, Square, ChevronDown, User, Calendar, MessageCircle,
  ArrowRight, Clock, SendHorizonal, Loader2, MessageSquare,
  Pause, Play, Check, BookOpen, Sparkles, ListChecks, Copy, FileStack,
  PhoneMissed, PhoneCall,
} from 'lucide-react';
import api from '../api';
import { useViewport } from '../providers/ViewportProvider.jsx';
import { useToast } from '../providers/ToastProvider.jsx';
import IntegrationsModal from '../components/recruitment/IntegrationsModal.jsx';
import StrategyModal from '../components/recruitment/StrategyModal.jsx';
import KnowledgeBaseModal from '../components/recruitment/KnowledgeBaseModal.jsx';
import VacancyTemplatesModal from '../components/recruitment/VacancyTemplatesModal.jsx';
import VacancyModal from '../components/recruitment/VacancyModal.jsx';
import ScopeBadge from '../components/recruitment/ScopeBadge.jsx';
import AiCheckPanel from '../components/recruitment/AiCheckPanel.jsx';
import useAiCheckGate from '../components/recruitment/useAiCheckGate.js';

// Этапы синхронизированы с app/services/recruitment_stages.py (воронка
// «5 этапов + флаги» — старая телеграм-привязка/общение убраны вместе со
// старым интервью-флоу, единственный живой источник теперь быстрый режим).
const STAGES = [
  { key: 'новый',         label: 'Новый',          color: 'bg-blue-100 text-blue-700',       dot: 'bg-blue-400',     border: 'border-t-blue-400'   },
  { key: 'опрос',         label: 'Опрос',          color: 'bg-cyan-100 text-cyan-700',       dot: 'bg-cyan-400',     border: 'border-t-cyan-400'   },
  { key: 'ответил',       label: 'Ответил',        color: 'bg-amber-100 text-amber-700',     dot: 'bg-amber-400',    border: 'border-t-amber-400'  },
  { key: 'думает',        label: 'Думает',         color: 'bg-orange-100 text-orange-700',   dot: 'bg-orange-400',   border: 'border-t-orange-400' },
  { key: 'собеседование', label: 'Собеседование',  color: 'bg-violet-100 text-violet-700',   dot: 'bg-violet-400',   border: 'border-t-violet-400' },
  { key: 'нанят',         label: 'Нанят ✓',        color: 'bg-emerald-100 text-emerald-700', dot: 'bg-emerald-400',  border: 'border-t-emerald-400'},
  { key: 'отказ',         label: 'Отказ',          color: 'bg-red-100 text-red-700',         dot: 'bg-red-400',      border: 'border-t-red-400'    },
];

const SOURCES = [
  { key: 'manual', label: 'Вручную' },
  { key: 'hh',     label: 'hh.ru'   },
  { key: 'avito',  label: 'Авито'   },
  { key: 'other',  label: 'Другое'  },
];

const stageOf   = (key) => STAGES.find(s => s.key === key) || STAGES[0];
const srcLabel  = (key) => SOURCES.find(s => s.key === key)?.label || key;
// Год обязателен: после импорта истории с площадок в списке соседствуют
// отклики 2023-2024 годов и сегодняшние, и «31 окт» рядом с «7 авг» читается
// как две недавние даты.
// «31 окт. 2023 г.» → «31 окт 2023»: подпись на карточке рендерится 10-м
// кеглем, служебные «г.» и точки съедают там заметную долю ширины.
const fmtDate   = (iso) => iso
  ? new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
      .replace(/\s*г\.$/, '').replace('.', '')
  : '';
const tgLink    = (phone) => { const d = (phone || '').replace(/\D/g, ''); return d.length >= 7 ? `https://t.me/+${d}` : null; };

const SRC_BADGE = {
  hh:     'bg-red-100 text-red-600',
  avito:  'bg-green-100 text-green-600',
  manual: 'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)]',
  other:  'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)]',
};
const srcBadgeLabel = (s) => s === 'manual' ? 'руч.' : s;

/** Куда уйдёт текст отказа: 'hh' | 'avito' | null.
 *
 * У hh отказ — действие в API отклика, текст прикладывается к нему. У Авито
 * такого действия нет, есть только переписка, и без чата (отклик «только
 * телефон») отправлять некуда — тогда отказ проставляется молча.
 */
function rejectionTarget(c) {
  if (!c) return null;
  if (c.source === 'hh' && c.external_id) return 'hh';
  if (c.source === 'avito' && c.platform_chat_id) return 'avito';
  return null;
}

// ── Candidate modal ────────────────────────────────────────────────
function CandidateModal({ candidate, vacancyId, initialStage, onClose, onSave }) {
  const [form, setForm] = useState({
    name:             candidate?.name             || '',
    phone:            candidate?.phone            || '',
    email:            candidate?.email            || '',
    source:           candidate?.source           || 'manual',
    stage:            candidate?.stage            || initialStage || 'новый',
    notes:            candidate?.notes            || '',
    age:              candidate?.age              ?? '',
    resume_url:         candidate?.resume_url         || '',
    telegram_chat_id:   candidate?.telegram_chat_id   || '',
    telegram_username:  candidate?.telegram_username   || '',
  });
  const [saving, setSaving] = useState(false);
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));

  async function save() {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const payload = { ...form, age: form.age !== '' ? Number(form.age) : null };
      const res = candidate
        ? await api.patch(`/recruitment/candidates/${candidate.id}`, payload)
        : await api.post('/recruitment/candidates', { ...payload, vacancy_id: vacancyId });
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
              <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Возраст</label>
              <input type="number" min={16} max={80} className="input w-full" value={form.age} onChange={set('age')} placeholder="30" />
            </div>
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Email</label>
            <input className="input w-full" value={form.email} onChange={set('email')} placeholder="mail@..." />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Ссылка на резюме</label>
            <input className="input w-full" value={form.resume_url} onChange={set('resume_url')} placeholder="https://hh.ru/resume/..." />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Telegram username</label>
            <input className="input w-full" value={form.telegram_username} onChange={set('telegram_username')} placeholder="@username" />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Telegram chat_id</label>
            <input className="input w-full" value={form.telegram_chat_id} onChange={set('telegram_chat_id')} placeholder="Заполняется автоматически или вручную" />
            <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">
              Определяется автоматически, когда кандидат напишет первым. Можно вставить вручную.
            </p>
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
          <button onClick={save} disabled={saving || !form.name.trim()} className="btn btn--primary">
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Interview modal ────────────────────────────────────────────────
const DEFAULT_INTERVIEW_TEMPLATE = 'Здравствуйте, #name!\nПриглашаем вас на собеседование.\n📅 Дата: #date\n🕐 Время: #time\n📍 Место: #place\n\nЕсли возникнут вопросы — напишите в этот чат.';

function applyTags(text, { name = '', date = '', time = '', place = '' } = {}) {
  const dateStr = date
    ? new Date(date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
    : '#date';
  return text
    .replace(/#name/g, name || '#name')
    .replace(/#date/g, date ? dateStr : '#date')
    .replace(/#time/g, time || '#time')
    .replace(/#place/g, place || '#place');
}

function InterviewModal({ candidate, onSave, onClose, templates = [] }) {
  const today = new Date().toISOString().split('T')[0];
  const [form, setForm] = useState({ date: today, time: '', location: '', note: '' });
  const [saving, setSaving] = useState(false);
  const [sendMsg, setSendMsg] = useState(candidate?.source === 'hh');
  const [sendTg, setSendTg] = useState(false);
  const [templateText, setTemplateText] = useState(DEFAULT_INTERVIEW_TEMPLATE);
  const [msgText, setMsgText] = useState(() =>
    applyTags(DEFAULT_INTERVIEW_TEMPLATE, { name: candidate?.name, date: today })
  );

  const interviewTemplates = templates.filter(t => t.type === 'interview');

  function applyTemplate(text) {
    setTemplateText(text);
    setMsgText(applyTags(text, { name: candidate?.name, date: form.date, time: form.time, place: form.location }));
  }

  const set = k => e => {
    const updated = { ...form, [k]: e.target.value };
    setForm(updated);
    setMsgText(applyTags(templateText, { name: candidate?.name, date: updated.date, time: updated.time, place: updated.location }));
  };

  async function save() {
    setSaving(true);
    try {
      await api.patch(`/recruitment/candidates/${candidate.id}`, {
        stage: 'собеседование',
        hh_message: (sendMsg && candidate?.source === 'hh' && msgText.trim()) ? msgText.trim() : null,
        send_telegram: sendTg && !!candidate?.telegram_chat_id,
      });

      const descParts = [];
      if (form.location) descParts.push(`📍 Место: ${form.location}`);
      if (form.note)     descParts.push(form.note);

      await api.post('/tasks', {
        title: `Собеседование: ${candidate.name}`,
        description: descParts.join('\n') || null,
        due_date: form.date || null,
        due_time: form.time || null,
        priority: 'high',
        category: 'Подбор персонала',
        status: 'todo',
      });

      onSave();
    } catch(e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" style={{ zIndex: 70 }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-sm w-full">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-base font-semibold">Назначить собеседование</h3>
          <button onClick={onClose} className="text-xl text-[color:var(--color-muted-foreground)] leading-none">&times;</button>
        </div>
        <p className="text-sm text-[color:var(--color-muted-foreground)] mb-4">{candidate.name}</p>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Дата</label>
              <input type="date" className="input w-full" value={form.date} onChange={set('date')} />
            </div>
            <div>
              <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Время</label>
              <input type="time" className="input w-full" value={form.time} onChange={set('time')} />
            </div>
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Место</label>
            <input className="input w-full" value={form.location} onChange={set('location')} placeholder="Офис, адрес или ссылка на звонок" />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Примечание</label>
            <textarea className="input w-full min-h-[60px] resize-none" value={form.note} onChange={set('note')} placeholder="Что взять с собой, вопросы..." />
          </div>
          {candidate?.source === 'hh' && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <input type="checkbox" id="sendMsgChk" checked={sendMsg} onChange={e => setSendMsg(e.target.checked)} className="rounded" />
                <label htmlFor="sendMsgChk" className="text-xs font-medium cursor-pointer">Отправить сообщение кандидату (hh.ru)</label>
              </div>
              {candidate?.telegram_chat_id && (
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="sendTgChk" checked={sendTg} onChange={e => setSendTg(e.target.checked)} className="rounded" />
                  <label htmlFor="sendTgChk" className="text-xs font-medium cursor-pointer">
                    Также отправить в Telegram (chat_id: <code>{candidate.telegram_chat_id}</code>)
                  </label>
                </div>
              )}
              {sendMsg && (
                <div className="space-y-1.5">
                  {interviewTemplates.length > 0 && (
                    <select className="input w-full text-sm" defaultValue=""
                      onChange={e => { if (e.target.value) applyTemplate(e.target.value); }}>
                      <option value="">— выбрать шаблон —</option>
                      {interviewTemplates.map((t, i) => (
                        <option key={i} value={t.text}>{t.name}</option>
                      ))}
                    </select>
                  )}
                  <textarea
                    className="input w-full text-sm resize-none"
                    rows={5}
                    value={msgText}
                    onChange={e => setMsgText(e.target.value)}
                  />
                  <p className="text-xs text-[color:var(--color-muted-foreground)]">
                    Теги: <code>#name</code> · <code>#date</code> · <code>#time</code> · <code>#place</code>
                  </p>
                </div>
              )}
            </div>
          )}
          <div className="rounded-lg bg-violet-50 border border-violet-100 px-3 py-2 text-xs text-violet-700 flex items-center gap-1.5">
            <span>📋</span> Задача автоматически создастся в разделе «Задачи»
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="btn btn-secondary">Отмена</button>
          <button onClick={save} disabled={saving} className="btn btn--primary">
            {saving ? 'Сохранение...' : 'Назначить'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Candidate detail modal ─────────────────────────────────────────
const DEFAULT_NO_ANSWER_MSG =
  'Здравствуйте! Пробовали до вас дозвониться, но не получилось. ' +
  'Подскажите, когда вам удобно поговорить?';

/** Исход звонка кандидату.
 *
 * Смысл кнопки «не дозвонился» не в учёте попыток, а в том, что вместо
 * второго звонка вслепую кандидату уходит вопрос «когда вам удобно» —
 * он отвечает текстом, и следующий звонок уже по назначенному времени.
 * Поэтому отправка включена по умолчанию, а галочка её отключает, а не
 * включает.
 */
function CallOutcome({ candidate, hasPlatformChat, platformLabel, templates, onChanged }) {
  const { toast } = useToast();
  const noAnswerTemplates = (templates || []).filter(t => t.type === 'no_answer');
  const [open, setOpen] = useState(false);
  const [send, setSend] = useState(true);
  const [text, setText] = useState(noAnswerTemplates[0]?.text || DEFAULT_NO_ANSWER_MSG);
  const [busy, setBusy] = useState(false);
  const [attempts, setAttempts] = useState(candidate.call_attempts || 0);

  async function submit() {
    setBusy(true);
    try {
      const res = await api.post(`/recruitment/candidates/${candidate.id}/no-answer`, {
        send_message: Boolean(send && hasPlatformChat),
        text: text.trim() || null,
      });
      setAttempts(res.data.call_attempts);
      setOpen(false);
      toast(res.data.warning
        || (res.data.message_sent
            ? `Попытка записана, сообщение отправлено в ${platformLabel}`
            : 'Попытка записана'),
        res.data.warning ? 'error' : 'success');
      onChanged?.();
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally { setBusy(false); }
  }

  async function reached() {
    setBusy(true);
    try {
      await api.post(`/recruitment/candidates/${candidate.id}/reached`);
      setAttempts(0);
      toast('Отметили, что дозвонились', 'success');
      onChanged?.();
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally { setBusy(false); }
  }

  return (
    <div className="rounded-xl border border-[color:var(--color-border)] p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-[color:var(--color-muted-foreground)] uppercase tracking-wide">
          Исход звонка
        </p>
        {attempts > 0 && (
          <span className={`text-[11px] font-medium px-2 py-0.5 rounded-md border ${
            attempts >= 3
              ? 'bg-orange-100 text-orange-800 border-orange-300'
              : 'bg-sky-100 text-sky-800 border-sky-200'
          }`}>
            не дозвонились {attempts} раз{attempts === 1 ? '' : attempts < 5 ? 'а' : ''}
          </span>
        )}
      </div>

      {attempts >= 3 && (
        <p className="text-xs text-orange-800 bg-orange-50 border border-orange-200 rounded-lg px-3 py-2 leading-relaxed">
          Третья попытка подряд. Дальше звонить смысла мало — либо ждём ответа в переписке,
          либо переводите в «Отказ».
        </p>
      )}

      {!open ? (
        <div className="flex flex-wrap gap-2">
          <button onClick={() => setOpen(true)} disabled={busy}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-xl border border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100 transition-colors disabled:opacity-50">
            <PhoneMissed size={13} /> Не дозвонился
          </button>
          {attempts > 0 && (
            <button onClick={reached} disabled={busy}
              className="flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 transition-colors disabled:opacity-50">
              <PhoneCall size={13} /> Дозвонился
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-2.5">
          {hasPlatformChat ? (
            <>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={send} onChange={e => setSend(e.target.checked)}
                  className="rounded" />
                <span className="text-xs">Написать кандидату в {platformLabel}</span>
              </label>
              {send && (
                <>
                  {noAnswerTemplates.length > 0 && (
                    <select className="input w-full text-sm" defaultValue=""
                      onChange={e => { if (e.target.value) setText(e.target.value); }}>
                      <option value="">— выбрать шаблон —</option>
                      {noAnswerTemplates.map((t, i) => (
                        <option key={i} value={t.text}>{t.name}</option>
                      ))}
                    </select>
                  )}
                  <textarea className="input w-full text-sm" rows={3} value={text}
                    onChange={e => setText(e.target.value)} />
                </>
              )}
            </>
          ) : (
            <p className="text-xs text-[color:var(--color-muted-foreground)] leading-relaxed">
              У этого отклика нет переписки — кандидат оставил только телефон.
              Запишем попытку, писать некуда.
            </p>
          )}
          <div className="flex gap-2 justify-end">
            <button onClick={() => setOpen(false)} disabled={busy}
              className="btn btn-secondary text-xs">Отмена</button>
            <button onClick={submit} disabled={busy}
              className="btn btn-primary text-xs flex items-center gap-1.5">
              {busy && <Loader2 size={12} className="animate-spin" />}
              {send && hasPlatformChat ? 'Записать и написать' : 'Записать попытку'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function CandidateDetail({ candidate, onClose, onEdit, onDelete, onStageChange, onResetHistory,
                           onPauseToggle, templates = [], onCandidateChanged }) {
  const { toast } = useToast();
  const stage = stageOf(candidate.stage);
  const tg = tgLink(candidate.phone);
  // Both job boards expose a chat, they just address it differently: hh by
  // negotiation id (external_id), Avito by messenger chat id. Avito applies of
  // type "by_call" carry no chat at all, hence the explicit check.
  // Boolean(), а не голое &&: `'avito' === source && candidate.platform_chat_id`
  // возвращает саму СТРОКУ chat_id, а не true. Пока значение только включало
  // и выключало разметку, это не мешало — но стоило отправить его в тело
  // запроса как `send_message`, и Pydantic ответил 422: строка вместо bool.
  const isHh = Boolean(candidate.source === 'hh' && candidate.external_id);
  const isAvitoChat = Boolean(candidate.source === 'avito' && candidate.platform_chat_id);
  const hasPlatformChat = isHh || isAvitoChat;
  const platformLabel = candidate.source === 'avito' ? 'Авито' : 'hh.ru';

  const [tab, setTab] = useState('info');
  const [resetting, setResetting] = useState(false);
  const [paused, setPaused] = useState(!!candidate.is_paused);
  const [toggling, setToggling] = useState(false);

  // Job-board chat state (hh.ru / Авито)
  const [quick, setQuick]           = useState(null);
  const [quickStarting, setQuickStarting] = useState(false);
  const [messages, setMessages]     = useState([]);
  const [msgLoading, setMsgLoading] = useState(false);
  const [msgError, setMsgError]     = useState('');
  const [text, setText]             = useState('');
  const [sending, setSending]       = useState(false);
  const bottomRef                   = useRef(null);

  useEffect(() => {
    if (tab === 'chat' && hasPlatformChat && messages.length === 0) { loadMessages(); loadQuick(); }
  }, [tab]);

  useEffect(() => {
    if (tab === 'chat') bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, tab]);

  async function loadMessages() {
    setMsgLoading(true); setMsgError('');
    try {
      const res = await api.get(`/recruitment/candidates/${candidate.id}/messages`);
      setMessages(res.data);
    } catch (e) {
      setMsgError(e.response?.data?.detail || e.message);
    } finally { setMsgLoading(false); }
  }

  async function loadQuick() {
    try {
      const res = await api.get(`/recruitment/candidates/${candidate.id}/quick-screening`);
      setQuick(res.data);
    } catch { /* панель просто не покажется */ }
  }

  async function startQuick() {
    setQuickStarting(true); setMsgError('');
    try {
      await api.post(`/recruitment/candidates/${candidate.id}/quick-screening`);
      await loadQuick();
      await loadMessages();
    } catch (e) {
      setMsgError(e.response?.data?.detail || e.message);
    } finally { setQuickStarting(false); }
  }

  async function handleSend() {
    if (!text.trim() || sending) return;
    setSending(true);
    try {
      await api.post(`/recruitment/candidates/${candidate.id}/messages`, { text: text.trim() });
      setText('');
      await loadMessages();
    } catch (e) {
      setMsgError(e.response?.data?.detail || e.message);
    } finally { setSending(false); }
  }

  async function handleTogglePause() {
    setToggling(true);
    try {
      const res = await api.post(`/recruitment/candidates/${candidate.id}/toggle-pause`);
      setPaused(res.data.is_paused);
      onPauseToggle?.(candidate.id, res.data.is_paused);
    } catch(e) { toast(e.response?.data?.detail || e.message, 'error'); }
    finally { setToggling(false); }
  }

  async function handleResetHistory() {
    if (!window.confirm(`Удалить всю историю переписки с ${candidate.name} и сбросить этап на «Новый»? Это действие нельзя отменить.`)) return;
    setResetting(true);
    try {
      await api.post(`/recruitment/candidates/${candidate.id}/reset-history`);
      onResetHistory?.(candidate.id);
      onClose();
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally { setResetting(false); }
  }

  function fmtMsgTime(iso) {
    if (!iso) return '';
    try {
      return new Date(iso).toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
      });
    } catch { return iso; }
  }

  return (
    <div className="modal-backdrop" style={{ zIndex: 60 }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-xl w-full flex flex-col overflow-hidden p-0">

        {/* ── Header with photo ── */}
        <div className="relative flex items-end gap-4 px-6 pt-6 pb-4 border-b border-[color:var(--color-border)] bg-[color:var(--color-muted)]/20">
          {/* Avatar / photo */}
          <div className="flex-shrink-0">
            {candidate.photo_url ? (
              <img
                src={candidate.photo_url}
                alt={candidate.name}
                className="w-16 h-16 rounded-2xl object-cover border-2 border-white shadow-md"
                onError={e => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex'; }}
              />
            ) : null}
            <div className={`w-16 h-16 rounded-2xl border-2 border-white shadow-md bg-[color:var(--color-bg-secondary)] items-center justify-center text-[color:var(--color-muted-foreground)] ${candidate.photo_url ? 'hidden' : 'flex'}`}>
              <User size={28} />
            </div>
          </div>

          {/* Name + stage */}
          <div className="flex-1 min-w-0 pb-0.5 pr-9">
            <h2 className="text-lg font-semibold leading-tight truncate">
              {candidate.name}
            </h2>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {candidate.age != null && (
                <span className="text-sm text-[color:var(--color-muted-foreground)]">{candidate.age} лет</span>
              )}
              <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${stage.color}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${stage.dot}`} />
                {stage.label}
              </span>
              <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${SRC_BADGE[candidate.source] || SRC_BADGE.other}`}>
                {srcBadgeLabel(candidate.source)}
              </span>
            </div>
          </div>

          <button onClick={onClose}
            className="absolute top-4 right-4 w-7 h-7 flex items-center justify-center rounded-full hover:bg-[color:var(--color-muted)] text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* ── Tabs ──
            The modal itself is a fixed, fairly narrow width (max-w-xl) on every
            device — a phone and a 4K monitor render the same px-wide box here.
            So labels must stay compact unconditionally; sizing them off the
            viewport (sm:) was the bug: desktop viewports got full-length labels
            that didn't actually fit this box, overflowing invisibly (no visible
            scrollbar) whenever the 4th hh.ru tab was present. */}
        <div className="flex overflow-x-auto border-b border-[color:var(--color-border)] px-3">
          <button
            onClick={() => setTab('info')}
            className={`flex-shrink-0 whitespace-nowrap text-xs font-medium py-2.5 px-2.5 border-b-2 transition-colors ${
              tab === 'info'
                ? 'border-[color:var(--color-primary)] text-[color:var(--color-primary)]'
                : 'border-transparent text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)]'
            }`}
          >
            Инфо
          </button>
          {hasPlatformChat && (
            <button
              onClick={() => setTab('chat')}
              className={`flex-shrink-0 whitespace-nowrap text-xs font-medium py-2.5 px-2.5 border-b-2 transition-colors flex items-center gap-1 ${
                tab === 'chat'
                  ? 'border-[color:var(--color-primary)] text-[color:var(--color-primary)]'
                  : 'border-transparent text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)]'
              }`}
            >
              <MessageCircle size={13} /> {platformLabel}
            </button>
          )}
          <button
            onClick={() => setTab('profile')}
            className={`flex-shrink-0 whitespace-nowrap text-xs font-medium py-2.5 px-2.5 border-b-2 transition-colors flex items-center gap-1 ${
              tab === 'profile'
                ? 'border-[color:var(--color-primary)] text-[color:var(--color-primary)]'
                : 'border-transparent text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)]'
            }`}
          >
            <Sparkles size={13} /> ИИ
          </button>
        </div>

        {/* ── Body ── */}
        {tab === 'info' && <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">

          {/* Contacts block */}
          {(candidate.phone || candidate.email) && (
            <div className="rounded-xl border border-[color:var(--color-border)] divide-y divide-[color:var(--color-border)] overflow-hidden">
              {candidate.phone && (
                <div className="flex items-center gap-3 px-4 py-3">
                  <Phone size={15} className="text-[color:var(--color-muted-foreground)] flex-shrink-0" />
                  <a href={`tel:${candidate.phone}`}
                    className="flex-1 min-w-0 truncate text-sm font-medium text-[color:var(--color-foreground)] hover:text-[color:var(--color-primary)] transition-colors">
                    {candidate.phone}
                  </a>
                  {tg && (
                    <a href={tg} target="_blank" rel="noopener noreferrer"
                      className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-lg bg-sky-50 text-sky-600 hover:bg-sky-100 border border-sky-200 transition-colors flex-shrink-0">
                      <MessageCircle size={12} /> Написать в TG
                    </a>
                  )}
                </div>
              )}
              {candidate.email && (
                <div className="flex items-center gap-3 px-4 py-3">
                  <Mail size={15} className="text-[color:var(--color-muted-foreground)] flex-shrink-0" />
                  <a href={`mailto:${candidate.email}`}
                    className="flex-1 text-sm font-medium text-[color:var(--color-foreground)] hover:text-[color:var(--color-primary)] transition-colors truncate">
                    {candidate.email}
                  </a>
                </div>
              )}
            </div>
          )}

          {/* Исход звонка. Стоит сразу под телефоном, потому что нажимают
              это ровно в тот момент, когда положили трубку. */}
          {candidate.phone && (
            <CallOutcome
              candidate={candidate}
              hasPlatformChat={hasPlatformChat}
              platformLabel={platformLabel}
              templates={templates}
              onChanged={onCandidateChanged}
            />
          )}

          {/* Resume link */}
          {candidate.resume_url && (
            <a href={candidate.resume_url} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-3 px-4 py-3 rounded-xl border border-[color:var(--color-border)] hover:border-[color:var(--color-primary)]/40 hover:bg-[color:var(--color-primary)]/4 transition-all group">
              <FileText size={15} className="text-[color:var(--color-muted-foreground)] flex-shrink-0 group-hover:text-[color:var(--color-primary)]" />
              <span className="flex-1 text-sm font-medium text-[color:var(--color-foreground)] group-hover:text-[color:var(--color-primary)]">
                Открыть резюме
              </span>
              <ExternalLink size={13} className="text-[color:var(--color-muted-foreground)] group-hover:text-[color:var(--color-primary)]" />
            </a>
          )}

          {/* Meta */}
          <div className="flex items-center gap-2 text-xs text-[color:var(--color-muted-foreground)]">
            <Clock size={12} />
            <span>Добавлен {fmtDate(candidate.created_at)}</span>
          </div>

          {/* Notes */}
          {candidate.notes && (
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-100">
              <div className="flex items-center gap-1.5 text-xs font-medium text-amber-700 mb-2">
                <FileText size={12} /> Заметки
              </div>
              <p className="text-sm text-amber-900 whitespace-pre-wrap break-words leading-relaxed">{candidate.notes}</p>
            </div>
          )}

          {/* Stage pipeline */}
          <div>
            <p className="text-xs font-medium text-[color:var(--color-muted-foreground)] mb-2.5 uppercase tracking-wide">Перевести в этап</p>
            <div className="flex flex-wrap gap-2">
              {STAGES.map(s => (
                <button
                  key={s.key}
                  onClick={() => { onStageChange(candidate.id, s.key); onClose(); }}
                  disabled={s.key === candidate.stage}
                  className={`flex items-center justify-center gap-1.5 whitespace-nowrap text-xs px-2.5 py-2 rounded-xl font-medium transition-all border ${s.color} ${
                    s.key === candidate.stage
                      ? 'opacity-40 cursor-default ring-1 ring-offset-1 ring-current'
                      : 'hover:scale-[1.03] hover:shadow-sm border-transparent'
                  }`}
                >
                  {s.key === candidate.stage && <span className="w-1.5 h-1.5 rounded-full bg-current" />}
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* Pause AI */}
          <div className="pt-2 border-t border-[color:var(--color-border)]">
            <p className="text-xs font-medium text-[color:var(--color-muted-foreground)] mb-2 uppercase tracking-wide">ИИ-автоматизация</p>
            <button
              onClick={handleTogglePause}
              disabled={toggling}
              className={`w-full flex items-center justify-center gap-2 text-xs font-medium px-3 py-2.5 rounded-xl border transition-colors disabled:opacity-50 ${
                paused
                  ? 'border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100'
                  : 'border-[color:var(--color-border)] text-[color:var(--color-text-muted)] hover:bg-[color:var(--color-control-bg-hover)]'
              }`}
            >
              {toggling ? <Loader2 size={13} className="animate-spin" /> : paused ? <Play size={13} /> : <Pause size={13} />}
              {paused ? '▶️ Возобновить (ИИ на паузе)' : '⏸ Поставить на паузу'}
            </button>
          </div>

          {/* Reset history */}
          <div className="pt-2 border-t border-[color:var(--color-border)]">
            <p className="text-xs font-medium text-[color:var(--color-muted-foreground)] mb-2 uppercase tracking-wide">Чистый тест</p>
            <button
              onClick={handleResetHistory}
              disabled={resetting}
              className="w-full flex items-center justify-center gap-2 text-xs font-medium px-3 py-2.5 rounded-xl border border-red-200 text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
            >
              {resetting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              Сбросить историю и этап
            </button>
          </div>
        </div>}

        {/* ── Chat tab ── */}
        {tab === 'chat' && (
          <div className="flex flex-col flex-1 overflow-hidden" style={{ minHeight: 0 }}>
            {/* Быстрый режим для одного кандидата — работает независимо от
                тумблера вакансии: тумблер решает только, запускать ли опрос
                автоматически на новых откликах. */}
            {quick && (
              <div className="border-b border-[color:var(--color-border)] px-4 py-2.5 bg-[color:var(--color-muted)]/30">
                {quick.status === 'asking' && quick.phase === 'interest' && (
                  <p className="text-xs text-[color:var(--color-muted-foreground)]">
                    ⚡ Уточняю у кандидата, актуален ли ещё поиск работы
                  </p>
                )}
                {quick.status === 'asking' && quick.phase !== 'interest' && (
                  <p className="text-xs text-[color:var(--color-muted-foreground)]">
                    ⚡ Опрос идёт: вопрос {Math.min(quick.idx + 1, quick.questions.length)} из {quick.questions.length}
                    {quick.answers.length > 0 && ` · получено ответов: ${quick.answers.length}`}
                  </p>
                )}
                {quick.status === 'done' && (
                  <p className="text-xs text-emerald-600">✅ Опрос завершён — кандидат ответил на все вопросы</p>
                )}
                {quick.status === 'waiting_admin' && (
                  <p className="text-xs text-amber-600">
                    ⏸ Опрос остановлен, дальше вы — бот больше не пишет
                  </p>
                )}
                {!quick.status && (
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs text-[color:var(--color-muted-foreground)]">
                      {quick.questions.length > 0
                        ? `Быстрый опрос: ${quick.questions.length} вопрос(ов), бот задаст их здесь по одному`
                        : 'У вакансии не заданы вопросы быстрого режима'}
                    </p>
                    <button
                      onClick={startQuick}
                      disabled={!quick.can_start || quickStarting}
                      className="btn btn--secondary text-xs flex-shrink-0 disabled:opacity-40"
                    >
                      {quickStarting ? 'Запуск…' : 'Начать опрос'}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Messages list */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2">
              {msgLoading && (
                <div className="flex justify-center py-8 text-[color:var(--color-muted-foreground)]">
                  <Loader2 size={20} className="animate-spin" />
                </div>
              )}
              {msgError && (
                <div className="text-xs text-red-500 text-center py-4">{msgError}</div>
              )}
              {!msgLoading && !msgError && messages.length === 0 && (
                <div className="text-xs text-[color:var(--color-muted-foreground)] text-center py-8">
                  Сообщений пока нет
                </div>
              )}
              {messages.map(m => {
                const isEmployer = m.author_type === 'employer';
                return (
                  <div key={m.id} className={`flex ${isEmployer ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[78%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
                      isEmployer
                        ? 'bg-[color:var(--color-primary)] text-white rounded-br-sm'
                        : 'bg-[color:var(--color-muted)] text-[color:var(--color-foreground)] rounded-bl-sm'
                    }`}>
                      {!isEmployer && m.author_name && (
                        <div className="text-[10px] font-medium opacity-60 mb-1">{m.author_name}</div>
                      )}
                      <p className="whitespace-pre-wrap break-words">{m.text}</p>
                      <div className={`text-[10px] mt-1 opacity-60 ${isEmployer ? 'text-right' : ''}`}>
                        {fmtMsgTime(m.created_at)}
                      </div>
                    </div>
                  </div>
                );
              })}
              <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div className="border-t border-[color:var(--color-border)] px-4 py-3 flex gap-2 items-end">
              <textarea
                rows={1}
                value={text}
                onChange={e => setText(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                placeholder="Написать кандидату..."
                className="flex-1 resize-none input text-sm py-2 max-h-28"
                style={{ minHeight: '38px' }}
              />
              <button
                onClick={handleSend}
                disabled={!text.trim() || sending}
                className="flex-shrink-0 w-9 h-9 flex items-center justify-center rounded-xl bg-[color:var(--color-primary)] text-white disabled:opacity-40 hover:opacity-90 transition-opacity"
              >
                {sending ? <Loader2 size={15} className="animate-spin" /> : <SendHorizonal size={15} />}
              </button>
            </div>
          </div>
        )}

        {tab === 'profile' && (
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
            {!candidate.profile ? (
              <div className="text-sm text-[color:var(--color-muted-foreground)] text-center py-8">
                <p>Профиля нет — эта функция была частью старого ИИ-интервью и больше не используется.</p>
              </div>
            ) : (() => {
              const p = candidate.profile;
              const recBadge = {
                invite:  { label: '✅ Пригласить', color: 'bg-emerald-100 text-emerald-700' },
                reserve: { label: '🔶 В резерв',    color: 'bg-amber-100 text-amber-700' },
                reject:  { label: '❌ Отказать',    color: 'bg-red-100 text-red-700' },
              }[p.recommendation] || { label: '❓ Не определено', color: 'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)]' };
              return (
                <>
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="flex items-center gap-2">
                      <span className="text-2xl font-semibold">{p.score ?? '?'}</span>
                      <span className="text-sm text-[color:var(--color-muted-foreground)]">/ 100</span>
                    </div>
                    <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${recBadge.color}`}>{recBadge.label}</span>
                  </div>
                  {p.score_reason && (
                    <p className="text-xs text-[color:var(--color-muted-foreground)]">{p.score_reason}</p>
                  )}

                  {p.summary && (
                    <div className="rounded-xl border border-[color:var(--color-border)] p-3.5">
                      <p className="text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1.5 uppercase tracking-wide">Резюме</p>
                      <p className="text-sm whitespace-pre-wrap leading-relaxed">{p.summary}</p>
                    </div>
                  )}

                  {!!(p.strengths || []).length && (
                    <div className="rounded-xl border border-emerald-100 bg-emerald-50 p-3.5">
                      <p className="text-xs font-medium text-emerald-700 mb-1.5 uppercase tracking-wide">Сильные стороны</p>
                      <ul className="space-y-1">
                        {p.strengths.map((s, i) => <li key={i} className="text-sm text-emerald-900">+ {s}</li>)}
                      </ul>
                    </div>
                  )}

                  {!!(p.red_flags || []).length && (
                    <div className="rounded-xl border border-red-100 bg-red-50 p-3.5">
                      <p className="text-xs font-medium text-red-700 mb-1.5 uppercase tracking-wide">Красные флаги</p>
                      <ul className="space-y-1">
                        {p.red_flags.map((f, i) => <li key={i} className="text-sm text-red-900">⚠ {f}</li>)}
                      </ul>
                    </div>
                  )}

                  {!!(p.custom_answers || []).length && (
                    <div className="rounded-xl border border-[color:var(--color-border)] p-3.5">
                      <p className="text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1.5 uppercase tracking-wide">Ответы на вопросы рекрутера</p>
                      <div className="space-y-1.5">
                        {p.custom_answers.map((a, i) => (
                          <p key={i} className="text-sm"><span className="font-medium">{a.question}:</span> {a.answer || '—'}</p>
                        ))}
                      </div>
                    </div>
                  )}

                  {(p.salary_expectation || p.availability) && (
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      {p.salary_expectation && (
                        <div className="rounded-xl border border-[color:var(--color-border)] p-3">
                          <p className="text-xs text-[color:var(--color-muted-foreground)] mb-0.5">Ожидания по ЗП</p>
                          <p>{p.salary_expectation}</p>
                        </div>
                      )}
                      {p.availability && (
                        <div className="rounded-xl border border-[color:var(--color-border)] p-3">
                          <p className="text-xs text-[color:var(--color-muted-foreground)] mb-0.5">Доступность</p>
                          <p>{p.availability}</p>
                        </div>
                      )}
                    </div>
                  )}

                  {!!(p.tags || []).length && (
                    <div className="flex flex-wrap gap-1.5">
                      {p.tags.map((t, i) => (
                        <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-[color:var(--color-bg-secondary)] text-[color:var(--color-muted-foreground)]">#{t}</span>
                      ))}
                    </div>
                  )}

                  {p.recommendation_reason && (
                    <p className="text-xs text-[color:var(--color-muted-foreground)] pt-2 border-t border-[color:var(--color-border)]">
                      {p.recommendation_reason}
                    </p>
                  )}

                  {candidate.profile_generated_at && (
                    <p className="text-xs text-[color:var(--color-muted-foreground)] flex items-center gap-1.5 pt-1">
                      <Clock size={12} /> Сформирован {fmtMsgTime(candidate.profile_generated_at)}
                    </p>
                  )}
                </>
              );
            })()}
          </div>
        )}

        {/* ── Footer ── */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-6 py-4 border-t border-[color:var(--color-border)] bg-[color:var(--color-muted)]/10">
          <button onClick={() => { onClose(); onEdit(candidate); }}
            className="order-1 sm:order-2 w-full sm:w-auto btn btn--primary text-sm flex items-center justify-center gap-1.5">
            <Pencil size={14} /> Редактировать
          </button>
          <div className="order-2 sm:order-1 flex items-center gap-2 flex-wrap">
            <button onClick={() => { onDelete(candidate.id); onClose(); }}
              className="flex items-center gap-1.5 text-sm text-red-500 hover:text-red-700 transition-colors">
              <Trash2 size={14} /> Удалить
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Candidate card ─────────────────────────────────────────────────
function CandidateCard({ c, onClick, onDragStart, onDragEnd, selectionMode, selected, onToggle }) {
  function handleClick(e) {
    if (selectionMode) { onToggle(c.id); return; }
    onClick(c);
  }
  const flags = c.flags || [];
  const progressAnswered = c.progress?.answered ?? 0;
  const progressTotal = c.progress?.total ?? 0;
  // Реплика кандидата выделяется, наша — приглушается: сканируя колонку,
  // ищут именно то, на что ещё не ответили.
  const fromCandidate = c.last_message_from !== 'employer';
  return (
    <div
      draggable={!selectionMode}
      onDragStart={e => {
        e.dataTransfer.setData('text/plain', String(c.id));
        e.dataTransfer.effectAllowed = 'move';
        onDragStart?.(c.id);
      }}
      onDragEnd={() => onDragEnd?.()}
      onClick={handleClick}
      className={`w-full text-left border rounded-xl px-3 py-2.5 shadow-sm transition-all group select-none
        ${selectionMode ? 'cursor-pointer' : 'cursor-grab active:cursor-grabbing hover:shadow-md'}
        ${selected
          ? 'bg-[color:var(--color-primary)]/8 border-[color:var(--color-primary)]/50'
          : 'bg-[color:var(--color-surface)] border-[color:var(--color-border)] hover:border-[color:var(--color-primary)]/40'
        }`}
    >
      {/* Имя переносится на вторую строку, а не обрезается: «Захаренкова …»
          не отвечает на вопрос, чья это карточка, — а именно по имени её и
          ищут глазами. Возраст и площадка ушли вправо, чтобы не отъедать у
          имени ширину в той же строке. */}
      <div className="flex items-start justify-between gap-1.5">
        <div className="flex items-start gap-1.5 min-w-0 flex-1">
          {selectionMode && (
            <span className={`flex-shrink-0 mt-0.5 ${selected ? 'text-[color:var(--color-primary)]' : 'text-[color:var(--color-muted-foreground)]'}`}>
              {selected ? <CheckSquare size={14} /> : <Square size={14} />}
            </span>
          )}
          <span className="text-sm font-semibold leading-snug line-clamp-2 break-words group-hover:text-[color:var(--color-primary)] transition-colors">
            {c.name}
          </span>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          {c.age != null && (
            <span className="text-xs text-[color:var(--color-muted-foreground)]">{c.age} л.</span>
          )}
          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${SRC_BADGE[c.source] || SRC_BADGE.other}`}>
            {srcBadgeLabel(c.source)}
          </span>
        </div>
      </div>

      {/* Флаги — то, ради чего карточку и открывают: видно, требует ли она
          действия, ещё до клика. */}
      {(flags.length > 0 || c.is_new || c.is_paused) && (
        <div className="flex flex-wrap items-center gap-1 mt-2">
          {c.is_new && <CardFlag tone="new" label="новый" />}
          {flags.map(f => (
            <CardFlag
              key={f.code}
              tone={f.escalate ? `${f.code}_escalate` : f.code}
              label={f.label}
              icon={f.code === 'no_answer' ? <PhoneMissed size={9} /> : undefined}
            />
          ))}
          {c.is_paused && <CardFlag tone="paused" label="на паузе" icon={<Pause size={9} />} />}
        </div>
      )}

      {/* Прогресс опроса — «2 из 4» отвечает на вопрос «далеко ли зашло»
          нагляднее, чем сам факт этапа. */}
      {progressTotal > 0 && (
        <div className="mt-2 flex items-center gap-1.5">
          <div className="flex-1 h-1 rounded-full bg-[color:var(--color-bg-secondary)] overflow-hidden">
            <div className="h-full rounded-full bg-[color:var(--color-primary)]"
                 style={{ width: `${Math.round((progressAnswered / progressTotal) * 100)}%` }} />
          </div>
          <span className="text-[10px] text-[color:var(--color-muted-foreground)] flex-shrink-0">
            {progressAnswered}/{progressTotal}
          </span>
        </div>
      )}

      {/* Последнее сообщение: главный ответ на «что там внутри». */}
      {c.last_message_text && (
        <div className="mt-2 flex items-start gap-1.5">
          <MessageCircle
            size={11}
            className={`flex-shrink-0 mt-0.5 ${fromCandidate ? 'text-[color:var(--color-primary)]' : 'text-[color:var(--color-muted-foreground)] opacity-50'}`}
          />
          <p className={`text-xs leading-snug line-clamp-2 ${fromCandidate
            ? 'text-[color:var(--color-foreground)]'
            : 'text-[color:var(--color-muted-foreground)]'}`}>
            {!fromCandidate && <span className="opacity-60">Вы: </span>}
            {c.last_message_text}
          </p>
        </div>
      )}

      <div className="mt-2 flex items-center justify-between gap-1">
        <span className="text-[10px] text-[color:var(--color-muted-foreground)] opacity-60">
          {fmtDate(c.last_message_at || c.created_at)}
        </span>
        {c.phone && (
          <span className="flex items-center gap-1 text-[10px] text-[color:var(--color-muted-foreground)] opacity-70">
            <Phone size={9} /> {c.phone}
          </span>
        )}
      </div>
    </div>
  );
}

// Подписи флагов приходят с бэкенда (recruitment_stages.flags), чтобы
// формулировка была одинаковой в карточке и в уведомлениях.
const FLAG_TONES = {
  needs_reply: 'bg-amber-100 text-amber-800 border-amber-200',
  silent:      'bg-[color:var(--color-bg-secondary)] text-[color:var(--color-text-muted)] border-[color:var(--color-border)]',
  undelivered: 'bg-red-100 text-red-700 border-red-200',
  no_answer:   'bg-sky-100 text-sky-800 border-sky-200',
  // Третий недозвон подряд — карточка перестаёт быть «просто перезвонить»
  // и требует решения, поэтому меняет тон на тревожный.
  no_answer_escalate: 'bg-orange-100 text-orange-800 border-orange-300',
  new:         'bg-emerald-100 text-emerald-700 border-emerald-200',
  paused:      'bg-amber-100 text-amber-700 border-amber-200',
};

function CardFlag({ tone, label, icon }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-md border ${
      FLAG_TONES[tone] || FLAG_TONES.silent
    }`}>
      {icon}{label}
    </span>
  );
}

// ── Funnel conversion stats (executive summary above the board) ────
function FunnelStats({ candidates, activeStage, onSelectStage }) {
  const total = candidates.length;
  if (!total) return null;
  const hired = candidates.filter(c => c.stage === 'нанят').length;
  const rejected = candidates.filter(c => c.stage === 'отказ').length;
  const inProgress = total - hired - rejected;
  const hireRate = total > 0 ? Math.round((hired / total) * 100) : 0;

  return (
    <div className="px-6 sm:px-10 pt-4 pb-1">
      <div className="app-card p-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="shrink-0">
            <div className="text-[11px] text-[color:var(--color-muted-foreground)]">Всего кандидатов</div>
            <div className="text-xl font-bold text-[color:var(--color-text)]">{total}</div>
          </div>
          <div className="shrink-0">
            <div className="text-[11px] text-[color:var(--color-muted-foreground)]">В работе</div>
            <div className="text-xl font-bold text-[color:var(--color-primary)]">{inProgress}</div>
          </div>
          <div className="shrink-0">
            <div className="text-[11px] text-[color:var(--color-muted-foreground)]">Нанято</div>
            <div className="text-xl font-bold text-[color:var(--color-success)]">{hired}</div>
          </div>
          <div className="shrink-0">
            <div className="text-[11px] text-[color:var(--color-muted-foreground)]">Конверсия в найм</div>
            <div className="text-xl font-bold" style={{ color: hireRate >= 15 ? 'var(--color-success)' : hireRate >= 5 ? 'var(--color-warning)' : 'var(--color-danger)' }}>{hireRate}%</div>
          </div>
          <div className="flex-1 min-w-[200px] flex items-center gap-1.5 flex-wrap">
            {STAGES.map(stage => {
              const count = candidates.filter(c => c.stage === stage.key).length;
              const pct = total > 0 ? (count / total) * 100 : 0;
              const isActive = activeStage === stage.key;
              return (
                <button key={stage.key} type="button" onClick={() => onSelectStage?.(isActive ? null : stage.key)}
                  className={`flex flex-col items-center gap-1 px-2 py-1 rounded-lg transition-colors ${onSelectStage ? 'cursor-pointer hover:bg-[color:var(--color-bg-secondary)]' : ''} ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}>
                  <span className="text-[10px] text-[color:var(--color-muted-foreground)] whitespace-nowrap">{stage.label}</span>
                  <span className="text-xs font-semibold">{count}</span>
                  <div className="w-12 h-1 rounded-full bg-[color:var(--color-bg-secondary)] overflow-hidden">
                    <div className={`h-full rounded-full ${stage.dot}`} style={{ width: `${pct}%` }} />
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Kanban board (desktop) ─────────────────────────────────────────
function KanbanBoard({ candidates, onCardClick, onAddClick, onDrop, selectionMode, selectedIds, onToggle }) {
  const [dragOver, setDragOver] = useState(null);
  const [dragging, setDragging] = useState(null);
  const scrollRef = useRef(null);
  // Показывать стрелки только когда листать действительно есть куда —
  // иначе они висят как украшение и врут о состоянии доски.
  const [overflow, setOverflow] = useState({ left: false, right: false });

  const syncOverflow = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setOverflow({
      left: el.scrollLeft > 4,
      right: el.scrollLeft + el.clientWidth < el.scrollWidth - 4,
    });
  }, []);

  useEffect(() => {
    syncOverflow();
    const el = scrollRef.current;
    if (!el) return;
    // ResizeObserver, а не событие window: доска сужается ещё и при
    // сворачивании списка вакансий, когда размер окна не меняется.
    const ro = new ResizeObserver(syncOverflow);
    ro.observe(el);
    return () => ro.disconnect();
  }, [syncOverflow, candidates.length]);

  function scrollByColumn(dir) {
    const el = scrollRef.current;
    if (!el) return;
    const col = el.querySelector('[data-kanban-col]');
    el.scrollBy({ left: dir * ((col?.offsetWidth || 220) + 12), behavior: 'smooth' });
  }

  return (
    <div className="relative">
      {/* Стрелки поверх доски. Колесо мыши здесь намеренно не перехватывается:
          доска занимает почти весь экран, и превращать вертикальную прокрутку
          в горизонтальную значило бы отобрать прокрутку страницы. Нативный
          Shift+колесо при этом работает как обычно. */}
      {overflow.left && (
        <ScrollArrow side="left" onClick={() => scrollByColumn(-1)} />
      )}
      {overflow.right && (
        <ScrollArrow side="right" onClick={() => scrollByColumn(1)} />
      )}
      <div ref={scrollRef} onScroll={syncOverflow}
           className="overflow-x-auto pb-4 snap-x snap-proximity scroll-smooth">
        <div className="flex gap-3">
        {STAGES.map(stage => {
          const cards = candidates.filter(c => c.stage === stage.key);
          const isTarget = dragOver === stage.key;
          const isDragSrc = dragging != null && candidates.find(c => c.id === dragging)?.stage === stage.key;
          const colSelected = cards.filter(c => selectedIds.has(c.id)).length;
          const needsAttention = cards.filter(
            c => (c.flags || []).some(f => f.code === 'needs_reply' || f.code === 'undelivered')
          ).length;
          return (
            // Колонки тянутся по доступной ширине, но не уже 250px: на 200
            // карточка становится теснее прежней фиксированной (230), и имя
            // с фамилией переставали помещаться. Приоритет за читаемостью
            // карточки — если семь колонок не влезают, доска прокручивается
            // стрелками, а вот обрезанное имя ничем не компенсируешь.
            <div key={stage.key} id={`kanban-col-${stage.key}`} data-kanban-col
                 className="flex-1 min-w-[250px] max-w-[340px] flex flex-col snap-start">
              <div className="flex items-center justify-between mb-3 px-0.5">
                <div className="flex items-center gap-2">
                  {selectionMode && cards.length > 0 && (
                    <button
                      onClick={() => cards.forEach(c => { if (!selectedIds.has(c.id)) onToggle(c.id); })}
                      className="text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-primary)]"
                      title="Выбрать всех в колонке"
                    >
                      {colSelected === cards.length ? <CheckSquare size={13} className="text-[color:var(--color-primary)]" /> : <Square size={13} />}
                    </button>
                  )}
                  <span className={`w-2 h-2 rounded-full ${stage.dot}`} />
                  <span className="text-sm font-semibold">{stage.label}</span>
                  <span className="text-[10px] text-[color:var(--color-muted-foreground)] bg-[color:var(--color-muted)]/60 rounded-full px-1.5 py-0.5 min-w-[20px] text-center">
                    {cards.length}
                  </span>
                  {/* Сколько в колонке ждут ответа — чтобы не проглядеть их
                      среди прочих, не разворачивая каждую карточку. */}
                  {needsAttention > 0 && (
                    <span
                      title={`${needsAttention} ждут вашего ответа`}
                      className="text-[10px] font-semibold text-amber-800 bg-amber-100 border border-amber-200 rounded-full px-1.5 py-0.5"
                    >
                      {needsAttention} ⚠
                    </span>
                  )}
                </div>
                {!selectionMode && (
                  <button
                    onClick={() => onAddClick(stage.key)}
                    title={`Добавить в «${stage.label}»`}
                    className="w-6 h-6 flex items-center justify-center rounded-lg text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-muted)] hover:text-[color:var(--color-foreground)] transition-colors"
                  >
                    <Plus size={14} />
                  </button>
                )}
              </div>

              <div
                onDragOver={e => { if (selectionMode) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; setDragOver(stage.key); }}
                onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget)) setDragOver(null); }}
                onDrop={e => {
                  e.preventDefault();
                  const id = parseInt(e.dataTransfer.getData('text/plain'));
                  if (id) onDrop(id, stage.key);
                  setDragOver(null);
                }}
                className={`flex-1 rounded-xl border-t-2 ${stage.border} bg-[color:var(--color-muted)]/20 p-2 flex flex-col gap-2 min-h-[120px] transition-all ${
                  isTarget && !isDragSrc ? 'ring-2 ring-inset ring-[color:var(--color-primary)]/50 bg-[color:var(--color-primary)]/5' : ''
                }`}
              >
                {cards.map(c => (
                  <CandidateCard
                    key={c.id}
                    c={c}
                    onClick={onCardClick}
                    onDragStart={id => setDragging(id)}
                    onDragEnd={() => { setDragging(null); setDragOver(null); }}
                    selectionMode={selectionMode}
                    selected={selectedIds.has(c.id)}
                    onToggle={onToggle}
                  />
                ))}
                {cards.length === 0 && (
                  <button
                    onClick={() => onAddClick(stage.key)}
                    className={`flex-1 flex items-center justify-center text-xs text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-primary)] cursor-pointer transition-colors rounded-lg py-4 ${
                      isTarget ? 'text-[color:var(--color-primary)]' : ''
                    }`}
                  >
                    {isTarget ? '↓ Перетащить сюда' : '+ добавить'}
                  </button>
                )}
                {cards.length > 0 && isTarget && !isDragSrc && (
                  <div className="h-10 rounded-lg border-2 border-dashed border-[color:var(--color-primary)]/40 flex items-center justify-center text-xs text-[color:var(--color-primary)]/60">
                    ↓ Сюда
                  </div>
                )}
              </div>
            </div>
          );
        })}
        </div>
      </div>
    </div>
  );
}

function ScrollArrow({ side, onClick }) {
  return (
    <button
      onClick={onClick}
      aria-label={side === 'left' ? 'Предыдущие этапы' : 'Следующие этапы'}
      className={`absolute top-1/2 -translate-y-1/2 z-10 w-8 h-8 rounded-full flex items-center justify-center
        bg-[color:var(--color-surface)] border border-[color:var(--color-border)] shadow-md
        text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-primary)]
        hover:border-[color:var(--color-primary)]/40 transition-colors
        ${side === 'left' ? '-left-3' : '-right-3'}`}
    >
      <ChevronDown size={16} className={side === 'left' ? 'rotate-90' : '-rotate-90'} />
    </button>
  );
}

// ── Mobile board (tabs + list) ─────────────────────────────────────
function MobileBoard({ candidates, onCardClick, onAddClick, selectionMode, selectedIds, onToggle }) {
  const [activeStage, setActiveStage] = useState('новый');
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
        {filtered.map(c => (
          <CandidateCard
            key={c.id} c={c} onClick={onCardClick}
            selectionMode={selectionMode} selected={selectedIds.has(c.id)} onToggle={onToggle}
          />
        ))}
        {filtered.length === 0 && (
          <div className="text-center py-8 text-sm text-[color:var(--color-muted-foreground)] italic">
            Нет кандидатов в этапе «{stage.label}»
          </div>
        )}
      </div>

      {!selectionMode && (
        <button onClick={() => onAddClick(activeStage)} className="w-full btn btn-secondary text-sm flex items-center justify-center gap-2">
          <Plus size={16} /> Добавить кандидата
        </button>
      )}
    </div>
  );
}

// ── Bulk actions bar ───────────────────────────────────────────────
function BulkActionsBar({ count, total, onSelectAll, onClear, onMoveStage, onStartScreening, onDelete, loading }) {
  const [stageOpen, setStageOpen] = useState(false);
  return (
    <div className="bulk-actions-bar fixed bottom-[calc(1.5rem+env(safe-area-inset-bottom))] left-1/2 -translate-x-1/2 z-50 flex flex-wrap items-center justify-center gap-2 max-w-[calc(100vw-1rem)] rounded-2xl shadow-2xl px-4 py-3 text-sm">
      <span className="font-semibold text-white/90 mr-1">{count} выбрано</span>
      <button
        onClick={onSelectAll}
        className="text-xs text-white/60 hover:text-white px-2 py-1 rounded-lg hover:bg-white/10 transition-colors"
      >
        Все {total}
      </button>
      <div className="w-px h-5 bg-white/20" />

      {/* Move to stage */}
      <div className="relative">
        <button
          onClick={() => setStageOpen(o => !o)}
          disabled={loading}
          className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 transition-colors disabled:opacity-50"
        >
          Перенести <ChevronDown size={13} />
        </button>
        {stageOpen && (
          <div className="absolute bottom-full mb-2 left-0 bg-[color:var(--color-surface)] text-[color:var(--color-text)] rounded-xl shadow-xl border border-[color:var(--color-border)] overflow-hidden min-w-[160px]">
            {STAGES.map(s => (
              <button
                key={s.key}
                onClick={() => { setStageOpen(false); onMoveStage(s.key); }}
                className={`w-full text-left flex items-center gap-2 px-3 py-2 text-sm hover:bg-[color:var(--color-control-bg-hover)] transition-colors`}
              >
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${s.dot}`} />
                {s.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <button
        onClick={onStartScreening}
        disabled={loading}
        className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 transition-colors disabled:opacity-50"
        title="Запустить быстрый опрос всем выбранным (hh.ru/Авито, у кого он ещё не идёт)"
      >
        <SendHorizonal size={13} /> Начать опрос
      </button>
      <button
        onClick={onDelete}
        disabled={loading}
        className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-red-500/80 hover:bg-red-500 transition-colors disabled:opacity-50"
      >
        <Trash2 size={13} /> Удалить
      </button>
      <button
        onClick={onClear}
        className="ml-1 w-7 h-7 flex items-center justify-center rounded-full hover:bg-white/10 transition-colors text-white/60 hover:text-white"
        title="Снять выделение"
      >
        <X size={15} />
      </button>
    </div>
  );
}

// ── Interview schedule view ────────────────────────────────────────
function InterviewSchedule({ onCandidateClick }) {
  const [interviews, setInterviews] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get('/recruitment/interviews')
      .then(r => setInterviews(r.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="py-16 text-center text-sm text-[color:var(--color-muted-foreground)]">Загрузка...</div>;
  if (!interviews.length) return (
    <div className="flex flex-col items-center justify-center py-20 text-[color:var(--color-muted-foreground)]">
      <Calendar size={44} className="mb-3 opacity-20" />
      <p className="text-sm">Нет запланированных собеседований</p>
    </div>
  );

  // Group by date
  const byDate = {};
  for (const c of interviews) {
    const d = c.interview_date || 'Дата не указана';
    if (!byDate[d]) byDate[d] = [];
    byDate[d].push(c);
  }
  // Sort groups by date
  const sortedDates = Object.keys(byDate).sort((a, b) => {
    if (a === 'Дата не указана') return 1;
    if (b === 'Дата не указана') return -1;
    return a.localeCompare(b);
  });

  function fmtGroupDate(iso) {
    if (iso === 'Дата не указана') return iso;
    try {
      return new Date(iso).toLocaleDateString('ru-RU', {
        weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
      });
    } catch { return iso; }
  }

  return (
    <div className="p-5 space-y-6">
      {sortedDates.map(date => (
        <div key={date}>
          <h3 className="text-sm font-semibold text-[color:var(--color-muted-foreground)] uppercase tracking-wide mb-3 capitalize">
            {fmtGroupDate(date)}
          </h3>
          <div className="space-y-2">
            {byDate[date]
              .sort((a, b) => (a.interview_time || '').localeCompare(b.interview_time || ''))
              .map(c => (
                <div
                  key={c.id}
                  onClick={() => onCandidateClick?.(c)}
                  className="flex items-center gap-3 p-3 rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-surface)] hover:bg-[color:var(--color-muted)]/20 cursor-pointer transition-colors"
                >
                  <div className="w-8 h-8 rounded-full bg-violet-100 text-violet-700 flex items-center justify-center flex-shrink-0 text-sm font-bold">
                    {(c.name || '?')[0].toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm truncate">{c.name}</p>
                    {c.vacancy_title && <p className="text-xs text-[color:var(--color-muted-foreground)] truncate">{c.vacancy_title}</p>}
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0 text-sm text-[color:var(--color-muted-foreground)]">
                    {c.interview_time && (
                      <span className="flex items-center gap-1"><Clock size={13} />{c.interview_time}</span>
                    )}
                    {c.interview_place && (
                      <span className="text-xs max-w-[120px] truncate">{c.interview_place}</span>
                    )}
                  </div>
                </div>
              ))
            }
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────
export default function Recruitment() {
  const { isMobile } = useViewport();
  const { toast } = useToast();
  const [vacancies,       setVacancies]       = useState([]);
  const [selectedId,      setSelectedId]      = useState(null);
  const [candidates,      setCandidates]      = useState([]);
  const [loading,         setLoading]         = useState(true);
  const [cLoading,        setCLoading]        = useState(false);
  const [showClosed,      setShowClosed]      = useState(false);
  const [error,           setError]           = useState(null);
  const [vacancyModal,    setVacancyModal]    = useState(null);
  const [candModal,       setCandModal]       = useState(null);
  const [detailModal,     setDetailModal]     = useState(null);
  const [interviewModal,  setInterviewModal]  = useState(null);
  const [showVacList,     setShowVacList]     = useState(!isMobile);
  const [showIntegrations,setShowIntegrations]= useState(false);
  const [showStrategies,  setShowStrategies]  = useState(false);
  const [showGlobalKb,    setShowGlobalKb]    = useState(false);
  const [showTemplates,   setShowTemplates]   = useState(false);
  const [hhToast,         setHhToast]         = useState('');
  // bulk selection
  const [selectionMode,   setSelectionMode]   = useState(false);
  const [selectedIds,     setSelectedIds]     = useState(new Set());
  const [bulkLoading,     setBulkLoading]     = useState(false);
  // Подтверждение отказа (hh.ru и Авито)
  const [hhDiscardConfirm, setHhDiscardConfirm] = useState(null); // {candidateId, newStage, candidate}
  const DEFAULT_REJECTION_MSG = 'Здравствуйте! К сожалению, ваша кандидатура не подошла для данной вакансии. Спасибо за проявленный интерес, желаем удачи в поиске работы!';
  const [rejectionMsg, setRejectionMsg] = useState(DEFAULT_REJECTION_MSG);
  const [msgTemplates, setMsgTemplates] = useState([]);
  useEffect(() => {
    api.get('/config/message-templates').then(r => setMsgTemplates(r.data || [])).catch(() => {});
  }, []);

  const [mainView, setMainView] = useState('funnel'); // 'funnel' | 'interviews'

  function toggleSelection(id) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }
  function exitSelection() { setSelectionMode(false); setSelectedIds(new Set()); }

  async function bulkMoveStage(newStage) {
    if (!selectedIds.size) return;
    if (newStage === 'собеседование') {
      // For bulk move to interview, skip the interview form and just move
      // (form is only shown for single-card drag)
    }
    setBulkLoading(true);
    try {
      await Promise.all([...selectedIds].map(id =>
        api.patch(`/recruitment/candidates/${id}`, { stage: newStage })
      ));
      await loadCandidates();
      exitSelection();
    } catch (e) { setError(e.message); }
    finally { setBulkLoading(false); }
  }

  async function bulkDelete() {
    if (!selectedIds.size) return;
    if (!window.confirm(`Удалить ${selectedIds.size} кандидатов?`)) return;
    setBulkLoading(true);
    try {
      await Promise.all([...selectedIds].map(id =>
        api.delete(`/recruitment/candidates/${id}`)
      ));
      await loadCandidates();
      exitSelection();
    } catch (e) { setError(e.message); }
    finally { setBulkLoading(false); }
  }

  async function bulkStartScreening() {
    if (!selectedIds.size) return;
    setBulkLoading(true);
    try {
      // Small batches, not one giant Promise.all(Settled) burst: each start
      // fetches its own fresh Avito OAuth token (no caching across the
      // batch — see _get_platform_chat), so 20-30 selected candidates fired
      // at once means 20-30 simultaneous token requests hitting Avito and
      // the DB at the same moment. Chunking keeps that burst small.
      const ids = [...selectedIds];
      const BATCH_SIZE = 5;
      const results = [];
      for (let i = 0; i < ids.length; i += BATCH_SIZE) {
        const batch = ids.slice(i, i + BATCH_SIZE);
        const batchResults = await Promise.allSettled(batch.map(id =>
          api.post(`/recruitment/candidates/${id}/quick-screening`)
        ));
        results.push(...batchResults);
      }
      // allSettled per batch, not all — a mixed selection is normal (some
      // may already be mid-screen, lack quick-mode questions, or not be a
      // job-board candidate at all), and one such rejection must not hide
      // that the rest actually started.
      const failed = results.filter(r => r.status === 'rejected').length;
      const started = results.length - failed;
      await loadCandidates();
      exitSelection();
      if (failed > 0) {
        toast(`Опрос запущен: ${started} из ${results.length}. Не удалось: ${failed} — откройте карточку, там есть причина.`, failed === results.length ? 'error' : 'success');
      } else {
        toast(`Опрос запущен для ${started} кандидатов`, 'success');
      }
    } catch (e) { setError(e.message); }
    finally { setBulkLoading(false); }
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('hh_connected') === '1') {
      setShowIntegrations(true);
      setHhToast('hh.ru успешно подключён!');
      setTimeout(() => setHhToast(''), 5000);
    } else if (params.get('hh_error')) {
      setHhToast(`Ошибка подключения hh.ru: ${params.get('hh_error')}`);
      setTimeout(() => setHhToast(''), 7000);
    }
    if (params.has('hh_connected') || params.has('hh_error')) {
      const url = new URL(window.location.href);
      url.searchParams.delete('hh_connected');
      url.searchParams.delete('hh_error');
      window.history.replaceState({}, '', url.toString());
    }
  }, []);

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

  async function duplicateVacancy(id) {
    try {
      const res = await api.post(`/recruitment/vacancies/${id}/duplicate`);
      setVacancies(prev => [res.data, ...prev]);
      setSelectedId(res.data.id);
      toast('Вакансия скопирована — описание, стратегия и база знаний перенесены', 'success');
    } catch (e) { toast(e.response?.data?.detail || e.message, 'error'); }
  }

  async function saveVacancyAsTemplate(v) {
    const name = window.prompt('Название шаблона', v.title);
    if (!name || !name.trim()) return;
    try {
      await api.post(`/recruitment/vacancies/${v.id}/save-as-template`, { name: name.trim() });
      toast('Шаблон сохранён — он переживёт закрытие или удаление этой вакансии', 'success');
    } catch (e) { toast(e.response?.data?.detail || e.message, 'error'); }
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

  async function resetCandidateHistory(id) {
    setCandidates(prev => prev.map(c => c.id === id ? { ...c, stage: 'новый' } : c));
  }

  function handlePauseToggle(id, isPaused) {
    setCandidates(prev => prev.map(c => c.id === id ? { ...c, is_paused: isPaused } : c));
  }

  async function stageChange(candidateId, newStage, extraFields = {}) {
    try {
      const res = await api.patch(`/recruitment/candidates/${candidateId}`, { stage: newStage, ...extraFields });
      const { warnings, ...candidateData } = res.data;
      setCandidates(prev => prev.map(c => c.id === candidateId ? candidateData : c));
      if (warnings?.length) setError('⚠️ ' + warnings.join(' | '));
    } catch (e) { setError(e.message); }
  }

  function requestStageChange(candidateId, newStage) {
    const candidate = candidates.find(c => c.id === candidateId);
    if (!candidate || candidate.stage === newStage) return;
    if (newStage === 'собеседование') {
      setInterviewModal(candidate);
      return;
    }
    // Отказ подтверждаем для любой площадки, где есть переписка. Раньше
    // условие было только на hh — а откликов с Авито теперь большинство, и
    // они уходили в отказ молча, без единого слова кандидату.
    if (newStage === 'отказ' && rejectionTarget(candidate)) {
      setRejectionMsg(DEFAULT_REJECTION_MSG);
      setHhDiscardConfirm({ candidateId, newStage, candidate });
      return;
    }
    stageChange(candidateId, newStage);
  }

  function handleDrop(candidateId, newStage) {
    requestStageChange(candidateId, newStage);
  }

  async function handleInterviewSave() {
    setInterviewModal(null);
    await loadCandidates();
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
        <div className="flex items-center gap-2 flex-wrap">
          {isMobile && (
            <button onClick={() => setShowVacList(v => !v)} className="btn btn-secondary text-sm">
              {showVacList ? 'Скрыть вакансии' : 'Вакансии'}
            </button>
          )}
          <button
            onClick={() => setShowIntegrations(true)}
            className="btn btn-secondary text-sm flex items-center gap-1.5"
            title="Настройка автоимпорта hh.ru и Авито"
          >
            <Settings size={15} /> Интеграции
          </button>
          <button
            onClick={() => setShowStrategies(true)}
            className="btn btn-secondary text-sm flex items-center gap-1.5"
            title="Управление стратегиями найма"
          >
            <ListChecks size={15} /> Стратегии найма
          </button>
          <button
            onClick={() => setShowGlobalKb(true)}
            className="btn btn-secondary text-sm flex items-center gap-1.5"
            title="Общая база знаний для ИИ-ассистента (все вакансии)"
          >
            <BookOpen size={15} /> Общая база знаний
          </button>
          <button
            onClick={() => setShowTemplates(true)}
            className="btn btn-secondary text-sm flex items-center gap-1.5"
            title="Сохранённые шаблоны вакансий — создать новую вакансию на основе одного из них"
          >
            <FileStack size={15} /> Шаблоны вакансий
          </button>
          <div className="flex items-center rounded-lg border border-[color:var(--color-border)] overflow-hidden">
            <button
              onClick={() => setMainView('funnel')}
              className={`px-3 py-1.5 text-sm transition-colors ${mainView === 'funnel' ? 'bg-[color:var(--color-primary)] text-white' : 'bg-[color:var(--color-control-bg)] text-[color:var(--color-text-muted)] hover:bg-[color:var(--color-muted)]'}`}
            >
              Воронка
            </button>
            <button
              onClick={() => setMainView('interviews')}
              className={`px-3 py-1.5 text-sm transition-colors flex items-center gap-1 ${mainView === 'interviews' ? 'bg-[color:var(--color-primary)] text-white' : 'bg-[color:var(--color-control-bg)] text-[color:var(--color-text-muted)] hover:bg-[color:var(--color-muted)]'}`}
            >
              <Calendar size={13} /> Собеседования
            </button>
          </div>
          <button onClick={() => setVacancyModal('new')} className="btn btn--primary text-sm flex items-center gap-1.5">
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

      {hhToast && (
        <div className={`mx-6 sm:mx-10 mt-3 rounded-xl px-4 py-3 text-sm flex items-center justify-between ${
          hhToast.startsWith('Ошибка')
            ? 'bg-red-50 border border-red-200 text-red-600'
            : 'bg-emerald-50 border border-emerald-200 text-emerald-700'
        }`}>
          {hhToast}
          <button onClick={() => setHhToast('')}><X size={14} /></button>
        </div>
      )}

      {/* Interview schedule view */}
      {mainView === 'interviews' && (
        <InterviewSchedule onCandidateClick={c => setDetailModal(c)} />
      )}

      {/* Funnel conversion summary — click a stage to scroll the board to it */}
      {mainView === 'funnel' && selectedId && (
        <FunnelStats candidates={candidates} onSelectStage={(key) => {
          if (!key) return;
          document.getElementById(`kanban-col-${key}`)?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
        }} />
      )}

      {/* Two-panel layout */}
      {mainView === 'funnel' && <div className={`flex ${isMobile ? 'flex-col' : ''} gap-0`}>
        {/* Свёрнутый список вакансий: 240px — заметная доля доски, а когда
            вакансия одна, панель всё это время держит выбор из одного
            пункта. В свёрнутом виде остаётся полоска, чтобы вернуть её. */}
        {!isMobile && !showVacList && (
          <aside className="flex-shrink-0 w-9 border-r border-[color:var(--color-border)] bg-[color:var(--color-muted)]/10 flex justify-center pt-4">
            <button
              onClick={() => setShowVacList(true)}
              title="Показать список вакансий"
              className="w-7 h-7 flex items-center justify-center rounded-lg text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-muted)] hover:text-[color:var(--color-foreground)] transition-colors"
            >
              <ChevronDown size={15} className="-rotate-90" />
            </button>
          </aside>
        )}

        {/* Left — vacancy list */}
        {showVacList && (
          <aside className={`flex-shrink-0 border-b sm:border-b-0 sm:border-r border-[color:var(--color-border)] bg-[color:var(--color-muted)]/10 ${isMobile ? 'w-full' : 'w-60'}`}>
            <div className="px-4 py-3 border-b border-[color:var(--color-border)] flex items-center justify-between gap-2">
              <label className="flex items-center gap-2 text-xs text-[color:var(--color-muted-foreground)] cursor-pointer">
                <input type="checkbox" checked={showClosed} onChange={e => setShowClosed(e.target.checked)} className="rounded" />
                Показать закрытые
              </label>
              {!isMobile && (
                <button
                  onClick={() => setShowVacList(false)}
                  title="Свернуть — освободить место доске"
                  className="w-6 h-6 flex-shrink-0 flex items-center justify-center rounded-lg text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-muted)] hover:text-[color:var(--color-foreground)] transition-colors"
                >
                  <ChevronDown size={14} className="rotate-90" />
                </button>
              )}
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
                          : 'border-[color:var(--color-border)] bg-[color:var(--color-surface)]'
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
                            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${v.is_open ? 'bg-emerald-100 text-emerald-700' : 'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)]'}`}>
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
                          <button onClick={e => { e.stopPropagation(); duplicateVacancy(v.id); }}
                            title="Дублировать (для повторной публикации)"
                            className="w-6 h-6 flex items-center justify-center rounded hover:bg-[color:var(--color-muted)] text-[color:var(--color-muted-foreground)]">
                            <Copy size={11} />
                          </button>
                          <button onClick={e => { e.stopPropagation(); saveVacancyAsTemplate(v); }}
                            title="Сохранить как шаблон (постоянное хранилище)"
                            className="w-6 h-6 flex items-center justify-center rounded hover:bg-[color:var(--color-muted)] text-[color:var(--color-muted-foreground)]">
                            <FileStack size={11} />
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
                      : 'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)] hover:bg-[color:var(--color-control-bg-hover)]'
                  }`}
                >
                  {selected.is_open ? '● Открыта' : '○ Закрыта'}
                </button>
                <button
                  onClick={() => duplicateVacancy(selected.id)}
                  title="Создать новую вакансию с теми же данными — для повторной публикации"
                  className="text-xs font-medium px-3 py-1.5 rounded-full bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)] hover:bg-[color:var(--color-control-bg-hover)] transition-colors flex items-center gap-1"
                >
                  <Copy size={12} /> Дублировать
                </button>
                <button
                  onClick={() => saveVacancyAsTemplate(selected)}
                  title="Сохранить в постоянное хранилище шаблонов — переживёт закрытие или удаление вакансии"
                  className="text-xs font-medium px-3 py-1.5 rounded-full bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)] hover:bg-[color:var(--color-control-bg-hover)] transition-colors flex items-center gap-1"
                >
                  <FileStack size={12} /> Сохранить как шаблон
                </button>
                <button
                  onClick={() => { if (selectionMode) exitSelection(); else setSelectionMode(true); }}
                  className={`text-xs font-medium px-3 py-1.5 rounded-full transition-colors flex items-center gap-1 ${
                    selectionMode
                      ? 'bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]'
                      : 'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)] hover:bg-[color:var(--color-control-bg-hover)]'
                  }`}
                >
                  <CheckSquare size={13} />
                  {selectionMode ? 'Отменить' : 'Выбрать'}
                </button>
                {!selectionMode && (
                  <button
                    onClick={() => setCandModal({ stage: 'новый' })}
                    className="btn btn--primary text-sm flex items-center gap-1.5"
                  >
                    <Plus size={15} /> Кандидат
                  </button>
                )}
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
                onCardClick={c => { if (selectionMode) toggleSelection(c.id); else setDetailModal(c); }}
                onAddClick={stage => setCandModal({ stage })}
                selectionMode={selectionMode}
                selectedIds={selectedIds}
                onToggle={toggleSelection}
              />
            ) : (
              <KanbanBoard
                candidates={candidates}
                onCardClick={c => setDetailModal(c)}
                onAddClick={stage => setCandModal({ stage })}
                onDrop={handleDrop}
                selectionMode={selectionMode}
                selectedIds={selectedIds}
                onToggle={toggleSelection}
              />
            )}
          </div>
        </div>
      </div>}

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
          onStageChange={requestStageChange}
          onResetHistory={resetCandidateHistory}
          onPauseToggle={handlePauseToggle}
          templates={msgTemplates}
          onCandidateChanged={loadCandidates}
        />
      )}

      {hhDiscardConfirm && (
        <div className="modal-backdrop" style={{ zIndex: 80 }}>
          <div className="modal-card max-w-md w-full">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-9 h-9 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                <X size={18} className="text-red-600" />
              </div>
              <div>
                <h3 className="font-semibold text-base">Подтвердите отказ</h3>
                <p className="text-sm text-[color:var(--color-muted-foreground)] mt-1">
                  {rejectionTarget(hhDiscardConfirm.candidate) === 'hh'
                    ? 'Кандидат получит письмо на hh.ru и увидит статус «Не подходит». Это действие нельзя отменить.'
                    : 'Текст уйдёт кандидату в переписку на Авито. Это действие нельзя отменить.'}
                </p>
              </div>
            </div>
            <div className="mb-4 space-y-2">
              {msgTemplates.filter(t => t.type === 'rejection').length > 0 && (
                <div>
                  <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Шаблон</label>
                  <select
                    className="input w-full text-sm"
                    defaultValue=""
                    onChange={e => { if (e.target.value) setRejectionMsg(e.target.value); }}
                  >
                    <option value="">— выбрать шаблон —</option>
                    {msgTemplates.filter(t => t.type === 'rejection').map((t, i) => (
                      <option key={i} value={t.text}>{t.name}</option>
                    ))}
                  </select>
                </div>
              )}
              <div>
                <label className="block text-sm font-medium mb-1">Текст письма кандидату</label>
                <textarea
                  className="input w-full text-sm"
                  rows={4}
                  value={rejectionMsg}
                  onChange={e => setRejectionMsg(e.target.value)}
                  placeholder="Текст сообщения об отказе..."
                />
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <button
                className="btn btn-secondary text-sm"
                onClick={() => setHhDiscardConfirm(null)}
              >
                Отмена
              </button>
              <button
                className="btn text-sm bg-red-500 hover:bg-red-600 text-white border-red-500"
                onClick={() => {
                  const { candidateId, newStage } = hhDiscardConfirm;
                  setHhDiscardConfirm(null);
                  stageChange(candidateId, newStage, {
                    rejection_message: rejectionMsg.trim() || null,
                  });
                }}
              >
                Отказать и уведомить
              </button>
            </div>
          </div>
        </div>
      )}

      {interviewModal && (
        <InterviewModal
          candidate={interviewModal}
          onSave={handleInterviewSave}
          onClose={() => setInterviewModal(null)}
          templates={msgTemplates}
        />
      )}

      {showIntegrations && (
        <IntegrationsModal
          vacancies={vacancies}
          onClose={() => { setShowIntegrations(false); loadCandidates(); }}
        />
      )}

      {showStrategies && (
        <StrategyModal onClose={() => setShowStrategies(false)} />
      )}

      {showGlobalKb && (
        <KnowledgeBaseModal scope="global" onClose={() => setShowGlobalKb(false)} />
      )}

      {showTemplates && (
        <VacancyTemplatesModal
          onClose={() => setShowTemplates(false)}
          onCreated={v => { setVacancies(prev => [v, ...prev]); setSelectedId(v.id); }}
        />
      )}

      {selectionMode && selectedIds.size > 0 && (
        <BulkActionsBar
          count={selectedIds.size}
          total={candidates.length}
          onSelectAll={() => setSelectedIds(new Set(candidates.map(c => c.id)))}
          onClear={exitSelection}
          onMoveStage={bulkMoveStage}
          onStartScreening={bulkStartScreening}
          onDelete={bulkDelete}
          loading={bulkLoading}
        />
      )}

    </div>
  );
}
