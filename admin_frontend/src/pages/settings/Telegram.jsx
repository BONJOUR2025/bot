import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { RefreshCw } from 'lucide-react';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';
import { Section, Field } from './shared.jsx';

export default function SettingsTelegram() {
  const { toast } = useToast();
  const [loaded, setLoaded] = useState(false);
  const { register, handleSubmit, reset } = useForm({ defaultValues: {} });
  const [testingNotify, setTestingNotify] = useState(false);

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
          <Field label="payment_calendar_cashier_chat_id" hint="Telegram ID кассира — куда отправляются просьбы оплатить счёт из Платёжного календаря">
            <input className="input w-full font-mono" placeholder="123456789" {...register('payment_calendar_cashier_chat_id')} />
          </Field>
        </div>
      </Section>

      <Section title="Telegram Secretary Mode">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Ваш username" hint="Ваш личный username в Telegram (без @). Используется для формирования ссылок-маяков для кандидатов.">
            <div className="flex">
              <span className="inline-flex items-center px-3 rounded-l-[var(--radius-md)] border border-r-0 border-[color:var(--color-control-border)] bg-[color:var(--color-bg-subtle)] text-[color:var(--color-muted-foreground)] select-none">@</span>
              <input className="input w-full rounded-l-none" placeholder="username" {...register('tg_personal_username')} />
            </div>
          </Field>
          <Field label="Business Connection ID" hint="ID подключения Secretary Mode. Можно найти в логах бота после подключения в Telegram → Настройки → Бизнес-аккаунт → Чат-боты. Заполняется автоматически при первом входящем сообщении.">
            <input className="input w-full font-mono text-sm" placeholder="вставьте connection_id из логов" {...register('tg_business_connection_id')} />
          </Field>
        </div>
      </Section>

      <div>
        <button type="submit" className="btn btn--primary">Сохранить настройки</button>
      </div>
    </form>
  );
}
