import { useState, useEffect, useRef, useMemo } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import {
  UserPlus,
  Trash2,
  Pencil,
  FileDown,
  Archive,
  Users,
  UserCheck,
  ShieldCheck,
  CreditCard,
  BarChart3,
  Layers,
  TrendingUp,
  X,
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  ResponsiveContainer, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import api from '../api';
import UpcomingBirthdays from '../components/UpcomingBirthdays.jsx';
import { SkeletonTable, SkeletonStats } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { useToast } from '../providers/ToastProvider.jsx';
import { Tabs } from '../components/ui/SalaryUI.jsx';
import KpiCard from '../components/ui/Kpi.jsx';
import { CHART_PALETTE as CHART_COLORS } from '../utils/chartPalette.js';

function ShareDonut({ data, total, title, icon: Icon, colorOf, activeName, onSelect }) {
  const [hover, setHover] = useState(null);
  if (!data.length) return null;
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <Icon size={15} className="text-[color:var(--color-primary)]" />
        {title}
        {activeName && <span className="text-xs font-normal text-[color:var(--color-muted-foreground)]">· фильтр: {activeName}</span>}
      </div>
      <div className="flex flex-col sm:flex-row gap-4 items-center">
        <div style={{ width: 160, height: 160, flexShrink: 0 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="value"
                nameKey="name"
                innerRadius="50%"
                outerRadius="80%"
                paddingAngle={2}
                onMouseEnter={(_, i) => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onClick={(entry) => onSelect?.(entry.name)}
                cursor={onSelect ? 'pointer' : 'default'}
              >
                {data.map((entry, i) => (
                  <Cell
                    key={entry.name}
                    fill={colorOf ? colorOf(entry.name, i) : CHART_COLORS[i % CHART_COLORS.length]}
                    opacity={activeName && activeName !== entry.name ? 0.35 : (hover === null || hover === i ? 1 : 0.4)}
                    stroke="none"
                  />
                ))}
              </Pie>
              <Tooltip formatter={(v) => [v, 'Кол-во']} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex-1 w-full space-y-2 min-w-0">
          {data.map((d, i) => {
            const pct = total > 0 ? (d.value / total) * 100 : 0;
            const color = colorOf ? colorOf(d.name, i) : CHART_COLORS[i % CHART_COLORS.length];
            const isActive = activeName === d.name;
            return (
              <button
                key={d.name}
                type="button"
                onClick={() => onSelect?.(d.name)}
                className={`flex items-center gap-2 w-full text-left rounded-md -mx-1 px-1 py-0.5 transition-colors ${onSelect ? 'hover:bg-[color:var(--color-bg-secondary)] cursor-pointer' : ''} ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}
              >
                <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-xs truncate">{d.name}</span>
                    <span className="text-xs font-semibold shrink-0">{d.value} ({pct.toFixed(0)}%)</span>
                  </div>
                  <div className="h-1 rounded-full bg-[color:var(--color-bg-secondary)] mt-0.5 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ExternalUserSelect({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(value || '');
  const [options, setOptions] = useState([]);
  const containerRef = useRef(null);

  useEffect(() => { setQuery(value || ''); }, [value]);

  useEffect(() => {
    function onOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', onOutside);
    return () => document.removeEventListener('mousedown', onOutside);
  }, []);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      api.get('employees/external-users', { params: { search: query } })
        .then((res) => setOptions(res.data || []))
        .catch(() => setOptions([]));
    }, 300);
    return () => clearTimeout(t);
  }, [query, open]);

  function pick(option) {
    const code = String(option.user_id);
    onChange(code);
    setQuery(code);
    setOpen(false);
  }

  const matched = options.find((o) => String(o.user_id) === String(value));

  return (
    <div ref={containerRef} className="relative space-y-1">
      <input
        className="modal-control font-mono"
        placeholder="Поиск по базе ЗП или ID из Агбис..."
        value={query}
        onChange={(e) => { setQuery(e.target.value); onChange(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
      />
      {matched && (
        <div className="text-xs text-[color:var(--color-text-muted)]">{matched.description}</div>
      )}
      {open && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-[color:var(--color-surface)] border rounded-lg shadow-lg max-h-52 overflow-y-auto">
          {options.map((o) => (
            <button key={o.user_id} type="button" onClick={() => pick(o)}
              className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50">
              {o.description} <span className="text-xs text-[color:var(--color-text-faint)]">№{o.user_id}</span>
            </button>
          ))}
          {options.length === 0 && (
            <div className="px-3 py-2 text-xs text-[color:var(--color-text-faint)]">Совпадений не найдено — можно вписать ID вручную</div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Employees() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const location = useLocation();

  const emptyForm = {
    id: '',
    id_original: '',
    name: '',
    full_name: '',
    phone: '',
    card_number: '',
    bank: '',
    work_place: '',
    clothing_size: '',
    birthdate: '',
    note: '',
    external_code: '',
    status: 'active',
    position: '',
    amo_user_id: '',
    is_admin: false,
    bot_user: false,
    vk_id: '',
    sync_to_bot: false,
    photo_file: null,
    photo_url: '',
    payout_chat_key: '',
    archived: false,
  };

  const [employees, setEmployees] = useState([]);
  const [positions, setPositions] = useState([]);
  const [amoUsers, setAmoUsers] = useState(null);   // null = not loaded / unavailable
  const [workPlaces, setWorkPlaces] = useState([]);
  const [cashierChats, setCashierChats] = useState([]);
  const [filterName, setFilterName] = useState('');
  const [filterPhone, setFilterPhone] = useState('');
  const [sort, setSort] = useState('');
  const [selected, setSelected] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [confirmWarnings, setConfirmWarnings] = useState([]);
  const [activeTab, setActiveTab] = useState('overview');
  const [positionFilter, setPositionFilter] = useState(null);
  const [statusFilterEmp, setStatusFilterEmp] = useState(null);
  const [workplaceFilter, setWorkplaceFilter] = useState(null);

  useEffect(() => {
    load();
    loadPositions();
    loadCashierChats();
    loadAmoUsers();
  }, []);

  async function loadAmoUsers() {
    try {
      const res = await api.get('amo/users');
      setAmoUsers(res.data || []);
    } catch {
      setAmoUsers(null);   // amoCRM не настроен/недоступен — селект покажет подсказку
    }
  }

  useEffect(() => {
    const editId = location.state?.editId;
    if (editId && employees.length > 0) {
      const emp = employees.find((e) => e.id === editId);
      if (emp) startEdit(emp);
    }
  }, [location.state, employees]);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get('employees/', { params: { archived: false } });
      setEmployees(res.data);
    } catch (err) {
      console.error(err);
      toast('Ошибка загрузки сотрудников', 'error');
    } finally {
      setLoading(false);
    }
  }

  async function loadCashierChats() {
    try {
      const res = await api.get('config/');
      const data = res.data || {};
      const rawChats = Array.isArray(data.card_dispatch_chats)
        ? data.card_dispatch_chats
        : [];
      const fallbackId = data.card_dispatch_chat_id;
      const normalized = rawChats
        .map((chat, idx) => {
          if (typeof chat !== 'object' || chat === null) return null;
          const chatId = Number(chat.chat_id ?? chat.id);
          if (!Number.isFinite(chatId)) return null;
          const key = String(chat.key ?? chat.id ?? `chat_${idx + 1}`);
          const name = String(chat.name ?? `Кассир ${idx + 1}`);
          return { key, name, chat_id: chatId };
        })
        .filter(Boolean);
      const fallbackNumber = Number(fallbackId);
      if (
        !normalized.length &&
        Number.isFinite(fallbackNumber) &&
        fallbackNumber !== 0
      ) {
        normalized.push({
          key: 'default',
          name: 'Основной кассир',
          chat_id: fallbackNumber,
        });
      }
      setCashierChats(normalized);
    } catch (err) {
      console.error(err);
    }
  }

  async function loadPositions() {
    try {
      const res = await api.get('dictionary/');
      setPositions(res.data.positions || []);
      setWorkPlaces(res.data.work_places || []);
    } catch (err) {
      console.error(err);
    }
  }

  function resolveChatName(key) {
    if (!cashierChats.length) {
      return key ? key : '';
    }
    if (!key) {
      const first = cashierChats[0];
      return first ? `По умолчанию — ${first.name}` : 'По умолчанию';
    }
    const found = cashierChats.find((chat) => chat.key === key);
    if (found) {
      return found.name;
    }
    return key ? `Неизвестный чат (${key})` : '';
  }

  function formatDateRu(value) {
    if (!value) return '';
    return new Date(value).toLocaleDateString('ru-RU');
  }

  function startCreate() {
    setForm({ ...emptyForm, id_original: '' });
    setShowForm(true);
  }

  function startEdit(emp) {
    const isBotUser = emp.bot_user ?? (!String(emp.id).startsWith('nb_') && !!emp.id);
    setForm({ ...emp, id: emp.id, id_original: emp.id, bot_user: isBotUser, payout_chat_key: emp.payout_chat_key || '' });
    setShowForm(true);
  }

  function toggleSelect(id, checked) {
    setSelected((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)));
  }

  async function deleteSelected() {
    if (!selected.length) return;
    if (!window.confirm('Удалить выбранных сотрудников?')) return;
    try {
      for (const id of selected) {
        await api.delete(`employees/${id}`);
      }
      setSelected([]);
      toast('Сотрудники удалены', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка при удалении', 'error');
    }
  }

  async function moveToArchive(id) {
    const employee = employees.find((e) => e.id === id);
    if (!employee) return;
    if (employee.status === 'active') {
      toast('Сначала измените статус на inactive', 'warning');
      return;
    }
    if (!window.confirm('Перенести сотрудника в архив?')) return;
    try {
      await api.post(`employees/${id}/archive`);
      setSelected((prev) => prev.filter((value) => value !== id));
      toast('Сотрудник перемещён в архив', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Не удалось переместить в архив', 'error');
    }
  }

  async function doSave() {
    const payload = {
      name: form.name,
      full_name: form.full_name,
      phone: form.phone,
      card_number: form.card_number || '',
      bank: form.bank || '',
      work_place: form.work_place || '',
      clothing_size: form.clothing_size || '',
      birthdate: form.birthdate || null,
      note: form.note || '',
      external_code: form.external_code || '',
      status: form.status || 'active',
      position: form.position || '',
      amo_user_id: form.amo_user_id || '',
      is_admin: form.is_admin,
      bot_user: form.bot_user,
      vk_id: form.vk_id || '',
      payout_chat_key: form.payout_chat_key || null,
    };
    try {
      if (form.id_original) {
        await api.put(`employees/${form.id_original}`, { id: form.bot_user ? form.id : form.id_original, ...payload });
      } else {
        if (form.bot_user) payload.id = form.id || '';
        await api.post('employees/', payload);
      }
      if (form.photo_file) {
        const fd = new FormData();
        fd.append('file', form.photo_file);
        await api.post(`employees/${payload.id}/photo`, fd);
      }
      setShowForm(false);
      setForm(emptyForm);
      toast('Сотрудник сохранён', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка при сохранении', 'error');
    }
  }

  function saveForm() {
    if (!form.name || !form.full_name || !form.phone) {
      toast('Заполните обязательные поля', 'warning');
      return;
    }
    const warnings = [];
    if (!form.card_number) {
      warnings.push('Номер карты не заполнен.');
    } else {
      const phoneDigits = form.phone.replace(/\D/g, '');
      const cardDigits  = form.card_number.replace(/\D/g, '');
      if (phoneDigits && cardDigits && phoneDigits !== cardDigits) {
        warnings.push('Номер карты отличается от номера телефона.');
      }
    }
    if (warnings.length > 0) {
      setConfirmWarnings(warnings);
      return;
    }
    doSave();
  }

  function handleFile(e) {
    const file = e.target.files?.[0];
    if (file) {
      setForm((f) => ({ ...f, photo_file: file }));
    }
  }

  async function downloadPdf() {
    try {
      const res = await api.get('employees/export.pdf', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'employees.pdf');
      document.body.appendChild(link);
      link.click();
      toast('PDF скачан', 'success');
    } catch (err) {
      console.error(err);
      toast('Ошибка экспорта PDF', 'error');
    }
  }

  const filtered = employees.filter(
    (e) =>
      e.full_name.toLowerCase().includes(filterName.toLowerCase()) &&
      e.phone.toLowerCase().includes(filterPhone.toLowerCase()) &&
      (!positionFilter || (e.position || 'Без должности') === positionFilter) &&
      (!statusFilterEmp || e.status === statusFilterEmp) &&
      (!workplaceFilter || (e.work_place || 'Не указано') === workplaceFilter)
  );

  const sortedList = [...filtered];
  if (sort === 'name') {
    sortedList.sort((a, b) => a.full_name.localeCompare(b.full_name));
  } else if (sort === 'position') {
    sortedList.sort((a, b) => a.position.localeCompare(b.position));
  }

  const activeCount = useMemo(() => employees.filter((e) => e.status === 'active').length, [employees]);
  const adminCount = useMemo(() => employees.filter((e) => e.is_admin).length, [employees]);
  const noCardCount = useMemo(() => employees.filter((e) => !e.card_number).length, [employees]);

  const positionDonutData = useMemo(() => {
    const map = {};
    for (const e of employees) {
      const key = e.position || 'Без должности';
      map[key] = (map[key] || 0) + 1;
    }
    return Object.entries(map)
      .sort(([, a], [, b]) => b - a)
      .map(([name, value]) => ({ name, value }));
  }, [employees]);

  const statusDonutData = useMemo(() => {
    const active = employees.filter((e) => e.status === 'active').length;
    const inactive = employees.length - active;
    return [
      { name: 'Активные', value: active },
      { name: 'Неактивные', value: inactive },
    ].filter((d) => d.value > 0);
  }, [employees]);

  const workplaceData = useMemo(() => {
    const map = {};
    for (const e of employees) {
      const key = e.work_place || 'Не указано';
      map[key] = (map[key] || 0) + 1;
    }
    return Object.entries(map)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count);
  }, [employees]);

  const hireTrendData = useMemo(() => {
    const map = {};
    for (const e of employees) {
      if (!e.created_at) continue;
      const d = new Date(e.created_at);
      if (isNaN(d)) continue;
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      map[key] = (map[key] || 0) + 1;
    }
    return Object.entries(map)
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-12)
      .map(([key, count]) => {
        const [y, m] = key.split('-');
        return { label: `${m}.${y.slice(2)}`, count };
      });
  }, [employees]);

  const mainTabs = [
    { key: 'overview', label: 'Обзор', icon: <BarChart3 size={14} /> },
    { key: 'list', label: 'Список', icon: <Users size={14} />, badge: sortedList.length },
  ];

  return (
    <div className="space-y-6 max-w-full mx-auto">
      <TopProgressBar active={loading} />
      <div>
        <span className="ui-eyebrow mb-3">
          {activeCount} в штате{employees.length > activeCount ? ` · всего ${employees.length}` : ''}
        </span>
        <h2 className="text-2xl font-semibold">Сотрудники</h2>
      </div>
      <UpcomingBirthdays />

      <Tabs tabs={mainTabs} active={activeTab} onChange={setActiveTab} />

      {activeTab === 'overview' && (
        <div className="space-y-5">
          {loading ? (
            // Держит сетку из четырёх карточек, а не подменяет её строкой
            // текста — иначе содержимое подпрыгивает при загрузке.
            <SkeletonStats count={4} />
          ) : (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <KpiCard label="Всего сотрудников" value={employees.length} accent="var(--color-primary)" icon={Users} />
                <KpiCard
                  label="Активных"
                  value={activeCount}
                  sub={employees.length ? `${((activeCount / employees.length) * 100).toFixed(0)}% от всех` : '—'}
                  accent="var(--color-success)"
                  icon={UserCheck}
                />
                <KpiCard label="Администраторов" value={adminCount} accent="var(--color-warning)" icon={ShieldCheck} />
                <KpiCard
                  label="Без карты"
                  value={noCardCount}
                  sub="требуют заполнения"
                  accent="var(--color-danger)"
                  icon={CreditCard}
                />
              </div>

              {hireTrendData.length > 0 && (
                <div className="app-card p-5">
                  <div className="text-sm font-semibold mb-4 flex items-center gap-2">
                    <TrendingUp size={15} className="text-[color:var(--color-primary)]" />
                    Динамика найма
                  </div>
                  <ResponsiveContainer width="100%" height={200}>
                    <AreaChart data={hireTrendData} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
                      <defs>
                        <linearGradient id="hireGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="var(--color-primary)" stopOpacity={0.35} />
                          <stop offset="95%" stopColor="var(--color-primary)" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                      <XAxis dataKey="label" tick={{ fontSize: 10, fill: 'var(--color-muted-foreground)' }} tickLine={false} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: 'var(--color-muted-foreground)' }} tickLine={false} axisLine={false} width={30} />
                      <Tooltip formatter={(v) => [v, 'Принято']} />
                      <Area
                        type="monotone"
                        dataKey="count"
                        stroke="var(--color-primary)"
                        strokeWidth={2}
                        fill="url(#hireGrad)"
                        dot={false}
                        activeDot={{ r: 4, strokeWidth: 0 }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <ShareDonut
                  data={positionDonutData}
                  total={employees.length}
                  title="По должностям"
                  icon={Layers}
                  activeName={positionFilter}
                  onSelect={(name) => { setPositionFilter((prev) => (prev === name ? null : name)); setActiveTab('list'); }}
                />
                <ShareDonut
                  data={statusDonutData}
                  total={employees.length}
                  title="По статусу"
                  icon={UserCheck}
                  colorOf={(name) => (name === 'Активные' ? 'var(--color-success)' : 'var(--color-text-muted)')}
                  activeName={statusFilterEmp ? (statusFilterEmp === 'active' ? 'Активные' : 'Неактивные') : null}
                  onSelect={(name) => {
                    const status = name === 'Активные' ? 'active' : 'inactive';
                    setStatusFilterEmp((prev) => (prev === status ? null : status));
                    setActiveTab('list');
                  }}
                />
              </div>

              {workplaceData.length > 0 && (
                <div className="app-card p-5">
                  <div className="text-sm font-semibold mb-4 flex items-center gap-2">
                    <BarChart3 size={15} className="text-[color:var(--color-primary)]" />
                    По местам работы
                    {workplaceFilter && <span className="text-xs font-normal text-[color:var(--color-muted-foreground)]">· фильтр: {workplaceFilter}</span>}
                  </div>
                  <ResponsiveContainer width="100%" height={Math.max(120, workplaceData.length * 40)}>
                    <BarChart
                      data={workplaceData}
                      layout="vertical"
                      margin={{ top: 0, right: 12, bottom: 0, left: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--color-border)" />
                      <XAxis type="number" allowDecimals={false} tick={{ fontSize: 10, fill: 'var(--color-muted-foreground)' }} tickLine={false} axisLine={false} />
                      <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: 'var(--color-muted-foreground)' }} tickLine={false} width={130} />
                      <Tooltip formatter={(v) => [v, 'Сотрудников']} />
                      <Bar
                        dataKey="count"
                        radius={[0, 4, 4, 0]}
                        onClick={(entry) => { setWorkplaceFilter((prev) => (prev === entry.name ? null : entry.name)); setActiveTab('list'); }}
                        cursor="pointer"
                      >
                        {workplaceData.map((d, i) => (
                          <Cell key={d.name} fill={CHART_COLORS[i % CHART_COLORS.length]} opacity={workplaceFilter && workplaceFilter !== d.name ? 0.35 : 1} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {activeTab === 'list' && (
        <>
      {(positionFilter || statusFilterEmp || workplaceFilter) && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-[color:var(--color-muted-foreground)]">Фильтр из графика:</span>
          {positionFilter && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] font-medium">
              {positionFilter}
              <button onClick={() => setPositionFilter(null)} className="hover:opacity-70"><X size={12} /></button>
            </span>
          )}
          {statusFilterEmp && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] font-medium">
              {statusFilterEmp === 'active' ? 'Активные' : 'Неактивные'}
              <button onClick={() => setStatusFilterEmp(null)} className="hover:opacity-70"><X size={12} /></button>
            </span>
          )}
          {workplaceFilter && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] font-medium">
              {workplaceFilter}
              <button onClick={() => setWorkplaceFilter(null)} className="hover:opacity-70"><X size={12} /></button>
            </span>
          )}
        </div>
      )}
      <div className="flex flex-wrap gap-2 items-center">
        <input
          className="input flex-1 min-w-[140px]"
          placeholder="Фильтр по ФИО"
          value={filterName}
          onChange={(e) => setFilterName(e.target.value)}
        />
        <input
          className="input flex-1 min-w-[140px]"
          placeholder="Фильтр по телефону"
          value={filterPhone}
          onChange={(e) => setFilterPhone(e.target.value)}
        />
        <select
          className="input w-full sm:w-auto"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          <option value="">Без сортировки</option>
          <option value="name">По имени</option>
          <option value="position">По должности</option>
        </select>
        <button className="btn w-full sm:w-auto" onClick={downloadPdf}>
          <FileDown size={16} /> Экспорт PDF
        </button>
        <button className="btn w-full sm:w-auto" onClick={startCreate}>
          <UserPlus size={16} /> Добавить сотрудника
        </button>
        <button
          className="btn w-full sm:w-auto bg-red-600 hover:bg-red-700 disabled:opacity-50"
          disabled={!selected.length}
          onClick={deleteSelected}
        >
          <Trash2 size={16} /> Удалить выбранных
        </button>
        <Link
          className="btn w-full sm:w-auto bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text)] hover:bg-[color:var(--color-control-bg-hover)]"
          to="/admin/archive"
        >
          <Archive size={16} /> Архив
        </Link>
      </div>
      <p className="text-sm text-[color:var(--color-text-muted)]">
        Чтобы отправить сотрудника в архив, сначала переведите его в статус{' '}
        <span className="font-medium">inactive</span>.
      </p>

      {loading ? (
        <div className="border rounded shadow bg-[color:var(--color-surface)] p-4">
          <SkeletonTable rows={8} cols={6} />
        </div>
      ) : (
        <ResponsiveTable
          data={sortedList}
          keyFn={(e) => e.id}
          emptyText="Нет сотрудников"
          rowClass={(e) => `cursor-pointer ${e.is_admin ? 'bg-orange-50 hover:bg-orange-100' : 'hover:bg-blue-50'} ${e.status !== 'active' ? 'opacity-60' : ''}`}
          columns={[
            {
              label: '',
              cellClass: 'w-10',
              render: (e) => (
                <span onClick={(ev) => ev.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selected.includes(e.id)}
                    onChange={(ev) => toggleSelect(e.id, ev.target.checked)}
                  />
                </span>
              ),
            },
            {
              label: 'Фото',
              mobileHide: true,
              render: (e) => (
                <span onClick={(ev) => ev.stopPropagation()}>
                  {e.photo_url ? (
                    <img
                      src={e.photo_url}
                      alt=""
                      className="w-8 h-8 rounded-full object-cover cursor-pointer"
                      onClick={() => window.open(e.photo_url, '_blank')}
                    />
                  ) : (
                    <div className="w-8 h-8 bg-[color:var(--color-control-bg)] rounded-full flex items-center justify-center">
                      <span className="text-[color:var(--color-text-muted)] text-xs">—</span>
                    </div>
                  )}
                </span>
              ),
            },
            {
              label: 'ФИО',
              primary: true,
              render: (e) => (
                <span onClick={() => navigate(`/admin/employees/${e.id}`)}>
                  {e.full_name}
                  {e.is_admin && <span className="ml-2 text-xs text-orange-600 font-medium">Админ</span>}
                </span>
              ),
            },
            { label: 'Имя', key: 'name', mobileHide: true },
            { label: 'Телефон', key: 'phone' },
            {
              label: 'День рождения',
              render: (e) => formatDateRu(e.birthdate),
            },
            { label: 'Должность', key: 'position' },
            {
              label: 'Роль',
              mobileHide: true,
              render: (e) => (e.is_admin ? 'Админ' : 'Польз.'),
            },
            {
              label: 'Создан',
              mobileHide: true,
              cellClass: 'text-[color:var(--color-text-faint)] text-xs',
              render: (e) => new Date(e.created_at).toLocaleDateString(),
            },
            {
              label: '',
              isAction: true,
              cellClass: 'text-right',
              render: (e) => {
                const canArchive = e.status !== 'active';
                const archiveTitle = canArchive
                  ? 'Перенести в архив'
                  : 'Переведите сотрудника в статус inactive, чтобы архивировать';
                return (
                  <span className="inline-flex items-center gap-2" onClick={(ev) => ev.stopPropagation()}>
                    <button className="text-blue-600" onClick={() => startEdit(e)} title="Редактировать">
                      <Pencil size={16} />
                    </button>
                    <a
                      href={`/api/employees/${e.id}/profile.pdf`}
                      className="text-[color:var(--color-text-muted)]"
                      title="Скачать PDF"
                    >
                      <FileDown size={16} />
                    </a>
                    <button
                      className={
                        canArchive
                          ? 'text-amber-600 hover:text-amber-800'
                          : 'cursor-not-allowed text-[color:var(--color-text-faint)]'
                      }
                      onClick={() => { if (canArchive) moveToArchive(e.id); }}
                      disabled={!canArchive}
                      title={archiveTitle}
                    >
                      <Archive size={16} className={!canArchive ? 'opacity-50' : ''} />
                    </button>
                  </span>
                );
              },
            },
          ]}
        />
      )}
        </>
      )}

      {showForm && (
        <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setShowForm(false)}>
          <div className="modal-card max-w-lg overflow-y-auto max-h-[90vh]">
            <h2 className="text-xl font-semibold">
              {form.id_original ? 'Редактирование' : 'Новый сотрудник'}
            </h2>

            {/* Bot user toggle */}
            <label className="flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={form.bot_user}
                onChange={(e) => setForm({ ...form, bot_user: e.target.checked, id: e.target.checked ? form.id : '' })}
              />
              Пользователь бота
            </label>

            {form.bot_user && (
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Telegram ID</label>
                <input className="modal-control" value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} />
              </div>
            )}

            <div>
              <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">
                VK ID <span className="text-[color:var(--color-muted-foreground)] font-normal">(необязательно — второй канал бота, в дополнение к Telegram)</span>
              </label>
              <input className="modal-control" value={form.vk_id} onChange={(e) => setForm({ ...form, vk_id: e.target.value })} placeholder="Обычно проще привязать на странице «Доступы»" />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Имя *</label>
                <input className="modal-control" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">ФИО *</label>
                <input className="modal-control" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Телефон *</label>
                <input className="modal-control" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Номер карты</label>
                <input className="modal-control" value={form.card_number} onChange={(e) => setForm({ ...form, card_number: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Банк</label>
                <input className="modal-control" value={form.bank} onChange={(e) => setForm({ ...form, bank: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Размер формы</label>
                <input className="modal-control" value={form.clothing_size} onChange={(e) => setForm({ ...form, clothing_size: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Должность</label>
                <select className="modal-control" value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })}>
                  <option value="">Не выбрано</option>
                  {positions.map((pos) => <option key={pos} value={pos}>{pos}</option>)}
                </select>
              </div>
              {(form.position || '').trim().toLowerCase() === 'менеджер по работе с клиентами' && (
                <div>
                  <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Пользователь amoCRM</label>
                  {amoUsers ? (
                    <select className="modal-control" value={form.amo_user_id || ''} onChange={(e) => setForm({ ...form, amo_user_id: e.target.value })}>
                      <option value="">— не привязан —</option>
                      {amoUsers.map((u) => <option key={u.id} value={String(u.id)}>{u.name} (#{u.id})</option>)}
                    </select>
                  ) : (
                    <div className="text-xs text-[color:var(--color-muted-foreground)]">
                      amoCRM не подключён — привязка станет доступна после авторизации amoCRM.
                    </div>
                  )}
                </div>
              )}
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Место работы</label>
                <select className="modal-control" value={form.work_place} onChange={(e) => setForm({ ...form, work_place: e.target.value })}>
                  <option value="">Не выбрано</option>
                  {workPlaces.map((wp) => <option key={wp} value={wp}>{wp}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Дата рождения</label>
                <input type="date" className="modal-control" value={form.birthdate} onChange={(e) => setForm({ ...form, birthdate: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Чат кассира</label>
                <select className="modal-control" value={form.payout_chat_key} onChange={(e) => setForm({ ...form, payout_chat_key: e.target.value })}>
                  <option value="">{cashierChats.length ? `По умолчанию — ${cashierChats[0].name}` : 'По умолчанию'}</option>
                  {cashierChats.map((chat) => <option key={chat.key} value={chat.key}>{chat.name} — {chat.chat_id}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Статус</label>
                <select className="modal-control" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  <option value="active">Активный</option>
                  <option value="inactive">Неактивный</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Внешний код (ID в Агбис, для кассовых перемещений)</label>
              <ExternalUserSelect value={form.external_code} onChange={(v) => setForm({ ...form, external_code: v })} />
            </div>

            <div>
              <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Заметка</label>
              <textarea className="modal-control" rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
            </div>

            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.sync_to_bot} onChange={(e) => setForm({ ...form, sync_to_bot: e.target.checked })} />
                Отразить в боте
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.is_admin} onChange={(e) => setForm({ ...form, is_admin: e.target.checked })} />
                Администратор
              </label>
            </div>

            <div>
              <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Фото</label>
              <input type="file" onChange={handleFile} />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button className="btn" onClick={() => setShowForm(false)}>Отмена</button>
              <button className="btn btn--primary" onClick={saveForm}>Сохранить</button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm warnings dialog */}
      {confirmWarnings.length > 0 && (
        <div className="modal-backdrop" style={{ zIndex: 70 }}>
          <div className="modal-card max-w-sm w-full">
            <h3 className="text-base font-semibold">Предупреждение</h3>
            <ul className="text-sm space-y-1">
              {confirmWarnings.map((w, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-amber-500 mt-0.5">⚠</span> {w}
                </li>
              ))}
            </ul>
            <p className="text-sm text-[color:var(--color-muted-foreground)]">Всё равно сохранить?</p>
            <div className="flex justify-end gap-2 pt-1">
              <button className="btn" onClick={() => setConfirmWarnings([])}>Отмена</button>
              <button className="btn btn--primary" onClick={() => { setConfirmWarnings([]); doSave(); }}>Сохранить</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
