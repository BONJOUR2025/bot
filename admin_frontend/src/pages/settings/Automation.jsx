import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';
import { Section, Field } from './shared.jsx';
import WorkHoursField from './WorkHoursField.jsx';

export default function SettingsAutomation() {
  const { toast } = useToast();
  const [loaded, setLoaded] = useState(false);
  const { register, handleSubmit, reset, control } = useForm({ defaultValues: {} });

  useEffect(() => { load(); }, []);

  async function load() {
    try {
      const res = await api.get('config/');
      reset(res.data);
      setLoaded(true);
    } catch { toast('Ошибка загрузки настроек', 'error'); }
  }

  async function save(values) {
    try {
      await api.patch('config/', values);
      toast('Сохранено', 'success');
    } catch { toast('Ошибка сохранения', 'error'); }
  }

  if (!loaded) return <p className="text-center p-10 text-[color:var(--color-muted-foreground)]">Загрузка…</p>;

  return (
    <form onSubmit={handleSubmit(save)} className="space-y-6 max-w-3xl">
      <Section title="Рабочие часы автоматизации">
        <p className="text-sm text-[color:var(--color-muted-foreground)] mb-1">
          Раньше это решал Telegram «Часы работы» бизнес-аккаунта — настройка была не видна
          и не редактировалась из панели. Теперь ИИ-ассистент и follow-up ориентируются на
          расписание ниже и сами объясняют кандидату, когда ждать ответа.
        </p>
        <WorkHoursField control={control} register={register} />
      </Section>

      <Section title="Автоматизация найма">
        <p className="text-sm text-[color:var(--color-muted-foreground)] mb-3">
          Фильтры кандидатов, follow-up и шаблоны сообщений hh.ru настраиваются в «Стратегии найма»
          (страница «Подбор» → карточка вакансии). Здесь остаются только общие параметры, не зависящие
          от стратегии конкретной вакансии.
        </p>
        <Field label="Место собеседований (по умолчанию)" hint="Используется если у вакансии не задан свой адрес.">
          <input className="input w-full" {...register('automation_interview_location')} placeholder="г. Москва, ул. Примерная, 1" />
        </Field>
        <Field label="AI-провайдер" hint="Anthropic — прямой доступ к Claude. Polza.ai — шлюз с оплатой в рублях, даёт доступ к DeepSeek и другим моделям.">
          <select className="input w-full" {...register('llm_provider')}>
            <option value="anthropic">Anthropic (Claude)</option>
            <option value="polza">Polza.ai (DeepSeek и др.)</option>
          </select>
        </Field>
        <Field label="Anthropic API Key" hint="API ключ для Claude AI (console.anthropic.com). Используется, если провайдер выше — Anthropic. Хранится в config.json на сервере.">
          <input type="password" className="input w-full font-mono text-sm" placeholder="sk-ant-api03-..." {...register('anthropic_api_key')} />
        </Field>
        <Field label="Polza.ai API Key" hint="Ключ из polza.ai/dashboard/api-keys. Используется, если провайдер выше — Polza.ai.">
          <input type="password" className="input w-full font-mono text-sm" placeholder="pz-..." {...register('polza_api_key')} />
        </Field>
        <Field label="Polza.ai — модель" hint="Формат provider/model, например deepseek/deepseek-chat. Проверьте точный id в каталоге моделей на polza.ai/models — пусто = deepseek/deepseek-chat.">
          <input className="input w-full font-mono text-sm" {...register('polza_model')} placeholder="deepseek/deepseek-chat" />
        </Field>
        <Field
          label="Модель для базы знаний (бот)"
          hint="Отдельно от модели выше, потому что база знаний целиком (~50 000 токенов) уходит в каждый вопрос сотрудника — здесь решает не цена за токен, а кэширование промпта. На deepseek кэш не работает: Polza раздаёт её сторонним площадкам без префиксного кэша (замерено — 1.58 ₽ за вопрос). У gpt-4.1-nano кэш есть: те же ответы за ~0.14 ₽. Пусто = openai/gpt-4.1-nano."
        >
          <input className="input w-full font-mono text-sm" {...register('kb_model')} placeholder="openai/gpt-4.1-nano" />
        </Field>
        <div className="border-t border-[color:var(--color-border)] pt-4 mt-2">
          <p className="text-xs font-semibold text-[color:var(--color-muted-foreground)] uppercase tracking-wide mb-3">Параметры AI — разговор с кандидатами</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
            <Field label="Модель" hint="claude-haiku-4-5-20251001 / claude-sonnet-4-6 / claude-opus-4-7 — только если провайдер Anthropic. Для Polza.ai используйте поле «Polza.ai — модель» выше.">
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
      </Section>

      <div>
        <button type="submit" className="btn btn--primary">Сохранить настройки</button>
      </div>
    </form>
  );
}
