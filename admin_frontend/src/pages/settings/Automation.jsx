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
        <Field label="" hint="Бот пишет кандидату сам, если тот замолчал — в рамках рабочих часов, заданных выше.">
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

      <div>
        <button type="submit" className="btn btn--primary">Сохранить настройки</button>
      </div>
    </form>
  );
}
