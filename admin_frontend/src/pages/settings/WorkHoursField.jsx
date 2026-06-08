import { Controller } from 'react-hook-form';
import { Field } from './shared.jsx';

const DAYS = [
  { value: 0, label: 'Пн' },
  { value: 1, label: 'Вт' },
  { value: 2, label: 'Ср' },
  { value: 3, label: 'Чт' },
  { value: 4, label: 'Пт' },
  { value: 5, label: 'Сб' },
  { value: 6, label: 'Вс' },
];

const DEFAULT_DAYS = [0, 1, 2, 3, 4];

/**
 * Shared "working hours" picker — governs both the AI candidate interview and
 * the proactive follow-up. Replaces relying on Telegram's own (invisible,
 * unconfigurable from here) Business Hours setting on the connected account.
 */
export default function WorkHoursField({ control, register }) {
  return (
    <div className="space-y-3">
      <Field label="Рабочие дни автоматизации" hint="В эти дни ИИ-ассистент и follow-up отвечают кандидатам. В остальные — кандидат получает сообщение «ответим в рабочее время».">
        <Controller
          name="automation_work_days"
          control={control}
          defaultValue={DEFAULT_DAYS}
          render={({ field }) => {
            const selected = Array.isArray(field.value) && field.value.length ? field.value : DEFAULT_DAYS;
            function toggle(day) {
              const next = selected.includes(day)
                ? selected.filter((d) => d !== day)
                : [...selected, day];
              field.onChange(next.sort((a, b) => a - b));
            }
            return (
              <div className="flex flex-wrap gap-1.5">
                {DAYS.map((d) => (
                  <button
                    key={d.value}
                    type="button"
                    onClick={() => toggle(d.value)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                      selected.includes(d.value)
                        ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]'
                        : 'border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-bg-secondary)]'
                    }`}
                  >
                    {d.label}
                  </button>
                ))}
              </div>
            );
          }}
        />
      </Field>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="Начало рабочего дня" hint="Время по МСК, формат ЧЧ:ММ">
          <input type="time" className="input w-full" {...register('automation_work_hours_from')} />
        </Field>
        <Field label="Конец рабочего дня" hint="Время по МСК, формат ЧЧ:ММ">
          <input type="time" className="input w-full" {...register('automation_work_hours_to')} />
        </Field>
      </div>
      <Field label="Сообщение в нерабочее время" hint="Кандидат получит его автоматически, если напишет вне рабочих часов. Плейсхолдер {hours} подставит расписание. Пусто = стандартный текст.">
        <textarea className="input w-full min-h-[70px] resize-y text-sm" {...register('automation_away_message')}
          placeholder={"Здравствуйте! Мы получили ваше сообщение. Наш ассистент отвечает в рабочее время ({hours}) — обязательно продолжим общение, как только начнётся рабочий день."} />
      </Field>
    </div>
  );
}
