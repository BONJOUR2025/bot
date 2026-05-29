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
    try { const r = await api.get('config/message-templates'); setTemplates(r.data || []); } catch {}
  }

  async function saveTemplates(list) {
    setSavingTpl(true);
    try {
      await api.put('config/message-templates', list);
      setTemplates(list);
      toast('Шаблоны сохранены', 'success');
    } catch { toast('Ошибка сохранения шаблонов', 'error'); }
    finally { setSavingTpl(false); }
  }

  function addTemplate() {
    setTemplates(prev => [...prev, { type: 'rejection', name: '', text: '' }]);
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

      {/* Secretary Mode */}
      <Section title="Telegram Secretary Mode">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Ваш username" hint="Ваш личный username в Telegram (без @). Используется для формирования ссылок-маяков для кандидатов.">
            <div className="flex items-center gap-0">
              <span className="input px-3 py-2 rounded-r-none border-r-0 text-[color:var(--color-muted-foreground)] bg-[color:var(--color-muted)] select-none">@</span>
              <input className="input w-full rounded-l-none" placeholder="username" {...register('tg_personal_username')} />
            </div>
          </Field>
          <Field label="Business Connection ID" hint="ID подключения Secretary Mode. Можно найти в логах бота после подключения в Telegram → Настройки → Бизнес-аккаунт → Чат-боты. Заполняется автоматически при первом входящем сообщении.">
            <input className="input w-full font-mono text-sm" placeholder="вставьте connection_id из логов" {...register('tg_business_connection_id')} />
          </Field>
        </div>
      </Section>

      {/* Automation */}
      <Section title="Автоматизация найма">
        <p className="text-sm text-[color:var(--color-muted-foreground)] mb-3">
          Глобальный переключатель автоматизации находится на странице «Подбор».
          Здесь настраиваются фильтры и база знаний.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
          <Field label="Возраст от" hint="Минимальный возраст кандидата">
            <input type="number" className="input w-full" {...register('automation_age_min')} placeholder="18" />
          </Field>
          <Field label="Возраст до" hint="Максимальный возраст кандидата">
            <input type="number" className="input w-full" {...register('automation_age_max')} placeholder="60" />
          </Field>
          <Field label="Источники" hint="hh, avito, manual — через запятую. Пусто = все.">
            <input className="input w-full" {...register('automation_sources_str')} placeholder="hh,avito" />
          </Field>
        </div>
        <Field label="База знаний (по умолчанию)" hint="Используется если у вакансии нет своей базы знаний. В карточке вакансии можно задать отдельную базу знаний для каждой позиции.">
          <textarea className="input w-full min-h-[100px] resize-y text-sm" {...register('automation_knowledge_base')}
            placeholder={"Компания занимается...\nГрафик работы: ...\nЗарплата: ...\nТребования: ..."} />
        </Field>
        <Field label="Место собеседований (по умолчанию)" hint="Используется если у вакансии не задан свой адрес.">
          <input className="input w-full" {...register('automation_interview_location')} placeholder="г. Москва, ул. Примерная, 1" />
        </Field>
        <Field label="Anthropic API Key" hint="API ключ для Claude AI (console.anthropic.com). Хранится в config.json на сервере.">
          <input type="password" className="input w-full font-mono text-sm" placeholder="sk-ant-api03-..." {...register('anthropic_api_key')} />
        </Field>
        <div className="border-t border-[color:var(--color-border)] pt-4 mt-2">
          <p className="text-xs font-semibold text-[color:var(--color-muted-foreground)] uppercase tracking-wide mb-3">Параметры AI — разговор с кандидатами</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
            <Field label="Модель" hint="claude-haiku-4-5-20251001 / claude-sonnet-4-6 / claude-opus-4-7">
              <input className="input w-full font-mono text-sm" {...register('ai_candidate_model')}
                placeholder="claude-haiku-4-5-20251001" />
            </Field>
            <Field label="Max tokens" hint="Жёсткий лимит длины ответа. 120 ≈ 2 предложения, 300 ≈ абзац.">
              <input type="number" className="input w-full" {...register('ai_candidate_max_tokens')}
                placeholder="120" min="50" max="2000" />
            </Field>
          </div>
          <Field label="Ответ при готовности к собеседованию (PROPOSE_INTERVIEW)"
            hint="Что кандидат получит когда AI решит что он готов к собеседованию. Пусто = стандартный текст.">
            <input className="input w-full text-sm" {...register('ai_propose_interview_reply')}
              placeholder="Отлично! Ваша заявка принята, наш менеджер свяжется с вами в ближайшее время для подтверждения." />
          </Field>
          <Field label="Ответ при эскалации (ESCALATE)"
            hint="Что кандидат получит когда AI не знает ответа и передаёт диалог менеджеру. Пусто = стандартный текст.">
            <input className="input w-full text-sm" {...register('ai_escalate_reply')}
              placeholder="Ваш вопрос передан нашему менеджеру, с вами свяжутся в ближайшее время." />
          </Field>
          <Field
            label="Системный промпт"
            hint="Плейсхолдеры: {knowledge_base} и {interview_location} — обязательны. Пусто = встроенный промпт по умолчанию."
          >
            <textarea className="input w-full min-h-[160px] resize-y text-sm font-mono"
              {...register('ai_candidate_system_prompt')}
              placeholder={"Ты HR-ассистент компании. Отвечаешь на вопросы кандидата о вакансии.\n\nБаза знаний:\n{knowledge_base}\n\nМесто собеседований: {interview_location}\n\nПравила..."} />
          </Field>
        </div>
        <Field
          label="Шаблон сообщения на hh.ru (с Telegram-ссылкой)"
          hint="Отправляется кандидату автоматикой. Плейсхолдеры: {name} — имя, {link} — ссылка на TG (обязательно!), {code} — код привязки."
        >
          <textarea className="input w-full min-h-[100px] resize-y text-sm font-mono" {...register('automation_hh_message_with_link')}
            placeholder={"{name}, здравствуйте! Для удобного общения перейдите по ссылке и нажмите «Отправить»:\n{link}\n\n⚠️ Не изменяйте текст сообщения."} />
        </Field>
        <Field
          label="Шаблон сообщения на hh.ru (без ссылки)"
          hint="Используется когда Telegram username не настроен. Плейсхолдеры: {name}, {code} (обязательно!), {username}."
        >
          <textarea className="input w-full min-h-[80px] resize-y text-sm font-mono" {...register('automation_hh_message_no_link')}
            placeholder={"{name}, здравствуйте! Напишите нам в Telegram @{username} и укажите код: {code}"} />
        </Field>
      </Section>

      <Section title="Follow-up (реактивация молчащих кандидатов)">
        <Field label="" hint="Бот пишет кандидату сам, если тот замолчал. Только с 10:00 до 20:00 МСК.">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" {...register('follow_up_enabled')} />
            <span className="text-sm">Включить follow-up</span>
          </label>
        </Field>
        <Field label="Задержка перед follow-up (часов)" hint="Сколько часов молчания кандидата до первого и каждого последующего напоминания.">
          <input type="number" className="input w-full" {...register('follow_up_delay_hours')}
            placeholder="1" min="0.5" max="72" step="0.5" />
        </Field>
        <Field label="Текст первого follow-up" hint="Пусто = стандартный текст.">
          <textarea className="input w-full min-h-[70px] resize-y text-sm" {...register('follow_up_message_1')}
            placeholder="Здравствуйте! Остались ли у вас вопросы по вакансии? Готовы записаться на собеседование?" />
        </Field>
        <Field label="Текст второго follow-up" hint="Отправляется если после первого тоже нет ответа. Пусто = стандартный текст.">
          <textarea className="input w-full min-h-[70px] resize-y text-sm" {...register('follow_up_message_2')}
            placeholder="Мы всё ещё ждём вашего ответа. Если вас интересует вакансия — напишите, будем рады помочь." />
        </Field>
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

      {/* Message templates */}
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
                  onChange={e => updateTemplate(i, 'type', e.target.value)}
                >
                  <option value="rejection">Отказ</option>
                  <option value="interview">Собеседование</option>
                </select>
                <input
                  className="input flex-1 text-sm"
                  placeholder="Название шаблона"
                  value={t.name}
                  onChange={e => updateTemplate(i, 'name', e.target.value)}
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
