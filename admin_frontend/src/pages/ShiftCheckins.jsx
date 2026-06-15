import { useEffect, useState } from 'react';
import api from '../api';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';

export default function ShiftCheckins() {
  const [list, setList] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [filters, setFilters] = useState({ from: '', to: '' });
  const [photoUrl, setPhotoUrl] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);

  function emptyForm() {
    const now = new Date();
    return {
      employee_id: '',
      date: now.toISOString().slice(0, 10),
      time: now.toTimeString().slice(0, 5),
    };
  }

  useEffect(() => {
    load();
    loadEmployees();
  }, [filters]);

  useEffect(() => {
    return () => {
      if (photoUrl) URL.revokeObjectURL(photoUrl);
    };
  }, [photoUrl]);

  async function load() {
    const params = {
      date_from: filters.from || undefined,
      date_to: filters.to || undefined,
    };
    try {
      const res = await api.get('shift-checkins/', { params });
      setList(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function loadEmployees() {
    try {
      const res = await api.get('employees/', { params: { archived: false } });
      setEmployees(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function openPhoto(item) {
    try {
      const res = await api.get(`shift-checkins/${item.id}/photo`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      setPhotoUrl(url);
    } catch (err) {
      console.error(err);
    }
  }

  function closePhoto() {
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    setPhotoUrl(null);
  }

  function startCreate() {
    setForm(emptyForm());
    setShowForm(true);
  }

  async function saveForm() {
    if (!form.employee_id || !form.date || !form.time) return;
    const employee = employees.find((e) => String(e.id) === String(form.employee_id));
    setSaving(true);
    try {
      await api.post('shift-checkins/', {
        employee_id: form.employee_id,
        employee_name: employee?.full_name || employee?.name || '',
        date: form.date,
        time: form.time,
      });
      setShowForm(false);
      load();
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  }

  function fmtTime(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return iso;
    }
  }

  const rowColor = (item) => (item.penalty_amount ? 'bg-red-50' : '');

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <h2 className="text-2xl font-semibold tracking-tight text-gray-800">Рабочее время</h2>
      <div className="flex flex-wrap gap-2 items-end">
        <input
          type="date"
          className="border p-2"
          value={filters.from}
          onChange={(e) => setFilters({ ...filters, from: e.target.value })}
        />
        <input
          type="date"
          className="border p-2"
          value={filters.to}
          onChange={(e) => setFilters({ ...filters, to: e.target.value })}
        />
        <button className="btn" onClick={load}>
          Применить
        </button>
        <button className="btn ml-auto" onClick={startCreate}>
          ➕ Добавить вручную
        </button>
      </div>
      <ResponsiveTable
        data={list}
        keyFn={(item) => item.id}
        rowClass={rowColor}
        emptyText="Нет данных"
        columns={[
          { label: 'Дата', key: 'date', primary: true },
          { label: 'Сотрудник', key: 'employee_name' },
          { label: 'Точка', render: (item) => item.salon_name || item.point || '—' },
          { label: 'Открытие', render: (item) => fmtTime(item.sent_at) },
          { label: 'По графику', render: (item) => item.expected_open_time || '—' },
          {
            label: 'Штраф',
            render: (item) =>
              item.penalty_amount
                ? `${item.delay_minutes} мин — ${item.penalty_amount.toFixed(0)} ₽`
                : item.no_schedule
                ? 'Нет графика'
                : '—',
          },
          {
            label: 'Фото',
            isAction: true,
            cellClass: 'text-right',
            render: (item) =>
              item.photo_path ? (
                <button className="text-blue-600" onClick={() => openPhoto(item)}>
                  📷 Открыть
                </button>
              ) : (
                <span className="text-gray-400">{item.manual ? 'Вручную' : '—'}</span>
              ),
          },
        ]}
      />

      {photoUrl && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && closePhoto()}>
          <div className="modal-card max-w-2xl">
            <img src={photoUrl} alt="Чек об открытии" className="w-full h-auto rounded" />
            <div className="flex justify-end pt-2">
              <button className="btn bg-gray-200 text-gray-700 hover:bg-gray-300" onClick={closePhoto}>
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && setShowForm(false)}>
          <div className="modal-card max-w-md">
            <h2 className="text-xl font-semibold">Отметка об открытии вручную</h2>
            <select
              className="modal-control"
              value={form.employee_id}
              onChange={(e) => setForm({ ...form, employee_id: e.target.value })}
            >
              <option value="">Сотрудник</option>
              {employees.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.full_name || e.name}
                </option>
              ))}
            </select>
            <input
              type="date"
              className="modal-control"
              value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })}
            />
            <input
              type="time"
              className="modal-control"
              value={form.time}
              onChange={(e) => setForm({ ...form, time: e.target.value })}
            />
            <div className="flex justify-end gap-2 pt-2">
              <button className="btn bg-gray-200 text-gray-700 hover:bg-gray-300" onClick={() => setShowForm(false)}>
                Отмена
              </button>
              <button className="btn" onClick={saveForm} disabled={saving}>
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
