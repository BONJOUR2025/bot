import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import api from '../api';

const FIELDS = {
  positions: 'Должности',
  work_places: 'Места работы',
  employee_statuses: 'Статусы сотрудников',
  payout_types: 'Типы выплат',
  payout_methods: 'Способы выплат',
  payout_statuses: 'Статусы выплат',
  payout_control_types: 'Типы заявок на выплаты',
  payout_control_methods: 'Способы заявок на выплаты',
  vacation_types: 'Типы отпусков',
  incentive_types: 'Типы штрафов и премий',
  broadcast_statuses: 'Статусы рассылки',
  asset_items: 'Предметы имущества',
  asset_sizes: 'Размеры имущества',
};

export default function Dictionary() {
  const { register, handleSubmit, reset } = useForm({ defaultValues: {} });
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    load();
  }, []);

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
      alert('Сохранено');
    } catch (err) {
      console.error(err);
      alert('Ошибка сохранения');
    }
  }

  if (!loaded) {
    return <p className="text-center">Загрузка...</p>;
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <h2 className="text-2xl font-semibold">Словарь</h2>
      <form onSubmit={handleSubmit(save)} className="space-y-4">
        {Object.entries(FIELDS).map(([key, label]) => (
          <section key={key} className="border rounded p-3 space-y-2">
            <h3 className="font-semibold">{label}</h3>
            <textarea
              className="border p-2 w-full"
              placeholder={`${label}, через запятую`}
              {...register(key)}
            />
          </section>
        ))}
        <button type="submit" className="btn">
          Сохранить
        </button>
      </form>
    </div>
  );
}




