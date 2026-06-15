import { useEffect, useRef, useState } from 'react';
import { RefreshCw, FileText, Download } from 'lucide-react';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';
import { Section } from './shared.jsx';

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

export default function SettingsDiagnostics() {
  const { toast } = useToast();
  const [files, setFiles] = useState([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [content, setContent] = useState('');
  const [totalLines, setTotalLines] = useState(0);
  const [lines, setLines] = useState(500);
  const [contentLoading, setContentLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const preRef = useRef(null);

  useEffect(() => { loadFiles(); }, []);

  useEffect(() => {
    if (selected) loadContent(selected, lines);
  }, [selected, lines]);

  useEffect(() => {
    if (!autoRefresh || !selected) return;
    const id = setInterval(() => loadContent(selected, lines), 5000);
    return () => clearInterval(id);
  }, [autoRefresh, selected, lines]);

  async function loadFiles() {
    setFilesLoading(true);
    try {
      const res = await api.get('system/logs');
      const list = res.data.files || [];
      setFiles(list);
      if (!selected && list.length) {
        const general = list.find((f) => f.name === 'app.log') || list[0];
        setSelected(general.name);
      }
    } catch {
      toast('Ошибка загрузки списка логов', 'error');
    } finally {
      setFilesLoading(false);
    }
  }

  async function loadContent(name, lineCount) {
    setContentLoading(true);
    try {
      const res = await api.get('system/logs/content', { params: { name, lines: lineCount } });
      setContent(res.data.content || '');
      setTotalLines(res.data.lines || 0);
      requestAnimationFrame(() => {
        if (preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight;
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

  return (
    <div className="space-y-6 max-w-6xl">
      <Section title="Диагностика — журналы">
        <div className="flex flex-col lg:flex-row gap-4">
          <div className="lg:w-64 shrink-0 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-[color:var(--color-muted-foreground)]">Файлы логов</span>
              <button type="button" onClick={loadFiles} disabled={filesLoading}
                className="btn text-xs p-1.5 disabled:opacity-50">
                <RefreshCw size={13} className={filesLoading ? 'animate-spin' : ''} />
              </button>
            </div>
            <div className="border border-[color:var(--color-border)] rounded-lg max-h-[60vh] overflow-y-auto divide-y divide-[color:var(--color-border)]">
              {files.length === 0 && (
                <div className="p-3 text-sm text-[color:var(--color-muted-foreground)]">
                  {filesLoading ? 'Загрузка…' : 'Логи не найдены'}
                </div>
              )}
              {files.map((f) => (
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
                  <span className="truncate font-mono text-xs flex-1">{f.name}</span>
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
