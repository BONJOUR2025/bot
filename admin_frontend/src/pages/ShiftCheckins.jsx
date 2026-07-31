import { useEffect, useMemo, useState } from 'react';
import api from '../api';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { groupEmployeesByPosition } from '../utils/employeeGrouping.js';

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

function dateRange(from, to) {
  const dates = [];
  if (!from || !to) return dates;
  const start = new Date(`${from}T00:00:00Z`);
  const end = new Date(`${to}T00:00:00Z`);
  if (start > end) return dates;
  for (let d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    dates.push(d.toISOString().slice(0, 10));
  }
  return dates.reverse();
}

export default function ShiftCheckins() {
  const [list, setList] = useState([]);
  const [employees, setEmployees] = useState([]);
  const employeesByPosition = useMemo(() => groupEmployeesByPosition(employees), [employees]);
  const [salons, setSalons] = useState([]);
  const [filters, setFilters] = useState({ from: todayStr(), to: todayStr() });
  const [photoUrl, setPhotoUrl] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
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
  }, [filters]);

  useEffect(() => {
    loadEmployees();
    loadSalons();
  }, []);

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

  async function loadSalons() {
    try {
      const res = await api.get('salons/', { params: { status: 'active' } });
      setSalons(res.data.filter((s) => s.status === 'active'));
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
    setEditingId(null);
    setForm(emptyForm());
    setShowForm(true);
  }

  function startEdit(item) {
    setEditingId(item.id);
    setForm({
      employee_id: item.employee_id,
      date: item.date,
      time: (item.sent_at || '').slice(11, 16),
    });
    setShowForm(true);
  }

  async function saveForm() {
    if (!form.employee_id || !form.date || !form.time) return;
    const employee = employees.find((e) => String(e.id) === String(form.employee_id));
    setSaving(true);
    try {
      const payload = {
        employee_id: form.employee_id,
        employee_name: employee?.full_name || employee?.name || '',
        date: form.date,
        time: form.time,
      };
      if (editingId) {
        await api.patch(`shift-checkins/${editingId}`, payload);
      } else {
        await api.post('shift-checkins/', payload);
      }
      setShowForm(false);
      setEditingId(null);
      load();
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm('Удалить запись вместе с фото?')) return;
    try {
      await api.delete(`shift-checkins/${id}`);
      load();
    } catch (err) {
      console.error(err);
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

  function fmtDate(dateStr) {
    try {
      return new Date(`${dateStr}T00:00:00`).toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        weekday: 'short',
      });
    } catch {
      return dateStr;
    }
  }

  function penaltyLabel(item) {
    if (item.penalty_amount) {
      return `${item.delay_minutes} мин — ${item.penalty_amount.toFixed(0)} ₽`;
    }
    if (item.no_schedule) return 'Нет графика';
    return '—';
  }

  function actionButtons(item) {
    return (
      <div className="flex justify-end gap-2">
        <button className="text-blue-600" onClick={() => startEdit(item)} title="Редактировать">
          ✏️
        </button>
        <button className="text-red-600" onClick={() => handleDelete(item.id)} title="Удалить запись">
          🗑
        </button>
      </div>
    );
  }

  function photoCell(item) {
    return item.photo_path ? (
      <button className="text-blue-600" onClick={() => openPhoto(item)}>
        📷 Открыть
      </button>
    ) : (
      <span className="text-[color:var(--color-text-faint)]">{item.manual ? 'Вручную' : '—'}</span>
    );
  }

  const dates = dateRange(filters.from, filters.to);
  const activeSalonIds = new Set(salons.map((s) => String(s.id)));
  const otherItems = list.filter((item) => !activeSalonIds.has(String(item.salon_id)));

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)]">Рабочее время</h2>
      <div className="flex flex-wrap gap-2 items-end">
        <input
          type="date"
          className="input"
          value={filters.from}
          onChange={(e) => setFilters({ ...filters, from: e.target.value })}
        />
        <input
          type="date"
          className="input"
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

      <div className="space-y-4">
        {dates.map((date) => {
          const rows = salons.flatMap((salon) => {
            const checkins = list.filter(
              (item) => item.date === date && String(item.salon_id) === String(salon.id)
            );
            if (checkins.length === 0) {
              return [{ id: `salon-${salon.id}`, salon, noCheckin: true }];
            }
            return checkins.map((item) => ({ id: item.id, salon, item }));
          });
          return (
            <div key={date} className="border rounded shadow bg-[color:var(--color-surface)] overflow-hidden">
              <div className="px-3 py-2 bg-[color:var(--color-bg-subtle)] font-semibold text-sm">{fmtDate(date)}</div>
              <ResponsiveTable
                data={rows}
                keyFn={(row) => row.id}
                rowClass={(row) => (row.item?.penalty_amount ? 'bg-red-50' : '')}
                emptyText="Нет активных салонов"
                columns={[
                  { label: 'Точка', render: (row) => row.salon.name, primary: true },
                  {
                    label: 'Сотрудник',
                    render: (row) =>
                      row.noCheckin ? (
                        <span className="text-[color:var(--color-text-faint)]">Нет отметки об открытии</span>
                      ) : (
                        row.item.employee_name
                      ),
                  },
                  { label: 'Открытие', render: (row) => (row.noCheckin ? '—' : fmtTime(row.item.sent_at)) },
                  {
                    label: 'По графику',
                    render: (row) => (row.noCheckin ? '—' : row.item.expected_open_time || '—'),
                  },
                  { label: 'Штраф', render: (row) => (row.noCheckin ? '—' : penaltyLabel(row.item)) },
                  { label: 'Фото', render: (row) => (row.noCheckin ? '—' : photoCell(row.item)) },
                  {
                    label: '',
                    isAction: true,
                    cellClass: 'text-right',
                    render: (row) => (row.noCheckin ? null : actionButtons(row.item)),
                  },
                ]}
              />
            </div>
          );
        })}
        {dates.length === 0 && (
          <div className="py-6 text-center text-[color:var(--color-text-muted)] text-sm">Выберите период</div>
        )}
      </div>

      {otherItems.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-lg font-semibold tracking-tight text-[color:var(--color-text)]">Прочие отметки</h3>
          <ResponsiveTable
            data={otherItems}
            keyFn={(item) => item.id}
            rowClass={(item) => (item.penalty_amount ? 'bg-red-50' : '')}
            emptyText="Нет данных"
            columns={[
              { label: 'Дата', key: 'date', primary: true },
              { label: 'Сотрудник', key: 'employee_name' },
              { label: 'Точка', render: (item) => item.salon_name || item.point || '—' },
              { label: 'Открытие', render: (item) => fmtTime(item.sent_at) },
              { label: 'По графику', render: (item) => item.expected_open_time || '—' },
              { label: 'Штраф', render: penaltyLabel },
              { label: 'Фото', render: photoCell },
              { label: '', isAction: true, cellClass: 'text-right', render: actionButtons },
            ]}
          />
        </div>
      )}

      {photoUrl && (
        <div className="modal-backdrop" onClick={(e) => e.target === e.currentTarget && closePhoto()}>
          <div className="modal-card max-w-2xl">
            <img src={photoUrl} alt="Чек об открытии" className="w-full h-auto rounded" />
            <div className="flex justify-end pt-2">
              <button className="btn btn--secondary" onClick={closePhoto}>
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <div
          className="modal-backdrop"
          onClick={(e) => e.target === e.currentTarget && (setShowForm(false), setEditingId(null))}
        >
          <div className="modal-card max-w-md">
            <h2 className="text-xl font-semibold">
              {editingId ? 'Редактирование отметки об открытии' : 'Отметка об открытии вручную'}
            </h2>
            <select
              className="modal-control"
              value={form.employee_id}
              onChange={(e) => setForm({ ...form, employee_id: e.target.value })}
            >
              <option value="">Сотрудник</option>
              {employeesByPosition.map(([position, list]) => (
                <optgroup key={position} label={position}>
                  {list.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.full_name || e.name}
                    </option>
                  ))}
                </optgroup>
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
              <button
                className="btn btn--secondary"
                onClick={() => {
                  setShowForm(false);
                  setEditingId(null);
                }}
              >
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
