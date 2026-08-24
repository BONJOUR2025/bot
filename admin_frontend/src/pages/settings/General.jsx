import { useEffect, useState } from 'react';
import { useForm, Controller } from 'react-hook-form';
import {
  RefreshCw, Download, Archive, AlertTriangle, FileSpreadsheet, Database,
} from 'lucide-react';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';
import FilePicker from '../../components/FilePicker.jsx';
import { Section, Field, StatusDot } from './shared.jsx';

export default function SettingsGeneral() {
  const { toast } = useToast();
  const [loaded, setLoaded] = useState(false);
  const { register, handleSubmit, reset, control } = useForm({ defaultValues: {} });

  const [status, setStatus]               = useState(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [archiveBefore, setArchiveBefore] = useState('');
  const [archiving, setArchiving]         = useState(false);
  const [archiveResult, setArchiveResult] = useState(null);
  const [downloading, setDownloading]     = useState(false);

  useEffect(() => { load(); loadStatus(); }, []);

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
    <div className="space-y-6 max-w-3xl">
    <form onSubmit={handleSubmit(save)} className="space-y-6">
      <Section title="Состояние системы">
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3 min-w-0">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <Database size={16} className="text-[color:var(--color-muted-foreground)] flex-shrink-0" />
              <div className="min-w-0">
                <div className="text-sm font-medium">База данных Firebird (Агбис)</div>
                {status?.firebird?.error && (
                  <div className="text-xs text-red-600 mt-0.5 font-mono break-words">{status.firebird.error}</div>
                )}
              </div>
            </div>
            <StatusDot ok={status?.firebird?.ok} loading={statusLoading} />
          </div>
          <div className="flex items-center justify-between gap-3 min-w-0">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <FileSpreadsheet size={16} className="text-[color:var(--color-muted-foreground)] flex-shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium">Excel-файл расчёта зарплаты</div>
                {status?.payroll_excel?.path && (
                  // title — подсказка при наведении на desktop; клик —
                  // скопировать путь целиком (на мобильном подсказка при
                  // наведении недоступна в принципе, поэтому tap-to-copy —
                  // единственный способ получить полный путь без нового
                  // модального окна ради одной строки текста).
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard?.writeText(status.payroll_excel.path)
                        .then(() => toast('Путь скопирован', 'success'))
                        .catch(() => {});
                    }}
                    title={status.payroll_excel.path}
                    className="ui-tap-44 block w-full text-left text-xs text-[color:var(--color-muted-foreground)] mt-0.5 font-mono hover:text-[color:var(--color-text)] transition-colors"
                  >
                    {/* truncate висит на внутреннем span, а не на кнопке:
                        на кнопке он приносит overflow:hidden, который
                        обрезает псевдоэлемент зоны нажатия от .ui-tap-44,
                        и она перестаёт ловить тап выше/ниже строки. */}
                    <span className="block truncate">{status.payroll_excel.path}</span>
                  </button>
                )}
                {status?.payroll_excel?.error && (
                  <div className="text-xs text-red-600 mt-0.5 break-words">{status.payroll_excel.error}</div>
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

      <Section title="Выплаты">
        <Field label="Лимит аванса в месяц (₽)" hint="Максимальная сумма авансов на одного сотрудника в календарный месяц">
          <input type="number" className="input w-full" {...register('max_advance_amount_per_month')} />
        </Field>
      </Section>

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

      <div>
        <button type="submit" className="btn btn--primary">Сохранить настройки</button>
      </div>
    </form>

      <Section title="Резервное копирование">
        <p className="text-sm text-[color:var(--color-muted-foreground)]">
          Скачивает ZIP-архив со всеми JSON-файлами и базой данных hr.db.
          Рекомендуется делать перед масштабными изменениями и в начале каждого месяца.
        </p>
        <button type="button" onClick={downloadBackup} disabled={downloading}
          className="btn btn--success flex items-center gap-2 disabled:opacity-50">
          <Download size={16} className={downloading ? 'animate-bounce' : ''} />
          {downloading ? 'Подготовка…' : 'Скачать резервную копию'}
        </button>
      </Section>

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
    </div>
  );
}
