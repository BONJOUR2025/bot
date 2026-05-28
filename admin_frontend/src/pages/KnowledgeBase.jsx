import { useEffect, useState } from 'react';
import { Plus, Trash2, Save, ChevronDown, ChevronRight, GripVertical } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

const CATEGORIES = ['Общее', 'Регламенты', 'Технологии', 'Инструкции', 'Условия работы', 'Безопасность'];

export default function KnowledgeBase() {
  const { toast } = useToast();
  const [docs, setDocs]           = useState([]);
  const [selected, setSelected]   = useState(null); // doc id
  const [form, setForm]           = useState({ title: '', category: 'Общее', content: '', order_idx: 0 });
  const [dirty, setDirty]         = useState(false);
  const [saving, setSaving]       = useState(false);
  const [creating, setCreating]   = useState(false);

  useEffect(() => { load(); }, []);

  async function load() {
    try {
      const r = await api.get('knowledge/documents');
      setDocs(r.data || []);
    } catch { toast('Ошибка загрузки', 'error'); }
  }

  function selectDoc(doc) {
    if (dirty && !confirm('Есть несохранённые изменения. Перейти без сохранения?')) return;
    setSelected(doc.id);
    setForm({ title: doc.title, category: doc.category, content: doc.content || '', order_idx: doc.order_idx || 0 });
    setDirty(false);
  }

  function change(field, val) {
    setForm(f => ({ ...f, [field]: val }));
    setDirty(true);
  }

  async function save() {
    if (!selected) return;
    setSaving(true);
    try {
      const r = await api.patch(`knowledge/documents/${selected}`, form);
      setDocs(prev => prev.map(d => d.id === selected ? { ...d, ...r.data } : d));
      setDirty(false);
      toast('Сохранено', 'success');
    } catch { toast('Ошибка сохранения', 'error'); }
    finally { setSaving(false); }
  }

  async function createDoc() {
    setCreating(true);
    try {
      const r = await api.post('knowledge/documents', {
        title: 'Новый документ',
        category: 'Общее',
        content: '',
        order_idx: docs.length,
      });
      setDocs(prev => [...prev, r.data]);
      selectDoc(r.data);
    } catch { toast('Ошибка создания', 'error'); }
    finally { setCreating(false); }
  }

  async function deleteDoc(id) {
    if (!confirm('Удалить документ?')) return;
    try {
      await api.delete(`knowledge/documents/${id}`);
      setDocs(prev => prev.filter(d => d.id !== id));
      if (selected === id) { setSelected(null); setDirty(false); }
      toast('Удалён', 'success');
    } catch { toast('Ошибка удаления', 'error'); }
  }

  // Group docs by category
  const grouped = docs.reduce((acc, d) => {
    (acc[d.category] = acc[d.category] || []).push(d);
    return acc;
  }, {});

  const selectedDoc = docs.find(d => d.id === selected);
  const charCount = form.content.length;
  const approxTokens = Math.round(charCount / 4);
  const approxPages = Math.round(charCount / 2000);

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden gap-0">
      {/* Sidebar */}
      <div className="w-64 shrink-0 border-r border-[color:var(--color-border)] flex flex-col bg-[color:var(--color-bg-secondary)]">
        <div className="p-3 border-b border-[color:var(--color-border)] flex items-center justify-between">
          <span className="text-sm font-semibold">База знаний</span>
          <button onClick={createDoc} disabled={creating}
            className="btn text-xs flex items-center gap-1 py-1 px-2 disabled:opacity-50">
            <Plus size={12} /> Добавить
          </button>
        </div>
        <div className="flex-1 overflow-y-auto py-2">
          {Object.entries(grouped).map(([cat, catDocs]) => (
            <CategoryGroup key={cat} category={cat} docs={catDocs}
              selected={selected} onSelect={selectDoc} onDelete={deleteDoc} />
          ))}
          {docs.length === 0 && (
            <p className="text-xs text-[color:var(--color-muted-foreground)] text-center mt-8 px-4">
              Нет документов. Нажмите «Добавить» чтобы создать первый.
            </p>
          )}
        </div>
      </div>

      {/* Editor */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {selected ? (
          <>
            <div className="p-4 border-b border-[color:var(--color-border)] flex items-center gap-3 flex-wrap">
              <input className="input flex-1 min-w-0 font-medium" value={form.title}
                onChange={e => change('title', e.target.value)} placeholder="Название документа" />
              <select className="input text-sm w-44 shrink-0" value={form.category}
                onChange={e => change('category', e.target.value)}>
                {CATEGORIES.map(c => <option key={c}>{c}</option>)}
              </select>
              <input type="number" className="input w-20 text-sm shrink-0" value={form.order_idx}
                onChange={e => change('order_idx', Number(e.target.value))} title="Порядок сортировки" placeholder="0" />
              <button onClick={save} disabled={saving || !dirty}
                className="btn btn--primary text-sm flex items-center gap-1.5 shrink-0 disabled:opacity-50">
                <Save size={14} /> {saving ? 'Сохраняю…' : 'Сохранить'}
              </button>
            </div>
            <textarea
              className="flex-1 p-4 bg-[color:var(--color-bg)] text-sm font-mono resize-none outline-none border-none leading-relaxed"
              value={form.content}
              onChange={e => change('content', e.target.value)}
              placeholder={"Вставьте текст регламента, инструкции или любой другой документ...\n\nClaude будет отвечать сотрудникам строго на основе этого текста."}
            />
            <div className="px-4 py-2 border-t border-[color:var(--color-border)] flex items-center gap-4 text-xs text-[color:var(--color-muted-foreground)]">
              <span>{charCount.toLocaleString()} симв.</span>
              <span>≈{approxTokens.toLocaleString()} токенов</span>
              <span>≈{approxPages} стр.</span>
              {dirty && <span className="text-amber-500 font-medium">● Несохранено</span>}
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-[color:var(--color-muted-foreground)]">
            <div className="text-center">
              <div className="text-4xl mb-3">📚</div>
              <p className="text-sm">Выберите документ слева или создайте новый</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function CategoryGroup({ category, docs, selected, onSelect, onDelete }) {
  const [open, setOpen] = useState(true);
  return (
    <div>
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] uppercase tracking-wide">
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        {category} <span className="ml-auto font-normal normal-case">{docs.length}</span>
      </button>
      {open && docs.map(doc => (
        <div key={doc.id}
          className={`group flex items-center gap-1 px-3 py-2 cursor-pointer text-sm ${selected === doc.id ? 'bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]' : 'hover:bg-[color:var(--color-muted)]/40'}`}
          onClick={() => onSelect(doc)}>
          <span className="flex-1 truncate">{doc.title}</span>
          <button onClick={e => { e.stopPropagation(); onDelete(doc.id); }}
            className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600 shrink-0">
            <Trash2 size={12} />
          </button>
        </div>
      ))}
    </div>
  );
}
