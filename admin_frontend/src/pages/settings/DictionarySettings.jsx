import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import api from '../../api';
import { useToast } from '../../providers/ToastProvider.jsx';
import { Section, Field } from './shared.jsx';

const FIELDS = {
  positions: 'Должности',
  work_places: 'Места работы',
  employee_statuses: 'Статусы сотрудников',
  payout_types: 'Типы выплат',
  payout_methods: 'Способы выплат',
  vacation_types: 'Типы отпусков',
  incentive_types: 'Типы штрафов и премий',
  asset_items: 'Предметы имущества',
  asset_sizes: 'Размеры имущества',
};

export default function SettingsDictionary() {
  const { toast } = useToast();
  const { register, handleSubmit, reset } = useForm({ defaultValues: {} });
  const [loaded, setLoaded] = useState(false);

  useEffect(() => { load(); }, []);

  async function load() {
    try {
      const res = await api.get('dictionary/');
      const defaults = {};
      Object.keys(FIELDS).forEach((key) => {
        defaults[key] = (res.data[key] || []).join(', ');
      });
      reset(defaults);
      setLoaded(true);
    } catch (err) {
      console.error(err);
      toast('Ошибка загрузки словаря', 'error');
    }
  }

  async function save(values) {
    const payload = {};
    Object.keys(FIELDS).forEach((key) => {
      payload[key] = values[key]
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
    });
    try {
      await api.patch('dictionary/', payload);
      toast('Сохранено', 'success');
    } catch (err) {
      console.error(err);
      toast('Ошибка сохранения', 'error');
    }
  }

  if (!loaded) return <p className="text-center p-10 text-[color:var(--color-muted-foreground)]">Загрузка…</p>;

  return (
    <form onSubmit={handleSubmit(save)} className="space-y-6 max-w-3xl">
      <Section title="Словарь значений">
        <p className="text-sm text-[color:var(--color-muted-foreground)]">
          Списки значений для выпадающих меню в формах сотрудников, выплат, отпусков и т.д.
          Перечисляйте варианты через запятую.
        </p>
        <div className="space-y-4">
          {Object.entries(FIELDS).map(([key, label]) => (
            <Field key={key} label={label} hint={`${label}, через запятую`}>
              <textarea className="input w-full min-h-[60px] resize-y text-sm" {...register(key)} />
            </Field>
          ))}
        </div>
      </Section>

      <div>
        <button type="submit" className="btn btn--primary">Сохранить настройки</button>
      </div>
    </form>
  );
}
