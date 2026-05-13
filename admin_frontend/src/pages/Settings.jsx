import { useEffect, useState, useCallback } from 'react';
import { useForm } from 'react-hook-form';
import {
  CheckCircle, XCircle, RefreshCw, Download, Archive,
  AlertTriangle, FileSpreadsheet, Database,
} from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

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
  const { register, handleSubmit, reset, watch } = useForm({ defaultValues: {} });

  const [status, setStatus]         = useState(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [archiveBefore, setArchiveBefore] = useState('');
  const [archiving, setArchiving]   = useState(false);
  const [archiveResult, setArchiveResult] = useState(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => { load(); loadStatus(); }, []);

  async function load() {
    try {
      const res = await api.get('config/');
      const data = res.data;
      reset({
        ...data,
        payout_types: (data.payout_types || []).join(', '),
        payout_methods: (data.payout_methods || []).join(', '),
        send_reminders_to: (data.send_reminders_to || []).join(', '),
      });
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
    const payload = {
      ...values,
      payout_types: (values.payout_types || '').split(',').map((s) => s.trim()).filter(Boolean),
      payout_methods: (values.payout_methods || '').split(',').map((s) => s.trim()).filter(Boolean),
      send_reminders_to: (values.send_reminders_to || '').split(',').map((s) => s.trim()).filter(Boolean),
    };
    try {
      await api.patch('config/', payload);
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
          hint="Полный путь к файлу, например C:\Users\hrbon\Desktop\ФОТ 2027.xlsx — обновите в начале каждого года при создании нового файла"
        >
          <input className="input w-full font-mono text-sm" placeholder="C:\путь\к\файлу.xlsx"
            {...register('payroll_excel_file')} />
        </Field>
        {status?.payroll_excel && !status.payroll_excel.ok && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
            <AlertTriangle size={15} className="mt-0.5 shrink-0" />
            Файл не найден. Обновите путь и сохраните настройки.
          </div>
        )}
      </Section>

      {/* General */}
      <Section title="Общие">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Название компании">
            <input className="input w-full" placeholder="Название компании" {...register('company_name')} />
          </Field>
          <Field label="Часовой пояс">
            <input className="input w-full" placeholder="Europe/Moscow" {...register('timezone')} />
          </Field>
        </div>
      </Section>

      {/* Payouts */}
      <Section title="Выплаты">
        <Field label="Лимит аванса в месяц (₽)">
          <input type="number" className="input w-full" {...register('max_advance_amount_per_month')} />
        </Field>
        <Field label="Типы выплат (через запятую)">
          <textarea className="input w-full h-16 resize-none text-sm" {...register('payout_types')} />
        </Field>
        <Field label="Способы выплат (через запятую)">
          <textarea className="input w-full h-16 resize-none text-sm" {...register('payout_methods')} />
        </Field>
      </Section>

      {/* Telegram bot */}
      <Section title="Telegram-бот">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="admin_id"><input className="input w-full" {...register('admin_id')} /></Field>
          <Field label="admin_chat_id"><input className="input w-full" {...register('admin_chat_id')} /></Field>
          <Field label="card_dispatch_chat_id"><input className="input w-full" {...register('card_dispatch_chat_id')} /></Field>
        </div>
        <Field label="Welcome-сообщение">
          <textarea className="input w-full h-20 resize-none text-sm" {...register('welcome_message')} />
        </Field>
      </Section>

      {/* Notifications */}
      <Section title="Уведомления">
        <label className="flex items-center gap-2 cursor-pointer text-sm">
          <input type="checkbox" className="w-4 h-4 rounded" {...register('birthday_reminder_enabled')} />
          Напоминать о днях рождения
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Время напоминания">
            <input className="input w-full" placeholder="09:00" {...register('birthday_reminder_time')} />
          </Field>
          <Field label="ID получателей (через запятую)">
            <input className="input w-full" {...register('send_reminders_to')} />
          </Field>
        </div>
      </Section>

      {/* PDF */}
      <Section title="PDF-отчёты">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Путь к шрифту">
            <input className="input w-full font-mono text-sm" {...register('font_path')} />
          </Field>
          <Field label="Формат даты">
            <input className="input w-full" placeholder="%d.%m.%Y" {...register('pdf_date_format')} />
          </Field>
        </div>
        <label className="flex items-center gap-2 cursor-pointer text-sm">
          <input type="checkbox" className="w-4 h-4 rounded" {...register('show_excel_comments')} />
          Показывать комментарии из Excel
        </label>
      </Section>

      {/* Save */}
      <div>
        <button type="submit" className="btn btn--primary">Сохранить настройки</button>
      </div>

      {/* Backup */}
      <Section title="Резервное копирование">
        <p className="text-sm text-[color:var(--color-muted-foreground)]">
          Скачивает ZIP-архив со всеми JSON-файлами данных системы (сотрудники, выплаты, штрафы, планы и др.).
          Рекомендуется делать перед любыми масштабными изменениями и в начале каждого месяца.
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
          Перемещает записи старше указанной даты из рабочих файлов в архивные. Архивные файлы не удаляются — они остаются на сервере.
          Затрагивает: авансы, штрафы/премии, корректировки.
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
