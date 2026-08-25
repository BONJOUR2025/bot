import { useEffect, useMemo, useState } from 'react';
import {
  Users, Copy, RefreshCw, KeyRound, Link as LinkIcon, RotateCcw,
  LogIn, LogOut, UsersRound,
} from 'lucide-react';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip,
} from 'recharts';
import api from '../api';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import KpiCard from '../components/ui/Kpi.jsx';
import { useToast } from '../providers/ToastProvider.jsx';

function fmtDateTime(value) {
  if (!value) return '';
  return new Date(value).toLocaleString('ru-RU');
}

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

function daysAgoStr(days) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function fmtDate(value) {
  if (!value) return '';
  const [y, m, d] = value.split('-');
  return `${d}.${m}`;
}

const TABS = [
  { id: 'table', label: 'Таблица' },
  { id: 'analytics', label: 'Аналитика' },
  { id: 'device', label: 'Подключение устройства' },
];

export default function VisitorCounters() {
  const { toast } = useToast();
  const [tab, setTab] = useState('table');
  const [summary, setSummary] = useState([]);
  const [salons, setSalons] = useState([]);
  const [filters, setFilters] = useState({ from: daysAgoStr(13), to: todayStr(), salon_id: '' });
  const [loading, setLoading] = useState(true);
  const [cumulative, setCumulative] = useState([]);
  const [resetting, setResetting] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadSalons();
  }, []);

  useEffect(() => {
    load();
  }, [filters]);

  useEffect(() => {
    loadCumulative();
  }, []);

  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  async function loadSalons() {
    try {
      const res = await api.get('salons/');
      setSalons(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function load() {
    setLoading(true);
    try {
      const params = {
        date_from: filters.from || undefined,
        date_to: filters.to || undefined,
        salon_id: filters.salon_id || undefined,
      };
      const res = await api.get('visitor-events/summary', { params });
      setSummary(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function loadCumulative() {
    try {
      const res = await api.get('visitor-events/totals');
      setCumulative(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await Promise.all([load(), loadCumulative(), loadSalons()]);
    } finally {
      setRefreshing(false);
    }
  }

  async function handleReset(salonId, salonName) {
    if (!confirm(`Полностью обнулить счётчик «${salonName}»?\nИстория событий и таблица/аналитика не удаляются — обнуляется только накопленный итог этой точки.`)) {
      return;
    }
    setResetting(salonId);
    try {
      await api.post('visitor-events/reset', { salon_id: salonId });
      toast(`Счётчик «${salonName}» обнулён`, 'success');
      loadCumulative();
    } catch (err) {
      console.error(err);
      toast('Ошибка обнуления счётчика', 'error');
    } finally {
      setResetting(null);
    }
  }

  const totals = summary.reduce(
    (acc, row) => ({
      in: acc.in + row.in_count,
      out: acc.out + row.out_count,
    }),
    { in: 0, out: 0 }
  );

  // Живые агрегаты по датчикам «на связи» — из cumulative (реально
  // накопленное состояние каждой точки с последнего сброса), а не из
  // summary за выбранный период фильтра.
  const liveTotals = cumulative.reduce(
    (acc, row) => ({
      in: acc.in + row.in_count,
      out: acc.out + row.out_count,
      net: acc.net + row.net,
    }),
    { in: 0, out: 0, net: 0 }
  );

  // Персональный спарклайн входов по дням для каждой точки — последние
  // до 7 дней из summary (реальная история за выбранный период фильтра).
  const sparkBySalon = useMemo(() => {
    const map = new Map();
    for (const row of summary) {
      const arr = map.get(row.salon_id) || [];
      arr.push(row);
      map.set(row.salon_id, arr);
    }
    for (const [key, arr] of map) {
      arr.sort((a, b) => a.date.localeCompare(b.date));
      map.set(key, arr.slice(-7));
    }
    return map;
  }, [summary]);

  // Точка с наибольшим числом входов СЕГОДНЯ — «сейчас здесь больше
  // всего людей», не просто статичный лидер по накопленному итогу.
  const hottestSalonId = useMemo(() => {
    const todayKey = todayStr();
    let best = null;
    let bestCount = 0;
    for (const row of summary) {
      if (row.date !== todayKey) continue;
      if (row.in_count > bestCount) {
        bestCount = row.in_count;
        best = row.salon_id;
      }
    }
    return bestCount > 0 ? best : null;
  }, [summary]);

  const columns = [
    { label: 'Дата', key: 'date', primary: true },
    { label: 'Салон', render: (row) => row.salon_name || row.salon_id },
    { label: 'Вошло', render: (row) => row.in_count },
    { label: 'Вышло', render: (row) => row.out_count },
    { label: 'Сейчас в зале', render: (row) => row.net },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <span className="ui-eyebrow mb-3">Проходимость точек по датчикам</span>
          <h2 className="text-2xl font-semibold">Счётчик посетителей</h2>
        </div>
        <button
          type="button"
          className="btn flex items-center gap-1.5"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /> Обновить
        </button>
      </div>

      <nav className="flex flex-wrap gap-1.5 bg-[color:var(--color-bg-secondary)] rounded-xl p-1.5">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === id
                ? 'bg-[color:var(--color-primary)] text-white'
                : 'text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-surface)]'
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-end gap-3">
        <div className="w-full sm:w-auto">
          <label className="block text-xs text-[color:var(--color-text-muted)] mb-1">С даты</label>
          <input
            type="date"
            className="input w-full sm:w-auto"
            value={filters.from}
            onChange={(e) => setFilters((f) => ({ ...f, from: e.target.value }))}
          />
        </div>
        <div className="w-full sm:w-auto">
          <label className="block text-xs text-[color:var(--color-text-muted)] mb-1">По дату</label>
          <input
            type="date"
            className="input w-full sm:w-auto"
            value={filters.to}
            onChange={(e) => setFilters((f) => ({ ...f, to: e.target.value }))}
          />
        </div>
        <div>
          <label className="block text-xs text-[color:var(--color-text-muted)] mb-1">Салон</label>
          <select
            className="input"
            value={filters.salon_id}
            onChange={(e) => setFilters((f) => ({ ...f, salon_id: e.target.value }))}
          >
            <option value="">Все салоны</option>
            {salons.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="visitor-fui-readout">
        <span>SYS://visitors.sensors</span><span className="sep">·</span>
        <span>ТОЧЕК НА СВЯЗИ: <b>{cumulative.length}</b></span><span className="sep">·</span>
        <span>ВОШЛО: <b style={{ color: 'var(--color-success)' }}>{liveTotals.in}</b></span><span className="sep">·</span>
        <span>СЕЙЧАС В ЗАЛАХ: <b style={{ color: 'var(--color-primary)' }}>{Math.max(0, liveTotals.net)}</b></span><span className="sep">·</span>
        <span>{now.toLocaleDateString('ru-RU')} {now.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}:<span className="fui-cursor">{String(now.getSeconds()).padStart(2, '0')}</span></span>
      </div>

      <div className="visitor-fui-frame grid gap-3 sm:grid-cols-2 lg:grid-cols-3 p-3">
        <span className="visitor-fui-corner-tr" />
        <span className="visitor-fui-corner-bl" />
        <span className="visitor-fui-scan" />
        {cumulative.map((row) => {
          const spark = sparkBySalon.get(row.salon_id) || [];
          const maxSpark = Math.max(...spark.map((d) => d.in_count), 1);
          const isHottest = row.salon_id === hottestSalonId;
          return (
            <div key={row.salon_id} className="app-card p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-xs text-[color:var(--color-text-muted)] flex items-center gap-1.5">
                    {isHottest && (
                      <span className="fui-radar fui-radar--alert" title="Больше всего входов сегодня"><i /><i /><i /><b /></span>
                    )}
                    <span>{row.salon_name || row.salon_id}{row.reset_at ? ` · с ${fmtDateTime(row.reset_at)}` : ''}</span>
                  </div>
                  <div className="text-2xl font-semibold text-[color:var(--color-text)]">{row.in_count}</div>
                  <div className="text-xs text-[color:var(--color-text-muted)] mt-1">Вышло: {row.out_count} · Сейчас в зале: {row.net}</div>
                  {spark.length > 1 && (
                    <div className="visitor-fui-spark" title="Входы по дням за выбранный период">
                      {spark.map((d) => (
                        <i
                          key={d.date}
                          style={{ height: `${Math.max(3, (d.in_count / maxSpark) * 20)}px`, opacity: 0.4 + (d.in_count / maxSpark) * 0.6 }}
                          title={`${fmtDate(d.date)}: ${d.in_count}`}
                        />
                      ))}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  className="btn flex items-center gap-1.5"
                  onClick={() => handleReset(row.salon_id, row.salon_name || row.salon_id)}
                  disabled={resetting === row.salon_id}
                >
                  <RotateCcw size={14} /> Обнулить
                </button>
              </div>
            </div>
          );
        })}
        {cumulative.length === 0 && (
          <p className="text-sm text-[color:var(--color-text-muted)]">Нет салонов с данными счётчика.</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <KpiCard label="Вошло за период" value={totals.in} accent="var(--color-success)" icon={LogIn} />
        <KpiCard label="Вышло за период" value={totals.out} accent="var(--color-warning)" icon={LogOut} />
        <KpiCard label="Сейчас в зале" value={Math.max(0, totals.in - totals.out)} accent="var(--color-primary)" icon={UsersRound} />
      </div>

      {tab === 'table' && (
        loading ? (
          <p className="text-[color:var(--color-text-muted)]">Загрузка…</p>
        ) : (
          <ResponsiveTable
            columns={columns}
            data={summary}
            keyFn={(row) => `${row.date}-${row.salon_id}`}
            emptyText="Нет данных за выбранный период"
          />
        )
      )}

      {tab === 'analytics' && <VisitorAnalytics summary={summary} loading={loading} />}

      {tab === 'device' && <DeviceConnection salons={salons} />}
    </div>
  );
}

function VisitorAnalytics({ summary, loading }) {
  const chartData = useMemo(() => {
    const byDate = new Map();
    for (const row of summary) {
      const entry = byDate.get(row.date) || { date: row.date, visits: 0 };
      entry.visits += row.in_count;
      byDate.set(row.date, entry);
    }
    return Array.from(byDate.values())
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((row) => ({ ...row, label: fmtDate(row.date) }));
  }, [summary]);

  const bySalon = useMemo(() => {
    const map = new Map();
    for (const row of summary) {
      const key = row.salon_name || row.salon_id;
      const entry = map.get(key) || { name: key, visits: 0 };
      entry.visits += row.in_count;
      map.set(key, entry);
    }
    return Array.from(map.values()).sort((a, b) => b.visits - a.visits);
  }, [summary]);

  if (loading) return <p className="text-[color:var(--color-text-muted)]">Загрузка…</p>;
  if (chartData.length === 0) {
    return (
      <div className="rounded border border-dashed border-[color:var(--color-border)] bg-[color:var(--color-surface)] p-6 text-center text-[color:var(--color-text-muted)]">
        Нет данных за выбранный период
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="app-card p-4">
        <h3 className="font-semibold mb-3">Посещений по дням</h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #e5e7eb)" />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} width={40} />
            <Tooltip />
            <Bar dataKey="visits" name="Посещений" fill="var(--color-primary)" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="app-card p-4">
        <h3 className="font-semibold mb-3">По салонам (за период)</h3>
        <ResponsiveContainer width="100%" height={Math.max(200, bySalon.length * 44)}>
          <BarChart data={bySalon} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #e5e7eb)" />
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} width={140} />
            <Tooltip />
            <Bar dataKey="visits" name="Посещений" fill="var(--color-primary)" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function DeviceConnection({ salons }) {
  const { toast } = useToast();
  const [apiKey, setApiKey] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const res = await api.get('config/');
      setApiKey(res.data.visitor_counter_api_key || '');
    } catch (err) {
      console.error(err);
      toast('Ошибка загрузки настроек', 'error');
    } finally {
      setLoaded(true);
    }
  }

  async function save(key) {
    setSaving(true);
    try {
      await api.patch('config/', { visitor_counter_api_key: key });
      setApiKey(key);
      toast('Сохранено', 'success');
    } catch (err) {
      console.error(err);
      toast('Ошибка сохранения', 'error');
    } finally {
      setSaving(false);
    }
  }

  function generateKey() {
    const bytes = crypto.getRandomValues(new Uint8Array(24));
    const key = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    save(key);
  }

  function copy(text) {
    navigator.clipboard.writeText(text);
    toast('Скопировано', 'success');
  }

  const endpointUrl = `${window.location.origin}/api/visitor-events/ingest`;

  if (!loaded) return <p className="text-[color:var(--color-text-muted)]">Загрузка…</p>;

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="app-card p-4 space-y-3">
        <h3 className="font-semibold flex items-center gap-2"><LinkIcon size={16} /> Адрес эндпоинта</h3>
        <div className="flex gap-2">
          <input className="input flex-1 font-mono text-sm" readOnly value={endpointUrl} />
          <button type="button" className="btn" onClick={() => copy(endpointUrl)}>
            <Copy size={14} />
          </button>
        </div>
        <p className="text-xs text-[color:var(--color-text-muted)]">Метод POST, тело JSON, заголовок X-API-Key с ключом ниже.</p>
      </div>

      <div className="app-card p-4 space-y-3">
        <h3 className="font-semibold flex items-center gap-2"><KeyRound size={16} /> API-ключ устройства</h3>
        <div className="flex gap-2">
          <input
            className="input flex-1 font-mono text-sm"
            value={apiKey}
            placeholder="не задан"
            onChange={(e) => setApiKey(e.target.value)}
          />
          <button type="button" className="btn" onClick={() => copy(apiKey)} disabled={!apiKey}>
            <Copy size={14} />
          </button>
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn btn--primary" disabled={saving} onClick={() => save(apiKey)}>
            Сохранить
          </button>
          <button type="button" className="btn flex items-center gap-1.5" disabled={saving} onClick={generateKey}>
            <RefreshCw size={14} /> Сгенерировать новый
          </button>
        </div>
        {!apiKey && (
          <p className="text-xs text-amber-600">
            Ключ не задан — эндпоинт не принимает данные от устройств, пока вы не сохраните ключ.
          </p>
        )}
      </div>

      <div className="app-card p-4 space-y-3">
        <h3 className="font-semibold">Коды салонов</h3>
        <p className="text-xs text-[color:var(--color-text-muted)]">
          Устройство указывает код салона (как в разделе «Салоны»), а не внутренний id.
        </p>
        <div className="space-y-1 text-sm">
          {salons.map((s) => (
            <div key={s.id} className="flex items-center justify-between gap-2 border-b border-[color:var(--color-border)] py-1 last:border-0">
              <span>{s.name}</span>
              <code className="text-xs bg-[color:var(--color-bg-subtle)] px-2 py-0.5 rounded">{s.code || '—'}</code>
            </div>
          ))}
        </div>
      </div>

      <div className="app-card p-4 space-y-2">
        <h3 className="font-semibold">Пример запроса (MicroPython)</h3>
        <pre className="text-xs bg-gray-900 text-gray-100 rounded p-3 overflow-x-auto">
{`import urequests, ujson

URL = "${endpointUrl}"
API_KEY = "${apiKey || '<ключ>'}"
SALON_CODE = "<код салона>"

def send_event(direction):
    body = ujson.dumps({
        "salon_code": SALON_CODE,
        "direction": direction,   # "in" или "out"
        "count": 1,
        "device_id": "esp8266-01"
    })
    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}
    r = urequests.post(URL, data=body, headers=headers)
    r.close()`}
        </pre>
      </div>
    </div>
  );
}
