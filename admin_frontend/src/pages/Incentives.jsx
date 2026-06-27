import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import api from '../api';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';

export default function Incentives() {
  const location = useLocation();
  const query = new URLSearchParams(location.search);

  const emptyForm = {
    id: null,
    employee_id: '',
    name: '',
    type: 'bonus',
    amount: '',
    reason: '',
    date: new Date().toISOString().slice(0, 10),
    added_by: 'admin',
  };

  const [list, setList] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [filters, setFilters] = useState({
    employee: query.get('employee_id') || '',
    type: query.get('type') || '',
    from: query.get('date_from') || '',
    to: query.get('date_to') || '',
  });
  const [form, setForm] = useState(emptyForm);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    loadEmployees();
  }, []);

  useEffect(() => {
    load();
  }, [filters]);

  async function loadEmployees() {
    try {
      const res = await api.get('employees/', { params: { archived: false } });
      setEmployees(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function load() {
    const params = {
      employee_id: filters.employee || undefined,
      type: filters.type || undefined,
      date_from: filters.from || undefined,
      date_to: filters.to || undefined,
    };
    try {
      const res = await api.get('incentives/', { params });
      setList(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function saveForm() {
    if (!form.employee_id || !form.amount || !form.date) return;
    const payload = { ...form, amount: Number(form.amount) };
    try {
      if (form.id) {
        await api.patch(`incentives/${form.id}`, payload);
      } else {
        await api.post('incentives/', payload);
      }
      setShowForm(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      console.error(err);
    }
  }

  async function remove(id) {
    if (!window.confirm('Удалить запись?')) return;
    try {
      await api.delete(`incentives/${id}`);
      load();
    } catch (err) {
      console.error(err);
    }
  }

  function startCreate() {
    setForm(emptyForm);
    setShowForm(true);
  }

  function startEdit(item) {
    setForm({ ...item, amount: item.amount });
    setShowForm(true);
  }

  const rowColor = (type) => (type === 'bonus' ? 'bg-green-50' : 'bg-red-50');
  const typeLabel = (t) => (t === 'bonus' ? '💰 Премия' : '⚠️ Штраф');

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)]">Штрафы и премии</h2>
      <div className="flex flex-wrap gap-2 items-end">
        <select
          className="input"
          value={filters.employee}
          onChange={(e) => setFilters({ ...filters, employee: e.target.value })}
        >
          <option value="">Все сотрудники</option>
          {employees.map((e) => (
            <option key={e.id} value={e.id}>
              {e.full_name || e.name}
            </option>
          ))}
        </select>
        <select
          className="input"
          value={filters.type}
          onChange={(e) => setFilters({ ...filters, type: e.target.value })}
        >
          <option value="">Все типы</option>
          <option value="bonus">Премия</option>
          <option value="penalty">Штраф</option>
        </select>
        <div className="flex flex-col sm:flex-row sm:flex-wrap gap-2 w-full sm:w-auto">
          <input
            type="date"
            className="input w-full sm:w-auto"
            value={filters.from}
            onChange={(e) => setFilters({ ...filters, from: e.target.value })}
          />
          <input
            type="date"
            className="input w-full sm:w-auto"
            value={filters.to}
            onChange={(e) => setFilters({ ...filters, to: e.target.value })}
          />
        </div>
        <button className="btn" onClick={load}>
          Применить
        </button>
        <button className="btn ml-auto" onClick={startCreate}>
          ➕ Добавить
        </button>
      </div>
      <ResponsiveTable
        data={list}
        keyFn={(item) => item.id}
        rowClass={(item) => rowColor(item.type)}
        emptyText="Нет данных"
        columns={[
          { label: 'Сотрудник', key: 'name', primary: true },
          { label: 'Дата', key: 'date' },
          { label: 'Тип', render: (item) => <span className="font-medium">{typeLabel(item.type)}</span> },
          {
            label: 'Сумма',
            headerClass: 'text-right',
            cellClass: 'text-right whitespace-nowrap',
            render: (item) => (
              <span className={`font-medium tabular-nums ${item.type === 'bonus' ? 'text-[color:var(--color-success)]' : 'text-[color:var(--color-danger)]'}`}>
                {item.type === 'bonus' ? '+' : '−'}{Number(item.amount || 0).toLocaleString('ru-RU')} ₽
              </span>
            ),
          },
          { label: 'Причина', key: 'reason' },
          { label: 'Добавил', key: 'added_by' },
          {
            label: '',
            isAction: true,
            cellClass: 'text-right',
            render: (item) => (
              <>
                <button className="text-blue-600 mr-1" onClick={() => startEdit(item)}>✏️</button>
                {!item.locked && (
                  <button className="text-red-600" onClick={() => remove(item.id)}>🗑️</button>
                )}
              </>
            ),
          },
        ]}
      />

      {showForm && (
        <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setShowForm(false)}>
          <div className="modal-card max-w-md">
            <h2 className="text-xl font-semibold">{form.id ? 'Редактирование' : 'Новая запись'}</h2>
            <select
              className="modal-control"
              value={form.employee_id}
              onChange={(e) => {
                const id = e.target.value;
                setForm((f) => ({
                  ...f,
                  employee_id: id,
                  name: employees.find((u) => String(u.id) === String(id))?.full_name || '',
                }));
              }}
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
            <select
              className="modal-control"
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
            >
              <option value="bonus">Премия</option>
              <option value="penalty">Штраф</option>
            </select>
            <input
              className="modal-control"
              placeholder="Сумма"
              type="number"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
            <textarea
              className="modal-control"
              placeholder="Причина"
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
            />
            <div className="flex justify-end gap-2 pt-2">
              <button className="btn bg-[color:var(--color-control-bg)] text-[color:var(--color-text)] hover:bg-[color:var(--color-control-bg-hover)]" onClick={() => setShowForm(false)}>
                Отмена
              </button>
              <button className="btn" onClick={saveForm}>
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}





