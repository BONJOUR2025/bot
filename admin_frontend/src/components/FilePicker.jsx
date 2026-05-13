import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { FolderOpen, Folder, FileText, ChevronUp, X } from 'lucide-react';
import api from '../api';

function FilePickerModal({ open, onClose, onSelect, ext, title }) {
  const [path, setPath] = useState('');
  const [items, setItems] = useState([]);
  const [parent, setParent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const browse = useCallback(async (p) => {
    setLoading(true);
    setError('');
    try {
      const params = { path: p };
      if (ext) params.ext = ext;
      const res = await api.get('system/browse', { params });
      setPath(res.data.path);
      setParent(res.data.parent);
      setItems(res.data.items);
    } catch (e) {
      setError(e.response?.data?.detail || 'Ошибка загрузки директории');
    } finally {
      setLoading(false);
    }
  }, [ext]);

  useEffect(() => {
    if (open) browse('');
  }, [open, browse]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="bg-[color:var(--color-bg)] border border-[color:var(--color-border)] rounded-xl shadow-xl w-full max-w-lg mx-4 flex flex-col"
        style={{ maxHeight: '75vh' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[color:var(--color-border)]">
          <span className="font-semibold text-sm">{title || 'Выбор файла'}</span>
          <button type="button" onClick={onClose}
            className="text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-fg)]">
            <X size={18} />
          </button>
        </div>

        {/* Current path bar */}
        <div className="px-3 py-2 bg-[color:var(--color-bg-secondary)] border-b border-[color:var(--color-border)] flex items-center gap-2 min-h-[36px]">
          {parent != null && (
            <button type="button" onClick={() => browse(parent)}
              className="shrink-0 p-1 rounded hover:bg-[color:var(--color-border)] text-[color:var(--color-muted-foreground)]">
              <ChevronUp size={16} />
            </button>
          )}
          <span className="font-mono text-xs text-[color:var(--color-muted-foreground)] truncate">
            {path || 'Диски'}
          </span>
        </div>

        {/* File list */}
        <div className="overflow-y-auto flex-1 p-2 space-y-0.5">
          {loading && (
            <p className="text-center text-sm py-6 text-[color:var(--color-muted-foreground)]">Загрузка…</p>
          )}
          {!loading && error && (
            <p className="text-center text-sm py-6 text-red-500">{error}</p>
          )}
          {!loading && !error && items.length === 0 && (
            <p className="text-center text-sm py-6 text-[color:var(--color-muted-foreground)]">Папка пуста</p>
          )}
          {!loading && !error && items.map((item) => (
            <button
              key={item.full_path}
              type="button"
              className="w-full text-left flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-[color:var(--color-bg-secondary)] text-sm transition-colors"
              onClick={() => item.is_dir ? browse(item.full_path) : onSelect(item.full_path)}
            >
              {item.is_dir
                ? <Folder size={16} className="shrink-0 text-yellow-500" />
                : <FileText size={16} className="shrink-0 text-blue-500" />}
              <span className="truncate">{item.name}</span>
            </button>
          ))}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-[color:var(--color-border)] flex justify-end">
          <button type="button" onClick={onClose} className="btn text-sm">Отмена</button>
        </div>
      </div>
    </div>,
    document.body
  );
}

export default function FilePicker({ value, onChange, placeholder, ext, title, className }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <div className="flex gap-2">
        <input
          className={`input flex-1 font-mono text-sm ${className || ''}`}
          placeholder={placeholder}
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
        />
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="btn flex items-center gap-1.5 shrink-0"
        >
          <FolderOpen size={15} />
          Выбрать
        </button>
      </div>
      <FilePickerModal
        open={open}
        onClose={() => setOpen(false)}
        onSelect={(p) => { onChange(p); setOpen(false); }}
        ext={ext}
        title={title}
      />
    </>
  );
}
