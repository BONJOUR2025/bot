import { useState, useEffect, useCallback } from 'react';
import { X, Pencil, Trash2, Plus, Loader2, Star } from 'lucide-react';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';
import StageBuilder from './StageBuilder.jsx';

const EMPTY_FORM = {
  name: '', description: '', age_min: '', age_max: '', sources_str: '',
  follow_up_enabled: false, follow_up_delay_hours: '', follow_up_message_1: '', follow_up_message_2: '',
  decline_after_hours: '', hh_message_with_link: '', hh_message_no_link: '', away_message: '', ai_model: '',
  stages: null,
};

function StrategyForm({ strategy, onClose, onSaved }) {
  const { toast } = useToast();
  const [form, setForm] = useState(() => strategy
    ? {
        name: strategy.name || '',
        description: strategy.description || '',
        age_min: strategy.age_min ?? '',
        age_max: strategy.age_max ?? '',
        sources_str: strategy.sources_str || '',
        follow_up_enabled: !!strategy.follow_up_enabled,
        follow_up_delay_hours: strategy.follow_up_delay_hours ?? '',
        follow_up_message_1: strategy.follow_up_message_1 || '',
        follow_up_message_2: strategy.follow_up_message_2 || '',
        decline_after_hours: strategy.decline_after_hours ?? '',
        hh_message_with_link: strategy.hh_message_with_link || '',
        hh_message_no_link: strategy.hh_message_no_link || '',
        away_message: strategy.away_message || '',
        ai_model: strategy.ai_model || '',
        stages: strategy.stages || null,
      }
    : EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  useEffect(() => {
    if (form.stages) return;
    api.get('/recruitment/default-stages').then(res => setForm(f => ({ ...f, stages: res.data }))).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function resetStagesToDefault() {
    if (!window.confirm('Заменить текущие этапы стандартным сценарием? Несохранённые изменения этапов будут потеряны.')) return;
    api.get('/recruitment/default-stages').then(res => setForm(f => ({ ...f, stages: res.data }))).catch(e => toast(e.message, 'error'));
  }

  async function save() {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const payload = {
        ...form,
        age_min: form.age_min !== '' ? Number(form.age_min) : null,
        age_max: form.age_max !== '' ? Number(form.age_max) : null,
        follow_up_delay_hours: form.follow_up_delay_hours !== '' ? Number(form.follow_up_delay_hours) : null,
        decline_after_hours: form.decline_after_hours !== '' ? Number(form.decline_after_hours) : null,
      };
      const res = strategy
        ? await api.patch(`/recruitment/strategies/${strategy.id}`, payload)
        : await api.post('/recruitment/strategies', payload);
      onSaved(res.data);
      onClose();
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally { setSaving(false); }
  }

  return (
    <div className="modal-backdrop" style={{ zIndex: 90 }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-lg w-full flex flex-col overflow-hidden" style={{ maxHeight: '90vh' }}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold">{strategy ? 'Редактировать стратегию' : 'Новая стратегия'}</h3>
          <button onClick={onClose} className="text-xl text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] leading-none">&times;</button>
        </div>
        <div className="space-y-3 overflow-y-auto flex-1 pr-1">
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Название *</label>
            <input className="input w-full" value={form.name} onChange={set('name')} placeholder="Стандартный отбор" autoFocus />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Описание</label>
            <textarea className="input w-full min-h-[50px] resize-none" value={form.description} onChange={set('description')} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Возраст от</label>
              <input type="number" className="input w-full" value={form.age_min} onChange={set('age_min')} />
            </div>
            <div>
              <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Возраст до</label>
              <input type="number" className="input w-full" value={form.age_max} onChange={set('age_max')} />
            </div>
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Источники (через запятую)</label>
            <input className="input w-full" value={form.sources_str} onChange={set('sources_str')} placeholder="hh, avito, manual" />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Отказывать автоматически после (часов, пусто = никогда)</label>
            <input type="number" className="input w-full" value={form.decline_after_hours} onChange={set('decline_after_hours')} placeholder="Никогда" />
          </div>
          <div className="rounded-xl border border-[color:var(--color-border)] p-3 space-y-2">
            <div className="flex items-center gap-2">
              <input type="checkbox" id="followUpEnabled" checked={form.follow_up_enabled} onChange={set('follow_up_enabled')} className="rounded" />
              <label htmlFor="followUpEnabled" className="text-sm font-medium cursor-pointer">Авто-напоминания (follow-up)</label>
            </div>
            {form.follow_up_enabled && (
              <div className="space-y-2 pl-1">
                <div>
                  <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Задержка перед напоминанием (часов)</label>
                  <input type="number" className="input w-full" value={form.follow_up_delay_hours} onChange={set('follow_up_delay_hours')} />
                </div>
                <div>
                  <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Сообщение №1</label>
                  <textarea className="input w-full min-h-[50px] resize-none text-sm" value={form.follow_up_message_1} onChange={set('follow_up_message_1')} />
                </div>
                <div>
                  <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Сообщение №2</label>
                  <textarea className="input w-full min-h-[50px] resize-none text-sm" value={form.follow_up_message_2} onChange={set('follow_up_message_2')} />
                </div>
              </div>
            )}
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Сообщение hh.ru (если есть ссылка на Telegram)</label>
            <textarea className="input w-full min-h-[50px] resize-none text-sm" value={form.hh_message_with_link} onChange={set('hh_message_with_link')} />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Сообщение hh.ru (без ссылки)</label>
            <textarea className="input w-full min-h-[50px] resize-none text-sm" value={form.hh_message_no_link} onChange={set('hh_message_no_link')} />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Сообщение «вне рабочего времени»</label>
            <textarea className="input w-full min-h-[50px] resize-none text-sm" value={form.away_message} onChange={set('away_message')} />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Модель ИИ</label>
            <input className="input w-full" value={form.ai_model} onChange={set('ai_model')} placeholder="claude-sonnet-4-6 (по умолчанию)" />
          </div>
          <div className="rounded-xl border border-[color:var(--color-border)] p-3">
            <label className="text-xs font-medium mb-2 block">Этапы интервью (конструктор сценария)</label>
            {form.stages ? (
              <StageBuilder
                stages={form.stages}
                onChange={stages => setForm(f => ({ ...f, stages }))}
                onResetDefault={resetStagesToDefault}
              />
            ) : (
              <div className="text-center py-4 text-sm text-[color:var(--color-muted-foreground)]">Загрузка...</div>
            )}
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

export default function StrategyModal({ onClose, onChanged }) {
  const { toast } = useToast();
  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(null); // null | 'new' | strategy object

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/recruitment/strategies');
      setStrategies(res.data || []);
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  function handleSaved(saved) {
    setStrategies(prev => {
      const exists = prev.find(s => s.id === saved.id);
      return exists ? prev.map(s => s.id === saved.id ? saved : s) : [...prev, saved];
    });
    onChanged?.();
  }

  async function handleDelete(s) {
    if (s.is_builtin) return;
    if (!window.confirm(`Удалить стратегию «${s.name}»?`)) return;
    try {
      await api.delete(`/recruitment/strategies/${s.id}`);
      setStrategies(prev => prev.filter(x => x.id !== s.id));
      onChanged?.();
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    }
  }

  return (
    <div className="modal-backdrop" style={{ zIndex: 85 }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-xl w-full flex flex-col overflow-hidden" style={{ maxHeight: '85vh' }}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold">Стратегии найма</h3>
          <button onClick={onClose} className="text-xl text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] leading-none">&times;</button>
        </div>
        <p className="text-xs text-[color:var(--color-muted-foreground)] mb-3">
          Стратегия определяет авто-напоминания, авто-отказ по таймауту, сообщения hh.ru и модель ИИ для вакансий, к которым она привязана.
        </p>
        <div className="flex-1 overflow-y-auto space-y-2">
          {loading ? (
            <div className="text-center py-8 text-sm text-[color:var(--color-muted-foreground)]">Загрузка...</div>
          ) : strategies.length === 0 ? (
            <div className="text-center py-8 text-sm text-[color:var(--color-muted-foreground)]">Нет стратегий</div>
          ) : strategies.map(s => (
            <div key={s.id} className="rounded-xl border border-[color:var(--color-border)] p-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium truncate">{s.name}</p>
                  {s.is_builtin && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600">
                      <Star size={10} /> встроенная
                    </span>
                  )}
                </div>
                {s.description && <p className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5 truncate">{s.description}</p>}
                <div className="flex items-center gap-3 mt-1.5 text-xs text-[color:var(--color-muted-foreground)] flex-wrap">
                  <span>{s.follow_up_enabled ? `Напоминания: вкл. (через ${s.follow_up_delay_hours ?? '?'} ч.)` : 'Напоминания: выкл.'}</span>
                  <span>Авто-отказ: {s.decline_after_hours != null ? `${s.decline_after_hours} ч.` : 'никогда'}</span>
                  <span>{s.stages?.length ?? 0} этап(ов) интервью</span>
                </div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <button onClick={() => setForm(s)} className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-[color:var(--color-muted)] text-[color:var(--color-muted-foreground)]">
                  <Pencil size={13} />
                </button>
                {!s.is_builtin && (
                  <button onClick={() => handleDelete(s)} className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-red-50 text-red-400">
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="flex justify-end mt-4">
          <button onClick={() => setForm('new')} className="btn btn-primary text-sm flex items-center gap-1.5">
            <Plus size={15} /> Новая стратегия
          </button>
        </div>
      </div>

      {form && (
        <StrategyForm
          strategy={form === 'new' ? null : form}
          onClose={() => setForm(null)}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}
