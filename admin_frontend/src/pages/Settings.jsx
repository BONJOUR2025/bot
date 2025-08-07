import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import api from '../api';

export default function Settings() {
  const [loaded, setLoaded] = useState(false);
  const { register, handleSubmit, reset } = useForm({ defaultValues: {} });

  useEffect(() => {
    load();
  }, []);

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
    } catch (err) {
      console.error(err);
    }
  }

  async function save(values) {
    const payload = {
      ...values,
      payout_types: values.payout_types.split(',').map((s) => s.trim()).filter(Boolean),
      payout_methods: values.payout_methods.split(',').map((s) => s.trim()).filter(Boolean),
      send_reminders_to: values.send_reminders_to
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    };
    try {
      await api.patch('config/', payload);
      alert('Сохранено');
    } catch (err) {
      console.error(err);
      alert('Ошибка сохранения');
    }
  }

  function downloadConfig() {
    window.open('/api/config/download/', '_blank');
  }

  async function uploadConfig(e) {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    await api.post('config/upload/', formData);
    load();
  }

  if (!loaded) {
    return <p className="text-center">Загрузка...</p>;
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <h2 className="text-2xl font-semibold tracking-tight text-gray-800">Настройки</h2>
      <form onSubmit={handleSubmit(save)} className="space-y-4">
        <section className="border rounded p-3 space-y-2">
          <h3 className="font-semibold">Общие</h3>
          <input className="border p-2 w-full" placeholder="Название компании" {...register('company_name')} />
          <input className="border p-2 w-full" placeholder="Валюта" {...register('default_currency')} />
          <input className="border p-2 w-full" placeholder="Часовой пояс" {...register('timezone')} />
        </section>
        <section className="border rounded p-3 space-y-2">
          <h3 className="font-semibold">Выплаты</h3>
          <input className="border p-2 w-full" placeholder="Лимит аванса в месяц" type="number" {...register('max_advance_amount_per_month')} />
          <textarea className="border p-2 w-full" placeholder="Типы выплат, через запятую" {...register('payout_types')} />
          <textarea className="border p-2 w-full" placeholder="Способы выплат, через запятую" {...register('payout_methods')} />
        </section>
        <section className="border rounded p-3 space-y-2">
          <h3 className="font-semibold">Telegram-бот</h3>
          <input className="border p-2 w-full" placeholder="admin_id" {...register('admin_id')} />
          <input className="border p-2 w-full" placeholder="admin_chat_id" {...register('admin_chat_id')} />
          <input className="border p-2 w-full" placeholder="card_dispatch_chat_id" {...register('card_dispatch_chat_id')} />
          <textarea className="border p-2 w-full" placeholder="Welcome" {...register('welcome_message')} />
        </section>
        <section className="border rounded p-3 space-y-2">
          <h3 className="font-semibold">Уведомления</h3>
          <input type="checkbox" {...register('birthday_reminder_enabled')} /> Напоминать о днях рождения
          <input className="border p-2 w-full" placeholder="Время" {...register('birthday_reminder_time')} />
          <textarea className="border p-2 w-full" placeholder="ID получателей" {...register('send_reminders_to')} />
        </section>
        <section className="border rounded p-3 space-y-2">
          <h3 className="font-semibold">PDF отчёты</h3>
          <input className="border p-2 w-full" placeholder="Шрифт" {...register('pdf_font')} />
          <input className="border p-2 w-full" placeholder="Формат даты" {...register('pdf_date_format')} />
          <label className="flex items-center gap-1">
            <input type="checkbox" {...register('show_excel_comments')} /> Показывать комментарии
          </label>
        </section>
        <section className="border rounded p-3 space-y-2">
          <h3 className="font-semibold">Пути файлов</h3>
          <input className="border p-2 w-full" placeholder="Excel" {...register('excel_file_path')} />
          <input className="border p-2 w-full" placeholder="Users" {...register('users_file_path')} />
          <input className="border p-2 w-full" placeholder="Font path" {...register('font_path')} />
          <input className="border p-2 w-full" placeholder="Advance" {...register('advance_requests_file_path')} />
          <input className="border p-2 w-full" placeholder="Adjustments" {...register('adjustments_file_path')} />
          <input className="border p-2 w-full" placeholder="Vacations" {...register('vacations_file_path')} />
        </section>
        <div className="flex gap-3">
          <button type="submit" className="btn">Сохранить</button>
          <button type="button" className="btn bg-gray-300 text-gray-700 hover:bg-gray-400" onClick={downloadConfig}>Скачать</button>
          <input type="file" onChange={uploadConfig} />
        </div>
      </form>
    </div>
  );
}
