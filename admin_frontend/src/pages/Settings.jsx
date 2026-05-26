import { useEffect, useState } from 'react';
import { useForm, Controller } from 'react-hook-form';
import {
  CheckCircle, XCircle, RefreshCw, Download, Archive,
  AlertTriangle, FileSpreadsheet, Database, Plus, Trash2,
} from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import FilePicker from '../components/FilePicker.jsx';

function StatusDot({ ok, loading }) {
  if (loading) return <RefreshCw size={14} className="animate-spin text-[color:var(--color-muted-foreground)]" />;
  return ok
    ? <CheckCircle size={16} className="text-green-500" />
    : <XCircle size={16} className="text-red-500" />;
}

function Section({ title, children }) {
  return (
    <div className="app-card p-5 space-y-4">
      <h3 className="font-semibold text-base">{title}</h3>
      {children}
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1">{label}</label>
      {children}
      {hint && <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">{hint}</p>}
    </div>
  );
}

export default function Settings() {
  const { toast } = useToast();
  const [loaded, setLoaded] = useState(false);
  const { register, handleSubmit, reset, control } = useForm({ defaultValues: {} });

  const [status, setStatus]               = useState(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [archiveBefore, setArchiveBefore] = useState('');
  const [archiving, setArchiving]         = useState(false);
  const [archiveResult, setArchiveResult] = useState(null);
  const [downloading, setDownloading]     = useState(false);
  const [testingNotify, setTestingNotify] = useState(false);
  const [templates, setTemplates]         = useState([]);
  const [savingTpl, setSavingTpl]         = useState(false);

  useEffect(() => { load(); loadStatus(); loadTemplates(); }, []);

  async function loadTemplates() {
    try { const r = await api.get('config/rejection-templates'); setTemplates(r.data || []); } catch {}
  }

  async function saveTemplates(list) {
    setSavingTpl(true);
    try {
      await api.put('config/rejection-templates', list);
      setTemplates(list);
      toast('Шаблоны сохранены', 'success');
    } catch { toast('Ошибка сохранения шаблонов', 'error'); }
    finally { setSavingTpl(false); }
  }

  function addTemplate() {
    setTemplates(prev => [...prev, { name: '', text: '' }]);
  }

  function updateTemplate(i, field, value) {
    setTemplates(prev => prev.map((t, idx) => idx === i ? { ...t, [field]: value } : t));
  }

  function removeTemplate(i) {
    setTemplates(prev => prev.filter((_, idx) => idx !== i));
  }

  async function load() {
    try {
      const res = await api.get('config/');
      reset(res.data);
      setLoaded(true);
    } catch { toast('Ошибка загрузки настроек', 'error'); }
  }

  async function loadStatus() {
    setStatusLoading(true);
    try {
      const res = await api.get('system/status');
      setStatus(res.data);
    } catch { setStatus(null); }
    finally { setStatusLoading(false); }
  }

  async function save(values) {
    try {
      await api.patch('config/', values);
      toast('Сохранено', 'success');
      loadStatus();
    } catch { toast('Ошибка сохранения', 'error'); }
  }

  async function downloadBackup() {
    setDownloading(true);
    try {
      const res = await api.get('system/backup', { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const ts  = new Date().toISOString().slice(0, 16).replace('T', '_').replace(':', '-');
      Object.assign(document.createElement('a'), { href: url, download: `backup_${ts}.zip` }).click();
      URL.revokeObjectURL(url);
      toast('Резервная копия скачана', 'success');
    } catch { toast('Ошибка создания резервной копии', 'error'); }
    finally { setDownloading(false); }
  }

  async function runArchive() {
    if (!archiveBefore) { toast('Укажите дату', 'error'); return; }
    if (!confirm(`Архивировать записи до ${archiveBefore}? Данные будут перемещены в отдельные файлы.`)) return;
    setArchiving(true);
    setArchiveResult(null);
    try {
      const res = await api.post('system/archive', { before: archiveBefore });
      setArchiveResult(res.data);
      toast('Архивация завершена', 'success');
    } catch { toast('Ошибка архивации', 'error'); }
    finally { setArchiving(false); }
  }

  if (!loaded) return <p className="text-center p-10 text-[color:var(--color-muted-foreground)]">Загрузка…</p>;

  return (
    <form onSubmit={handleSubmit(save)} className="space-y-6 max-w-3xl">
      <h2 className="text-2xl font-semibold tracking-tight">Настройки</h2>

      {/* System status */}
      <Section title="Состояние системы">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Database size={16} className="text-[color:var(--color-muted-foreground)]" />
              <div>
                <div className="text-sm font-medium">База данных Firebird (Агбис)</div>
                {status?.firebird?.error && (
                  <div className="text-xs text-red-600 mt-0.5 font-mono">{status.firebird.error}</div>
                )}
              </div>
            </div>
            <StatusDot ok={status?.firebird?.ok} loading={statusLoading} />
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <FileSpreadsheet size={16} className="text-[color:var(--color-muted-foreground)]" />
              <div>
                <div className="text-sm font-medium">Excel-файл расчёта зарплаты</div>
                {status?.payroll_excel?.path && (
                  <div className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5 font-mono truncate max-w-xs">
                    {status.payroll_excel.path}
                  </div>
                )}
                {status?.payroll_excel?.error && (
                  <div className="text-xs text-red-600 mt-0.5">{status.payroll_excel.error}</div>
                )}
              </div>
            </div>
            <StatusDot ok={status?.payroll_excel?.ok} loading={statusLoading} />
          </div>
          <button type="button" onClick={loadStatus} disabled={statusLoading}
            className="btn text-xs flex items-center gap-1.5 disabled:opacity-50">
            <RefreshCw size={13} className={statusLoading ? 'animate-spin' : ''} /> Обновить статус
          </button>
        </div>
      </Section>

      {/* Payroll Excel path */}
      <Section title="Расчёт зарплаты">
        <Field
          label="Путь к Excel-файлу (ФОТ)"
          hint="Полный путь к файлу, например C:\Users\hrbon\Desktop\ФОТ 2027.xlsx — обновите в начале каждого года"
        >
          <Controller
            name="payroll_excel_file"
            control={control}
            render={({ field }) => (
              <FilePicker
                value={field.value}
                onChange={field.onChange}
                placeholder="C:\путь\к\файлу.xlsx"
                ext=".xlsx,.xls"
                title="Выбор Excel-файла (ФОТ)"
              />
            )}
          />
        </Field>
        {status?.payroll_excel && !status.payroll_excel.ok && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
            <AlertTriangle size={15} className="mt-0.5 shrink-0" />
            Файл не найден. Обновите путь и сохраните настройки.
          </div>
        )}
      </Section>

      {/* Payouts */}
      <Section title="Выплаты">
        <Field label="Лимит аванса в месяц (₽)" hint="Максимальная сумма авансов на одного сотрудника в календарный месяц">
          <input type="number" className="input w-full" {...register('max_advance_amount_per_month')} />
        </Field>
      </Section>

      {/* Telegram bot */}
      <Section title="Telegram-бот">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="admin_id" hint="ID администратора в Telegram">
            <input className="input w-full font-mono" {...register('admin_id')} />
          </Field>
          <Field label="admin_chat_id" hint="Чат для уведомлений и напоминаний о ДР">
            <input className="input w-full font-mono" {...register('admin_chat_id')} />
          </Field>
          <Field label="card_dispatch_chat_id" hint="Чат для отправки реквизитов карты при выплате">
            <input className="input w-full font-mono" {...register('card_dispatch_chat_id')} />
          </Field>
          <Field label="notification_chat_id" hint="Telegram ID для уведомлений: новые отклики, сообщения с hh.ru, привязка выплат">
            <div className="flex gap-2">
              <input className="input flex-1 font-mono" placeholder="123456789" {...register('notification_chat_id')} />
              <button
                type="button"
                disabled={testingNotify}
                onClick={async () => {
                  setTestingNotify(true);
                  try {
                    const res = await api.post('config/test-notification');
                    if (res.data.ok) toast(res.data.message, 'success');
                    else toast(res.data.error, 'error');
                  } catch (e) {
                    toast(e.response?.data?.detail || e.message, 'error');
                  } finally { setTestingNotify(false); }
                }}
                className="btn text-sm flex items-center gap-1.5 flex-shrink-0 disabled:opacity-50"
              >
                <RefreshCw size={13} className={testingNotify ? 'animate-spin' : ''} />
                Тест
              </button>
            </div>
          </Field>
        </div>
      </Section>

      {/* PDF */}
      <Section title="PDF-отчёты">
        <Field label="Путь к шрифту" hint="Шрифт для генерации PDF-отчётов, например fonts/DejaVuSans.ttf">
          <Controller
            name="font_path"
            control={control}
            render={({ field }) => (
              <FilePicker
                value={field.value}
                onChange={field.onChange}
                placeholder="fonts/DejaVuSans.ttf"
                ext=".ttf,.otf"
                title="Выбор файла шрифта"
              />
            )}
          />
        </Field>
      </Section>

      {/* Rejection message templates */}
      <Section title="Шаблоны писем об отказе (hh.ru)">
        <p className="text-sm text-[color:var(--color-muted-foreground)]">
          Шаблоны доступны при переводе кандидата в статус «Отказ» на странице Подбора персонала.
        </p>
        <div className="space-y-3">
          {templates.map((t, i) => (
            <div key={i} className="border border-[color:var(--color-border)] rounded-lg p-3 space-y-2">
              <div className="flex gap-2 items-center">
                <input
                  className="input flex-1 text-sm"
                  placeholder="Название шаблона"
                  value={t.name}
                  onChange={e => updateTemplate(i, 'name', e.target.value)}
                />
                <button type="button" onClick={() => removeTemplate(i)}
                  className="text-red-400 hover:text-red-600">
                  <Trash2 size={15} />
                </button>
              </div>
              <textarea
                className="input w-full text-sm resize-none"
                rows={3}
                placeholder="Текст письма..."
                value={t.text}
                onChange={e => updateTemplate(i, 'text', e.target.value)}
              />
            </div>
          ))}
          <div className="flex gap-2">
            <button type="button" onClick={addTemplate}
              className="btn text-sm flex items-center gap-1.5">
              <Plus size={14} /> Добавить шаблон
            </button>
            <button type="button" onClick={() => saveTemplates(templates)} disabled={savingTpl}
              className="btn btn--primary text-sm disabled:opacity-50">
              {savingTpl ? 'Сохраняю…' : 'Сохранить шаблоны'}
            </button>
          </div>
        </div>
      </Section>

      {/* Save */}
      <div>
        <button type="submit" className="btn btn--primary">Сохранить настройки</button>
      </div>

      {/* Backup */}
      <Section title="Резервное копирование">
        <p className="text-sm text-[color:var(--color-muted-foreground)]">
          Скачивает ZIP-архив со всеми JSON-файлами и базой данных hr.db.
          Рекомендуется делать перед масштабными изменениями и в начале каждого месяца.
        </p>
        <button type="button" onClick={downloadBackup} disabled={downloading}
          className="btn flex items-center gap-2 bg-green-600 text-white hover:bg-green-700 disabled:opacity-50">
          <Download size={16} className={downloading ? 'animate-bounce' : ''} />
          {downloading ? 'Подготовка…' : 'Скачать резервную копию'}
        </button>
      </Section>

      {/* Archive */}
      <Section title="Архивация старых данных">
        <p className="text-sm text-[color:var(--color-muted-foreground)]">
          Перемещает записи старше указанной даты из рабочих файлов в архивные.
          Затрагивает: штрафы/премии, корректировки, сообщения.
        </p>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Архивировать записи до</label>
            <input type="date" className="input" value={archiveBefore}
              onChange={(e) => setArchiveBefore(e.target.value)} />
          </div>
          <button type="button" onClick={runArchive} disabled={archiving || !archiveBefore}
            className="btn flex items-center gap-2 disabled:opacity-50">
            <Archive size={15} className={archiving ? 'animate-pulse' : ''} />
            {archiving ? 'Архивирую…' : 'Запустить архивацию'}
          </button>
        </div>
        {archiveResult && (
          <div className="rounded-lg border border-[color:var(--color-border)] bg-[color:var(--color-bg-secondary)] p-3 text-sm space-y-1">
            {Object.entries(archiveResult.files || {}).map(([file, info]) => (
              <div key={file} className="flex items-center justify-between gap-4">
                <span className="font-mono text-xs text-[color:var(--color-muted-foreground)]">{file}</span>
                <span>
                  <span className="text-amber-600 font-medium">−{info.archived}</span>
                  <span className="text-[color:var(--color-muted-foreground)] mx-1">/</span>
                  <span className="text-green-600 font-medium">{info.kept} осталось</span>
                </span>
              </div>
            ))}
          </div>
        )}
      </Section>
    </form>
  );
}
