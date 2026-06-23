import { useState, useEffect, useCallback } from 'react';
import { Trash2, FileStack, Plus } from 'lucide-react';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';

export default function VacancyTemplatesModal({ onClose, onCreated }) {
  const { toast } = useToast();
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creatingId, setCreatingId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/recruitment/vacancy-templates');
      setTemplates(res.data || []);
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  async function handleCreate(t) {
    setCreatingId(t.id);
    try {
      const res = await api.post(`/recruitment/vacancy-templates/${t.id}/create-vacancy`);
      toast(`Вакансия «${res.data.title}» создана на основе шаблона`, 'success');
      onCreated?.(res.data);
      onClose();
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    } finally { setCreatingId(null); }
  }

  async function handleDelete(t) {
    if (!window.confirm(`Удалить шаблон «${t.name}»?`)) return;
    try {
      await api.delete(`/recruitment/vacancy-templates/${t.id}`);
      setTemplates(prev => prev.filter(x => x.id !== t.id));
    } catch (e) {
      toast(e.response?.data?.detail || e.message, 'error');
    }
  }

  return (
    <div className="modal-backdrop" style={{ zIndex: 85 }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-xl w-full flex flex-col overflow-hidden" style={{ maxHeight: '85vh' }}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold">Шаблоны вакансий</h3>
          <button onClick={onClose} className="text-xl text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] leading-none">&times;</button>
        </div>
        <p className="text-xs text-[color:var(--color-muted-foreground)] mb-3">
          Шаблон хранится независимо от вакансий — закрытие или удаление вакансии его не затрагивает.
          Сохраните вакансию как шаблон кнопкой «Сохранить как шаблон» в её карточке, а здесь создавайте
          новые вакансии на его основе (название, описание, стратегия, место собеседования и база знаний переносятся).
        </p>
        <div className="flex-1 overflow-y-auto space-y-2">
          {loading ? (
            <div className="text-center py-8 text-sm text-[color:var(--color-muted-foreground)]">Загрузка...</div>
          ) : templates.length === 0 ? (
            <div className="text-center py-8 text-sm text-[color:var(--color-muted-foreground)] flex flex-col items-center gap-2">
              <FileStack size={24} className="opacity-30" />
              Нет сохранённых шаблонов
            </div>
          ) : templates.map(t => (
            <div key={t.id} className="rounded-xl border border-[color:var(--color-border)] p-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">{t.name}</p>
                <p className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5 truncate">{t.title}</p>
                <div className="flex items-center gap-3 mt-1.5 text-xs text-[color:var(--color-muted-foreground)] flex-wrap">
                  {t.strategy_name && <span>Стратегия: {t.strategy_name}</span>}
                  <span>{t.kb_entries_count} вопрос(ов) в базе знаний</span>
                </div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <button onClick={() => handleCreate(t)} disabled={creatingId === t.id}
                  className="btn text-xs flex items-center gap-1 disabled:opacity-50">
                  <Plus size={13} /> {creatingId === t.id ? 'Создание...' : 'Создать вакансию'}
                </button>
                <button onClick={() => handleDelete(t)} className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-red-50 text-red-400 flex-shrink-0">
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
