import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import api from '../api';

export default function Dictionary() {
  const { register, handleSubmit, reset } = useForm({ defaultValues: {} });
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const res = await api.get('dictionary/');
      reset({ positions: (res.data.positions || []).join(', ') });
      setLoaded(true);
    } catch (err) {
      console.error(err);
    }
  }

  async function save(values) {
    const payload = {
      positions: values.positions
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    };
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
        <section className="border rounded p-3 space-y-2">
          <h3 className="font-semibold">Должности</h3>
          <textarea
            className="border p-2 w-full"
            placeholder="Должности, через запятую"
            {...register('positions')}
          />
        </section>
        <button type="submit" className="bg-blue-600 text-white px-3 py-2 rounded">
          Сохранить
        </button>
      </form>
    </div>
  );
}
