import { useEffect, useState } from 'react';
import { Pencil, Trash2, Plus } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';

export default function Vacations() {
  const { toast } = useToast();
  const { isMobile } = useViewport();

  const emptyForm = {
    id: null,
    employee_id: '',
    name: '',
    start_date: '',
    end_date: '',
    type: 'Отпуск',
    comment: '',
  };

  const [vacations, setVacations] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [filters, setFilters] = useState({
    employee: '',
    type: '',
    from: '',
    to: '',
    query: '',
  });
  const [form, setForm] = useState(emptyForm);
  const [showForm, setShowForm] = useState(false);
  const [todayCount, setTodayCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [monthView, setMonthView] = useState(() => {
    const d = new Date();
    d.setDate(1);
    return d;
  });

  function formatDateRange(start, end) {
    const opts = { day: '2-digit', month: '2-digit', year: 'numeric' };
    const s = new Date(start).toLocaleDateString('ru-RU', opts);
    const e = new Date(end).toLocaleDateString('ru-RU', opts);
    return `${s} – ${e}`;
  }

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
      toast('Ошибка загрузки сотрудников', 'error');
    }
  }

  async function load() {
    setLoading(true);
    try {
      const params = {
        employee_id: filters.employee || undefined,
        type: filters.type || undefined,
        date_from: filters.from || undefined,
        date_to: filters.to || undefined,
      };
      const res = await api.get('vacations/', { params });
      let list = res.data;
      if (filters.query) {
        const q = filters.query.toLowerCase();
        list = list.filter((v) => v.name.toLowerCase().includes(q));
      }
      list.sort((a, b) => new Date(a.start_date) - new Date(b.start_date));
      setVacations(list);
      const activeRes = await api.get('vacations/active');
      setTodayCount(activeRes.data.length);
    } catch (err) {
      console.error(err);
      toast('Ошибка загрузки данных', 'error');
    } finally {
      setLoading(false);
    }
  }

  function duration(start, end) {
    const s = new Date(start);
    const e = new Date(end);
    return Math.round((e - s) / 86400000) + 1;
  }

  function startCreate() {
    setForm(emptyForm);
    setShowForm(true);
  }

  function startEdit(v) {
    setForm({ ...v });
    setShowForm(true);
  }

  async function saveForm() {
    if (!form.employee_id || !form.start_date || !form.end_date) {
      toast('Заполните обязательные поля', 'warning');
      return;
    }
    try {
      if (form.id) {
        await api.put(`vacations/${form.id}`, form);
      } else {
        await api.post('vacations/', form);
      }
      setShowForm(false);
      setForm(emptyForm);
      toast('Запись сохранена', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка сохранения', 'error');
    }
  }

  async function remove(id) {
    if (!window.confirm('Удалить запись?')) return;
    try {
      await api.delete(`vacations/${id}`);
      toast('Запись удалена', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка удаления', 'error');
    }
  }

  function handleSelect(id) {
    const emp = employees.find((e) => String(e.id) === String(id));
    if (emp) {
      setForm((f) => ({ ...f, employee_id: emp.id, name: emp.full_name || emp.name }));
    }
  }

  const year = monthView.getFullYear();
  const month = monthView.getMonth();
  const daysCount = new Date(year, month + 1, 0).getDate();
  const days = Array.from({ length: daysCount }, (_, i) => i + 1);
  const empIds = [...new Set(vacations.map((v) => v.employee_id))];
  const todayStr = new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <h2 className="text-2xl font-semibold">Отпуска и больничные</h2>
      <div className="text-sm text-[color:var(--color-text-muted)]">Сегодня в отпуске — {todayCount} сотрудника</div>
      <div className="flex flex-wrap gap-2 items-end">
        <select
          className="input"
          value={filters.type}
          onChange={(e) => setFilters({ ...filters, type: e.target.value })}
        >
          <option value="">Все типы</option>
          <option value="Отпуск">Отпуск</option>
          <option value="Больничный">Больничный</option>
        </select>
        <select
          className="input"
          value={filters.employee}
          onChange={(e) => setFilters({ ...filters, employee: e.target.value })}
        >
          <option value="">Сотрудник</option>
          {employees.map((e) => (
            <option key={e.id} value={e.id}>
              {e.full_name || e.name}
            </option>
          ))}
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
        <input
          className="input flex-grow"
          placeholder="Поиск по ФИО"
          value={filters.query}
          onChange={(e) => setFilters({ ...filters, query: e.target.value })}
        />
        <button className="btn btn-primary ml-auto" onClick={startCreate}>
          <Plus size={16} /> Добавить запись
        </button>
      </div>

      {loading ? (
        <div className="border rounded shadow bg-[color:var(--color-surface)] p-4">
          <SkeletonTable rows={6} cols={6} />
        </div>
      ) : (
        <ResponsiveTable
          data={vacations}
          keyFn={(v) => v.id}
          emptyText="Нет данных"
          columns={[
            { label: 'Сотрудник', key: 'name', primary: true },
            { label: 'Тип', key: 'type' },
            { label: 'Даты', render: (v) => formatDateRange(v.start_date, v.end_date) },
            { label: 'Длительность', render: (v) => `${duration(v.start_date, v.end_date)} дней` },
            { label: 'Комментарий', key: 'comment' },
            {
              label: '',
              isAction: true,
              cellClass: 'text-right',
              render: (v) => (
                <>
                  <button className="text-blue-600 hover:text-blue-800" onClick={() => startEdit(v)} title="Редактировать">
                    <Pencil size={16} />
                  </button>
                  <button className="text-[color:var(--color-text-muted)] hover:text-[color:var(--color-text)] ml-2" onClick={() => remove(v.id)} title="Удалить">
                    <Trash2 size={16} />
                  </button>
                </>
              ),
            },
          ]}
        />
      )}

      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <button
            className="px-2"
            onClick={() =>
              setMonthView(
                (m) => new Date(m.getFullYear(), m.getMonth() - 1, 1)
              )
            }
          >
            ←
          </button>
          <span className="font-semibold">
            {monthView.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })}
          </span>
          <button
            className="px-2"
            onClick={() =>
              setMonthView(
                (m) => new Date(m.getFullYear(), m.getMonth() + 1, 1)
              )
            }
          >
            →
          </button>
        </div>
        {isMobile ? (
          <div className="space-y-3">
            {empIds.length === 0 && (
              <div className="py-6 text-center text-[color:var(--color-text-muted)] text-sm">Нет данных</div>
            )}
            {empIds.map((eid) => {
              const emp = employees.find((e) => String(e.id) === String(eid));
              const name = emp ? emp.full_name || emp.name : '';
              const empVacations = vacations
                .filter((v) => String(v.employee_id) === String(eid))
                .filter((v) => {
                  const monthStart = new Date(year, month, 1).toISOString().slice(0, 10);
                  const monthEnd = new Date(year, month, daysCount).toISOString().slice(0, 10);
                  return v.start_date <= monthEnd && v.end_date >= monthStart;
                });
              return (
                <div key={eid} className="border rounded-xl bg-[color:var(--color-surface)] shadow-sm overflow-hidden">
                  <div className="px-4 py-3 border-b bg-[color:var(--color-bg-subtle)] font-medium text-sm">
                    {name}
                  </div>
                  <div className="px-4 py-2 space-y-2">
                    {empVacations.map((v) => {
                      let dotCls = 'bg-green-200';
                      if (v.end_date < todayStr) dotCls = 'bg-[color:var(--color-border)]';
                      else if (v.start_date <= todayStr && v.end_date >= todayStr)
                        dotCls = 'bg-yellow-200';
                      return (
                        <div key={v.id} className="flex items-center gap-2 text-sm">
                          <span className={`inline-block w-2.5 h-2.5 rounded-full shrink-0 ${dotCls}`} />
                          <span className="flex-1">{formatDateRange(v.start_date, v.end_date)}</span>
                          <span className="text-[color:var(--color-text-muted)] text-xs">{v.type}</span>
                        </div>
                      );
                    })}
                    {empVacations.length === 0 && (
                      <div className="text-sm text-[color:var(--color-text-faint)]">Нет записей в этом месяце</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="overflow-x-auto border rounded shadow bg-[color:var(--color-surface)]">
            <table className="min-w-[900px] text-xs">
              <thead className="bg-[color:var(--color-bg-subtle)]">
                <tr>
                  <th className="p-1 text-left sticky left-0 bg-[color:var(--color-bg-subtle)] z-10">Сотрудник</th>
                  {days.map((d) => (
                    <th key={d} className="p-1 w-6 text-center">
                      {d}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {empIds.map((eid) => {
                  const emp = employees.find((e) => String(e.id) === String(eid));
                  const name = emp ? emp.full_name || emp.name : '';
                  return (
                    <tr key={eid} className="hover:bg-[color:var(--color-control-bg-hover)]">
                      <th className="p-2 text-left sticky left-0 bg-[color:var(--color-surface)] z-10">
                        {name}
                      </th>
                      {days.map((d) => {
                        const dateStr = new Date(year, month, d)
                          .toISOString()
                          .slice(0, 10);
                        const vac = vacations.find(
                          (v) =>
                            String(v.employee_id) === String(eid) &&
                            v.start_date <= dateStr &&
                            v.end_date >= dateStr
                        );
                        let cls = '';
                        let title = '';
                        if (vac) {
                          title = `${formatDateRange(vac.start_date, vac.end_date)}${
                            vac.comment ? ' ' + vac.comment : ''
                          }`;
                          if (vac.end_date < todayStr) cls = 'bg-[color:var(--color-border)]';
                          else if (
                            vac.start_date <= todayStr &&
                            vac.end_date >= todayStr
                          )
                            cls = 'bg-yellow-200';
                          else cls = 'bg-green-200';
                        } else {
                          const dow = new Date(year, month, d).getDay();
                          if (dow === 0 || dow === 6) cls = 'bg-[color:var(--color-bg-subtle)]';
                        }
                        return (
                          <td key={d} className={`border p-1 ${cls}`} title={title} />
                        );
                      })}
                    </tr>
                  );
                })}
                {empIds.length === 0 && (
                  <tr>
                    <td colSpan={days.length + 1} className="p-4 text-center text-[color:var(--color-text-muted)]">
                      Нет данных
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showForm && (
        <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setShowForm(false)}>
          <div className="modal-card max-w-md">
            <h2 className="text-xl font-semibold">
              {form.id ? 'Редактирование' : 'Новая запись'}
            </h2>
            <select
              className="modal-control"
              value={form.employee_id}
              onChange={(e) => handleSelect(e.target.value)}
            >
              <option value="">Сотрудник</option>
              {employees.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.full_name || e.name}
                </option>
              ))}
            </select>
            <select
              className="modal-control"
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
            >
              <option value="Отпуск">Отпуск</option>
              <option value="Больничный">Больничный</option>
            </select>
            <input
              type="date"
              className="modal-control"
              value={form.start_date}
              onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            />
            <input
              type="date"
              className="modal-control"
              value={form.end_date}
              onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            />
            <textarea
              className="modal-control"
              placeholder="Комментарий"
              value={form.comment}
              onChange={(e) => setForm({ ...form, comment: e.target.value })}
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
