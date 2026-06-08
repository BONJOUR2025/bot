import { useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';
import { Section } from './shared.jsx';

export default function SettingsTemplates() {
  const { toast } = useToast();
  const [templates, setTemplates] = useState([]);
  const [loaded, setLoaded]       = useState(false);
  const [saving, setSaving]       = useState(false);

  useEffect(() => { load(); }, []);

  async function load() {
    try { const r = await api.get('config/message-templates'); setTemplates(r.data || []); }
    catch {}
    finally { setLoaded(true); }
  }

  async function saveTemplates(list) {
    setSaving(true);
    try {
      await api.put('config/message-templates', list);
      setTemplates(list);
      toast('Шаблоны сохранены', 'success');
    } catch { toast('Ошибка сохранения шаблонов', 'error'); }
    finally { setSaving(false); }
  }

  function addTemplate() {
    setTemplates((prev) => [...prev, { type: 'rejection', name: '', text: '' }]);
  }

  function updateTemplate(i, field, value) {
    setTemplates((prev) => prev.map((t, idx) => (idx === i ? { ...t, [field]: value } : t)));
  }

  function removeTemplate(i) {
    setTemplates((prev) => prev.filter((_, idx) => idx !== i));
  }

  if (!loaded) return <p className="text-center p-10 text-[color:var(--color-muted-foreground)]">Загрузка…</p>;

  return (
    <div className="space-y-6 max-w-3xl">
      <Section title="Шаблоны сообщений (hh.ru)">
        <p className="text-sm text-[color:var(--color-muted-foreground)]">
          Шаблоны доступны при переводе кандидата в статус «Отказ» или «Собеседование».
          В шаблонах собеседования можно использовать теги:{' '}
          <code className="text-xs bg-[color:var(--color-bg-secondary)] px-1 rounded">#name</code>{' '}
          <code className="text-xs bg-[color:var(--color-bg-secondary)] px-1 rounded">#date</code>{' '}
          <code className="text-xs bg-[color:var(--color-bg-secondary)] px-1 rounded">#time</code>{' '}
          <code className="text-xs bg-[color:var(--color-bg-secondary)] px-1 rounded">#place</code>
        </p>
        <div className="space-y-3">
          {templates.map((t, i) => (
            <div key={i} className="border border-[color:var(--color-border)] rounded-lg p-3 space-y-2">
              <div className="flex gap-2 items-center">
                <select
                  className="input text-sm w-36 flex-shrink-0"
                  value={t.type || 'rejection'}
                  onChange={(e) => updateTemplate(i, 'type', e.target.value)}
                >
                  <option value="rejection">Отказ</option>
                  <option value="interview">Собеседование</option>
                </select>
                <input
                  className="input flex-1 text-sm"
                  placeholder="Название шаблона"
                  value={t.name}
                  onChange={(e) => updateTemplate(i, 'name', e.target.value)}
                />
                <button type="button" onClick={() => removeTemplate(i)}
                  className="text-red-400 hover:text-red-600 flex-shrink-0">
                  <Trash2 size={15} />
                </button>
              </div>
              <textarea
                className="input w-full text-sm resize-none"
                rows={3}
                placeholder={t.type === 'interview'
                  ? 'Здравствуйте, #name! Приглашаем на собеседование #date в #time. Место: #place'
                  : 'Текст письма об отказе...'}
                value={t.text}
                onChange={(e) => updateTemplate(i, 'text', e.target.value)}
              />
            </div>
          ))}
          <div className="flex gap-2">
            <button type="button" onClick={addTemplate}
              className="btn text-sm flex items-center gap-1.5">
              <Plus size={14} /> Добавить шаблон
            </button>
            <button type="button" onClick={() => saveTemplates(templates)} disabled={saving}
              className="btn btn--primary text-sm disabled:opacity-50">
              {saving ? 'Сохраняю…' : 'Сохранить шаблоны'}
            </button>
          </div>
        </div>
      </Section>
    </div>
  );
}
