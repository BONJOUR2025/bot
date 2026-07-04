import { useEffect, useRef, useState } from 'react';
import { RefreshCw, FileText, Download, Folder, ChevronLeft } from 'lucide-react';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';
import { Section } from './shared.jsx';

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

// What each on-disk folder actually holds — see app/utils/logger.py and the
// modules listed there for exactly which log writes where.
const FOLDER_HINTS = {
  bot: 'Общий лог, ошибки, запуск/остановка ботов (Telegram и VK), вход/выход из админки',
  users: 'Активность каждого сотрудника (Telegram и VK) — один файл на человека',
  payouts: 'Одобрение/отклонение выплат',
  messages: 'Рассылки, сообщения от сотрудников, журнал отправленных сообщений',
  leave_requests: 'Заявки на отпуск/отгул',
  payment_calendar: 'Отправка счетов кассиру',
};

export default function SettingsDiagnostics() {
  const { toast } = useToast();
  const [folders, setFolders] = useState([]);
  const [foldersLoading, setFoldersLoading] = useState(false);
  const [openFolder, setOpenFolder] = useState(null);
  const [selected, setSelected] = useState(null);
  const [content, setContent] = useState('');
  const [totalLines, setTotalLines] = useState(0);
  const [lines, setLines] = useState(500);
  const [contentLoading, setContentLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const preRef = useRef(null);

  useEffect(() => { loadFolders(); }, []);

  useEffect(() => {
    if (selected) loadContent(selected, lines);
  }, [selected, lines]);

  useEffect(() => {
    if (!autoRefresh || !selected) return;
    const id = setInterval(() => loadContent(selected, lines), 5000);
    return () => clearInterval(id);
  }, [autoRefresh, selected, lines]);

  async function loadFolders() {
    setFoldersLoading(true);
    try {
      const res = await api.get('system/logs');
      setFolders(res.data.folders || []);
    } catch {
      toast('Ошибка загрузки списка логов', 'error');
    } finally {
      setFoldersLoading(false);
    }
  }

  async function loadContent(name, lineCount) {
    setContentLoading(true);
    try {
      const res = await api.get('system/logs/content', { params: { name, lines: lineCount } });
      setContent(res.data.content || '');
      setTotalLines(res.data.lines || 0);
      requestAnimationFrame(() => {
        if (preRef.current) preRef.current.scrollTop = 0;
      });
    } catch {
      toast('Ошибка загрузки лога', 'error');
      setContent('');
    } finally {
      setContentLoading(false);
    }
  }

  function downloadCurrent() {
    if (!content) return;
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    Object.assign(document.createElement('a'), { href: url, download: selected.replace(/[\\/]/g, '_') }).click();
    URL.revokeObjectURL(url);
  }

  function openFolderView(folder) {
    setOpenFolder(folder);
    setSelected(null);
    setContent('');
    // Jump straight to the folder's first (or "general") file so it's not
    // an extra click for the common case of one-file-per-folder.
    const first = folder.files.find((f) => f.file === 'app.log') || folder.files[0];
    if (first) setSelected(first.name);
  }

  if (!openFolder) {
    return (
      <div className="space-y-6 max-w-6xl">
        <Section title="Диагностика — журналы">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-[color:var(--color-muted-foreground)]">
              {folders.length ? `${folders.length} папок` : ''}
            </span>
            <button type="button" onClick={loadFolders} disabled={foldersLoading}
              className="btn text-xs flex items-center gap-1.5 disabled:opacity-50">
              <RefreshCw size={13} className={foldersLoading ? 'animate-spin' : ''} /> Обновить
            </button>
          </div>
          {folders.length === 0 && (
            <div className="p-6 text-center text-sm text-[color:var(--color-muted-foreground)]">
              {foldersLoading ? 'Загрузка…' : 'Логи не найдены'}
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {folders.map((folder) => (
              <button
                key={folder.name}
                type="button"
                onClick={() => openFolderView(folder)}
                className="text-left border border-[color:var(--color-border)] rounded-lg p-4 hover:border-[color:var(--color-primary)] hover:bg-[color:var(--color-bg-secondary)] transition-colors"
              >
                <div className="flex items-center gap-2 font-medium">
                  <Folder size={16} className="shrink-0 text-[color:var(--color-primary)]" />
                  <span className="font-mono truncate">{folder.name}</span>
                </div>
                {FOLDER_HINTS[folder.name] && (
                  <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1.5">{FOLDER_HINTS[folder.name]}</p>
                )}
                <p className="text-xs text-[color:var(--color-muted-foreground)] mt-2">
                  {folder.count} {folder.count === 1 ? 'файл' : 'файлов'} · {formatSize(folder.total_size)}
                </p>
              </button>
            ))}
          </div>
        </Section>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-6xl">
      <Section title="Диагностика — журналы">
        <button
          type="button"
          onClick={() => { setOpenFolder(null); setSelected(null); setContent(''); }}
          className="btn text-xs flex items-center gap-1.5 mb-3"
        >
          <ChevronLeft size={13} /> Все папки
        </button>
        <div className="flex flex-col lg:flex-row gap-4">
          <div className="lg:w-64 shrink-0 space-y-2">
            <div className="text-xs font-medium text-[color:var(--color-muted-foreground)] font-mono">{openFolder.name}/</div>
            <div className="border border-[color:var(--color-border)] rounded-lg max-h-[60vh] overflow-y-auto divide-y divide-[color:var(--color-border)]">
              {openFolder.files.map((f) => (
                <button
                  key={f.name}
                  type="button"
                  onClick={() => setSelected(f.name)}
                  className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 transition-colors ${
                    selected === f.name
                      ? 'bg-[color:var(--color-primary)] text-white'
                      : 'hover:bg-[color:var(--color-bg-secondary)]'
                  }`}
                >
                  <FileText size={14} className="shrink-0" />
                  <span className="truncate font-mono text-xs flex-1">{f.file}</span>
                  <span className={`text-xs shrink-0 ${selected === f.name ? 'text-white/80' : 'text-[color:var(--color-muted-foreground)]'}`}>
                    {formatSize(f.size)}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2">
                <label className="text-xs text-[color:var(--color-muted-foreground)]">Строк:</label>
                <select className="input text-sm py-1" value={lines} onChange={(e) => setLines(Number(e.target.value))}>
                  <option value={100}>100</option>
                  <option value={500}>500</option>
                  <option value={1000}>1000</option>
                  <option value={5000}>5000</option>
                </select>
              </div>
              <label className="flex items-center gap-1.5 text-xs text-[color:var(--color-muted-foreground)]">
                <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
                Автообновление (5с)
              </label>
              <button type="button" onClick={() => selected && loadContent(selected, lines)} disabled={contentLoading || !selected}
                className="btn text-xs flex items-center gap-1.5 disabled:opacity-50">
                <RefreshCw size={13} className={contentLoading ? 'animate-spin' : ''} /> Обновить
              </button>
              <button type="button" onClick={downloadCurrent} disabled={!content}
                className="btn text-xs flex items-center gap-1.5 disabled:opacity-50">
                <Download size={13} /> Скачать
              </button>
              {selected && (
                <span className="text-xs text-[color:var(--color-muted-foreground)] ml-auto">
                  {selected} · показано {Math.min(lines, totalLines)} из {totalLines} строк
                </span>
              )}
            </div>
            <pre
              ref={preRef}
              className="bg-[color:var(--color-bg-secondary)] border border-[color:var(--color-border)] rounded-lg p-3 text-xs font-mono overflow-auto h-[60vh] whitespace-pre-wrap break-all"
            >
              {content || (contentLoading ? 'Загрузка…' : 'Выберите файл лога слева')}
            </pre>
          </div>
        </div>
      </Section>
    </div>
  );
}
