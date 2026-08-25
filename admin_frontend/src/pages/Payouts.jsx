import { useEffect, useMemo, useState } from 'react';
import {
  CheckCircle,
  Download,
  Pencil,
  RefreshCw,
  Trash2,
  XCircle,
  LinkIcon,
  Unlink,
  Search,
  X,
  ExternalLink,
  Bell,
  ChevronDown,
  ChevronUp,
  Send,
  Smartphone,
  MessageCircle,
  BarChart3,
  TrendingUp,
  Wallet,
  Clock,
  ArrowUpDown,
  Trophy,
  Layers,
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  ResponsiveContainer, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import api from '../api';
import { useAuth } from '../providers/AuthProvider.jsx';
import { useToast } from '../providers/ToastProvider.jsx';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { Tabs } from '../components/ui/SalaryUI.jsx';
import { groupEmployeesByPosition } from '../utils/employeeGrouping.js';
import KpiCard from '../components/ui/Kpi.jsx';
import { CHART_PALETTE as CHART_COLORS } from '../utils/chartPalette.js';

const MAX_AMOUNT = 100000;
const STATUS_OPTIONS = ['Ожидает', 'Одобрено', 'Отклонено', 'Выплачено'];
const MANAGE_DATES_PERMISSION = 'payouts-manage-dates';

const METHOD_RAW = { 'На карту': '💳 На карту', 'Из кассы': '🏦 Из кассы', 'Наличными': '🤝 Наличными' };
const DAY_NAMES = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
// Один статус — один цвет на всей странице: конвейер, полоса долей,
// бейджи ленты и рейка. Прежде «Выплачено» было акцентом, и полоса
// долей выходила сплошь фиолетовой — 99% площади в цвете, который
// должен означать исключение.
const STATUS_COLORS = {
  'Ожидает': 'var(--fui-processing)',
  'Одобрено': 'var(--color-primary)',
  'Отклонено': 'var(--color-danger)',
  'Выплачено': 'color-mix(in srgb, var(--color-text) 24%, transparent)',
};

// Стадии в том порядке, в котором по ним идёт заявка. Цвет описывает
// стадию, а не оценку: ожидание — обработка, одобрено — активная
// операция, выплачено — норма и потому нейтраль. Прежний светофор
// (янтарный / зелёный / синий) читал «одобрено» как успех, а
// «ожидает» как проблему.
const PAYOUT_STAGES = [
  { key: 'Ожидает', ink: 'var(--fui-processing)' },
  { key: 'Одобрено', ink: 'var(--color-primary)' },
  { key: 'Выплачено', ink: 'var(--color-text-muted)' },
];

const fmtMoneyShort = (v) => (!v ? '—' : Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽');

const pad = (value) => String(value).padStart(2, '0');

// Общая ЗП/К выплате в форме выплаты считается за конкретный календарный
// месяц — по умолчанию текущий, но выплата часто оформляется в начале
// месяца за предыдущий, поэтому его можно сменить вручную.
function currentSalaryMonth() {
  const d = new Date();
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

const MONTH_LABELS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];

// Last 12 months, most recent first, for the salary-period picker.
function salaryMonthOptions() {
  const out = [];
  const d = new Date();
  d.setDate(1);
  for (let i = 0; i < 12; i++) {
    out.push({ year: d.getFullYear(), month: d.getMonth() + 1 });
    d.setMonth(d.getMonth() - 1);
  }
  return out;
}

function toInputTimestamp(value) {
  if (!value) return '';
  const source = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(source.getTime())) {
    if (typeof value === 'string') {
      const fallback = new Date(value.replace(' ', 'T'));
      if (!Number.isNaN(fallback.getTime())) {
        return toInputTimestamp(fallback);
      }
    }
    return '';
  }
  return (
    `${source.getFullYear()}-${pad(source.getMonth() + 1)}-${pad(source.getDate())}` +
    `T${pad(source.getHours())}:${pad(source.getMinutes())}:${pad(source.getSeconds())}`
  );
}

function toPayloadTimestamp(value) {
  if (!value) return undefined;
  if (!value.includes('T')) {
    return value;
  }
  const [datePart, timePart] = value.split('T');
  const [hours = '00', minutes = '00', seconds = '00'] = timePart.split(':');
  return `${datePart} ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}


function PayoutDayHeatmap({ data, activeDay, onSelect }) {
  const max = Math.max(...data.map((d) => d.sum), 1);
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <ArrowUpDown size={15} className="text-[color:var(--color-primary)]" />
        Активность по дням недели
      </div>
      <div className="space-y-2.5">
        {data.map((d, i) => {
          const pct = max > 0 ? (d.sum / max) * 100 : 0;
          const isWeekend = d.day === 'Вс' || d.day === 'Сб';
          const isActive = activeDay === i;
          return (
            <button
              key={d.day}
              type="button"
              onClick={() => onSelect?.(i)}
              className={`flex items-center gap-3 w-full text-left rounded-md -mx-1 px-1 py-0.5 transition-colors ${onSelect ? 'hover:bg-[color:var(--color-bg-secondary)] cursor-pointer' : ''} ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}
            >
              <div className="w-6 text-xs text-right text-[color:var(--color-muted-foreground)] shrink-0 font-medium">{d.day}</div>
              <div className="flex-1 h-6 rounded-lg bg-[color:var(--color-bg-secondary)] overflow-hidden">
                <div
                  className="h-full rounded-lg transition-all duration-500"
                  /* Выходные — графитом, а не янтарным: янтарный в этой
                     системе означает предупреждение, и суббота выглядела
                     проблемой, хотя это просто другой день. */
                  style={{ width: `${pct}%`, background: isWeekend ? 'color-mix(in srgb, var(--color-text) 26%, transparent)' : 'var(--color-primary)', opacity: activeDay != null && !isActive ? 0.35 : 0.85 }}
                />
              </div>
              <div className="text-xs font-medium text-right shrink-0 whitespace-nowrap">{fmtMoneyShort(d.sum)}</div>
            </button>
          );
        })}
      </div>
      <div className="flex gap-4 mt-4 text-xs text-[color:var(--color-muted-foreground)]">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm opacity-75" style={{ background: 'var(--color-primary)' }} />
          Будни
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm opacity-75" style={{ background: 'color-mix(in srgb, var(--color-text) 26%, transparent)' }} />
          Выходные
        </span>
      </div>
    </div>
  );
}

function EmployeeLeaderboard({ data, total, activeName, onSelect }) {
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <Trophy size={15} className="text-[color:var(--color-primary)]" />
        Топ получателей
      </div>
      <div className="space-y-4">
        {data.slice(0, 6).map(([name, { sum, count }], i) => {
          const pct = total > 0 ? (sum / total) * 100 : 0;
          const isActive = activeName === name;
          return (
            <button
              key={name}
              type="button"
              onClick={() => onSelect?.(name)}
              className={`block w-full text-left rounded-md -mx-1 px-1 py-1 transition-colors ${onSelect ? 'hover:bg-[color:var(--color-bg-secondary)] cursor-pointer' : ''} ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2 min-w-0">
                  {/* Ранг моношкалой вместо медалей-эмодзи: на финансовом
                      экране золото-серебро-бронза читаются как игровая
                      награда, а порядок и так задан позицией в списке. */}
                  <span className="payout-rank">{String(i + 1).padStart(2, '0')}</span>
                  <span className="text-sm font-medium truncate">{name}</span>
                </div>
                <div className="text-right shrink-0 ml-3">
                  <div className="text-sm font-bold text-[color:var(--color-primary)] whitespace-nowrap">{fmtMoneyShort(sum)}</div>
                  <div className="text-xs text-[color:var(--color-muted-foreground)]">{count} зап.</div>
                </div>
              </div>
              <div className="h-1.5 rounded-full bg-[color:var(--color-bg-secondary)] overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${pct}%`, background: CHART_COLORS[i % CHART_COLORS.length] }}
                />
              </div>
            </button>
          );
        })}
        {data.length === 0 && (
          <div className="text-sm text-[color:var(--color-muted-foreground)] text-center py-4">Нет данных</div>
        )}
      </div>
    </div>
  );
}

function StatusDonut({ data, total, title, icon: Icon, colorOf, formatValue, tooltipLabel = 'Кол-во', activeName, onSelect }) {
  const fmtVal = formatValue || ((v) => v);
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
              <Tooltip formatter={(v) => [fmtVal(v), tooltipLabel]} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex-1 space-y-2 min-w-0">
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
                    <span className="text-xs font-semibold shrink-0">{fmtVal(d.value)} ({pct.toFixed(0)}%)</span>
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

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-surface)] shadow-xl p-3 text-sm">
      <div className="font-semibold mb-1 text-[color:var(--color-muted-foreground)]">{label}</div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full" style={{ background: p.color }} />
          <span className="font-medium">{fmtMoneyShort(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

function formatDateTime(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    const fixed = value.replace(' ', 'T');
    const dt = new Date(fixed);
    if (Number.isNaN(dt.getTime())) return value;
    return (
      dt.toLocaleDateString('ru-RU') +
      ' ' +
      dt.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    );
  }
  return (
    d.toLocaleDateString('ru-RU') +
    ' ' +
    d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  );
}

// ── Movement quick-view modal (from table link icon) ─────────────
function MovementQuickViewModal({ payout, onUnlink, onChangeMove, onClose }) {
  const { toast } = useToast();
  const [moveDetails, setMoveDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(true);
  const [unlinking, setUnlinking] = useState(false);

  useEffect(() => {
    if (!payout.cash_move_id) { setLoadingDetails(false); return; }
    api.get(`cash-moves/by-id/${payout.cash_move_id}`)
      .then((r) => setMoveDetails(r.data))
      .catch(() => setMoveDetails(null))
      .finally(() => setLoadingDetails(false));
  }, [payout.cash_move_id]);

  async function handleUnlink() {
    setUnlinking(true);
    try {
      await onUnlink();
      onClose();
    } catch { toast('Ошибка отвязки', 'error'); }
    finally { setUnlinking(false); }
  }

  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-sm w-full">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold flex items-center gap-2">
            <LinkIcon size={16} className="text-green-500" /> Кассовое движение
          </h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-[color:var(--color-control-bg-hover)]"><X size={18} /></button>
        </div>
        {loadingDetails ? (
          <div className="flex items-center justify-center gap-2 py-4 text-[color:var(--color-text-faint)] text-sm">
            <RefreshCw size={14} className="animate-spin" /> Загрузка…
          </div>
        ) : moveDetails ? (
          <div className="text-sm space-y-2">
            <div className="flex justify-between">
              <span className="text-[color:var(--color-text-muted)]">Дата</span>
              <span>{moveDetails.DK_DATE || '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[color:var(--color-text-muted)]">Сумма</span>
              <span className="font-semibold text-blue-700">
                {Number(moveDetails.SUMM).toLocaleString('ru-RU')} ₽
              </span>
            </div>
            {moveDetails.dep_name && (
              <div className="flex justify-between">
                <span className="text-[color:var(--color-text-muted)]">Филиал</span>
                <span>{moveDetails.dep_name}</span>
              </div>
            )}
            {moveDetails.BASIS && (
              <div className="flex justify-between gap-4">
                <span className="text-[color:var(--color-text-muted)] shrink-0">Основание</span>
                <span className="font-mono text-xs text-right truncate min-w-0">{moveDetails.BASIS}</span>
              </div>
            )}
          </div>
        ) : (
          <div className="text-sm text-[color:var(--color-text-faint)]">ID: {payout.cash_move_id}</div>
        )}
        <div className="flex justify-between mt-5">
          <button
            className="btn text-sm border border-red-200 text-red-500 hover:border-red-400 hover:text-red-700 disabled:opacity-50"
            onClick={handleUnlink}
            disabled={unlinking}
          >
            {unlinking
              ? <RefreshCw size={12} className="inline animate-spin mr-1" />
              : <Unlink size={13} className="inline mr-1" />}
            Отвязать
          </button>
          <div className="flex gap-2">
            <button className="btn text-sm" onClick={() => { onClose(); onChangeMove(); }}>Изменить</button>
            <button className="btn" onClick={onClose}>Закрыть</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Movement picker modal ─────────────────────────────────────────
function MovementPickerModal({ payout, onLink, onClose }) {
  const { toast } = useToast();
  const defaultFrom = () => {
    if (!payout?.timestamp) return '';
    const d = new Date(payout.timestamp.replace(' ', 'T'));
    if (isNaN(d)) return '';
    d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 10);
  };
  const defaultTo = () => {
    if (!payout?.timestamp) return '';
    const d = new Date(payout.timestamp.replace(' ', 'T'));
    if (isNaN(d)) return '';
    d.setDate(d.getDate() + 7);
    return d.toISOString().slice(0, 10);
  };
  const [dateFrom, setDateFrom] = useState(defaultFrom);
  const [dateTo, setDateTo]     = useState(defaultTo);
  const [moves, setMoves]       = useState([]);
  const [loading, setLoading]   = useState(false);
  const [linking, setLinking]   = useState(null);

  async function loadMoves() {
    setLoading(true);
    try {
      const params = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo)   params.date_to   = dateTo;
      const res = await api.get('cash-moves/', { params });
      setMoves(Array.isArray(res.data) ? res.data : []);
    } catch { toast('Ошибка загрузки движений', 'error'); }
    finally { setLoading(false); }
  }

  useEffect(() => { loadMoves(); }, []);

  async function handleLink(moveId) {
    setLinking(moveId);
    try {
      await onLink(moveId);
      onClose();
    } catch { toast('Ошибка привязки', 'error'); }
    finally { setLinking(null); }
  }

  return (
    <div className="modal-backdrop" style={{ zIndex: 60 }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold flex items-center gap-2">
            <LinkIcon size={16} /> Выбрать кассовое движение
          </h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-[color:var(--color-control-bg-hover)]"><X size={18} /></button>
        </div>

        <div className="flex flex-col sm:flex-row sm:flex-wrap gap-2 mb-3">
          <input type="date" className="input w-full sm:w-auto sm:flex-1" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          <input type="date" className="input w-full sm:w-auto sm:flex-1" value={dateTo}   onChange={(e) => setDateTo(e.target.value)} />
          <button className="btn btn--primary w-full sm:w-auto" onClick={loadMoves} disabled={loading}>
            {loading ? <RefreshCw size={14} className="animate-spin" /> : 'Найти'}
          </button>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center text-[color:var(--color-text-faint)] text-sm">Загрузка…</div>
        ) : moves.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-[color:var(--color-text-faint)] text-sm">Нет движений за период</div>
        ) : (
          <div className="overflow-auto flex-1">
            <ResponsiveTable
              data={moves}
              keyFn={(m) => m.ID_KASSES_MOVE}
              rowState={(m) => (m.has_payout ? 'disabled' : null)}
              columns={[
                { label: 'Дата', primary: true, render: (m) => <span className="whitespace-nowrap text-xs">{m.DK_DATE}</span> },
                { label: 'Филиал', render: (m) => m.dep_name || '—' },
                {
                  label: 'Основание',
                  render: (m) => <span className="font-mono text-xs">{m.BASIS || '—'}</span>,
                },
                {
                  label: 'Сумма',
                  render: (m) => (
                    <span className="font-medium whitespace-nowrap">
                      {Number(m.SUMM).toLocaleString('ru-RU')} ₽
                    </span>
                  ),
                },
                {
                  label: '',
                  isAction: true,
                  render: (m) => (
                    <button
                      className="btn btn--primary text-xs px-2 py-1 disabled:opacity-50"
                      disabled={linking === m.ID_KASSES_MOVE}
                      onClick={() => handleLink(String(m.ID_KASSES_MOVE))}
                    >
                      {linking === m.ID_KASSES_MOVE
                        ? <RefreshCw size={12} className="animate-spin" />
                        : 'Привязать'}
                    </button>
                  ),
                },
              ]}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Notification journal ──────────────────────────────────────────
// Records every notification sent to an employee on a payout status change:
// recipient, channel, message text and the real delivery result.
const DELIVERY_META = {
  sent:    { label: 'Отправлено', cls: 'text-[color:var(--color-success)]', dot: 'bg-[color:var(--color-success)]' },
  failed:  { label: 'Ошибка',     cls: 'text-[color:var(--color-danger)]',  dot: 'bg-[color:var(--color-danger)]' },
  skipped: { label: 'Пропущено',  cls: 'text-[color:var(--color-muted-foreground)]', dot: 'bg-[color:var(--color-text-faint)]' },
};
const CHANNEL_META = {
  telegram: { label: 'Telegram', Icon: Send },
  vk:       { label: 'VK',       Icon: MessageCircle },
  push:     { label: 'Push',     Icon: Smartphone },
};

function NotificationJournal({ entries, open, onToggle, onRefresh }) {
  const fmtTime = (iso) => {
    try { return new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }); }
    catch { return iso; }
  };
  const failedCount = entries.filter((e) => e.delivery === 'failed').length;

  return (
    <div className="app-card overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2 font-medium">
          <Bell size={16} className="text-[color:var(--color-primary)]" />
          Журнал уведомлений
          <span className="text-xs text-[color:var(--color-muted-foreground)]">({entries.length})</span>
          {failedCount > 0 && (
            <span className="text-xs px-1.5 py-0.5 rounded-full bg-[color:var(--color-danger-muted)] text-[color:var(--color-danger)]">
              {failedCount} с ошибкой
            </span>
          )}
        </span>
        {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>

      {open && (
        <div className="border-t border-[color:var(--color-border)]">
          <div className="flex justify-end px-4 py-2">
            <button onClick={onRefresh} className="text-xs flex items-center gap-1 text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-text)]">
              <RefreshCw size={12} /> Обновить
            </button>
          </div>
          {entries.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-[color:var(--color-muted-foreground)]">
              Пока нет уведомлений. Они появятся здесь при одобрении/отклонении/выплате заявок.
            </div>
          ) : (
            <ul className="divide-y divide-[color:var(--color-border)] max-h-96 overflow-y-auto">
              {entries.map((e) => {
                const meta = DELIVERY_META[e.delivery] || DELIVERY_META.skipped;
                const channelMeta = CHANNEL_META[e.channel] || CHANNEL_META.push;
                const ChannelIcon = channelMeta.Icon;
                return (
                  <li key={e.id} className="px-4 py-2.5 text-sm flex items-start gap-3">
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${meta.dot}`} title={meta.label} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                        <span className="font-medium">{e.recipient_name || e.user_id}</span>
                        <span className="text-xs text-[color:var(--color-muted-foreground)]">·</span>
                        <span className="text-xs">{e.status}</span>
                        <span className="inline-flex items-center gap-1 text-xs text-[color:var(--color-muted-foreground)]">
                          <ChannelIcon size={11} />
                          {channelMeta.label}
                        </span>
                        <span className={`text-xs font-medium ${meta.cls}`}>{meta.label}</span>
                      </div>
                      <div className="text-[color:var(--color-muted-foreground)] whitespace-pre-line break-words mt-0.5">
                        {e.message}
                      </div>
                      {e.error && (
                        <div className="text-xs text-[color:var(--color-danger)] mt-0.5">Причина: {e.error}</div>
                      )}
                    </div>
                    <span className="shrink-0 text-xs text-[color:var(--color-muted-foreground)] whitespace-nowrap">{fmtTime(e.timestamp)}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// «Выплачено» — нормальный исход, и он же 548 строк из 555. Зелёный
// бейдж на каждой строке превращал ленту в сплошную зелёную колонку и
// обесценивал сам цвет: раз подсвечено всё, подсвечено ничего. Норма
// набрана нейтрально, цвет остаётся тем строкам, где он что-то значит —
// заявка ждёт решения или отклонена.
const STATUS_BADGE_CLASS = { 'Ожидает': 'badge--processing', 'Одобрено': 'badge--info', 'Выплачено': 'badge--neutral', 'Отклонено': 'badge--error' };
const STATUS_FLASH_COLOR = {
  'Ожидает': 'var(--color-text-faint)',
  'Одобрено': 'var(--color-primary-muted)',
  'Выплачено': 'var(--color-success-muted)',
  'Отклонено': 'var(--color-danger-muted)',
};
// Тот же порядок цветов, что у бейджей выше — используется точками
// статус-рейла ленты (payout-fui-rail), а не донатом на «Обзоре»
// (у него своя, независимая палитра STATUS_COLORS).
const STATUS_DOT_COLOR = {
  'Ожидает': 'var(--fui-processing)',
  'Одобрено': 'var(--color-primary)',
  // Норма — графитом. Рейка из 548 зелёных засечек читалась как
  // сплошная зелёная полоса вдоль всей ленты и не сообщала ничего,
  // кроме собственного присутствия.
  'Выплачено': 'color-mix(in srgb, var(--color-text) 22%, transparent)',
  'Отклонено': 'var(--color-danger)',
};

// «Сегодня»/«вчера» вместо голой даты — лента читается как поток
// событий, а не архив.
function dayLabel(value) {
  if (!value) return 'Без даты';
  const d = new Date(value.replace(' ', 'T'));
  if (Number.isNaN(d.getTime())) return 'Без даты';
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const that = new Date(d); that.setHours(0, 0, 0, 0);
  const diffDays = Math.round((today - that) / 86400000);
  const label = d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'long' });
  if (diffDays === 0) return `${label}, сегодня`;
  if (diffDays === 1) return `${label}, вчера`;
  return label;
}

// ── Одна запись ленты заявок ───────────────────────────────────────
function PayoutFeedItem({
  p, selected, onToggleSelect, moveMatch, findingMove, onFindMove, onQuickView,
  onEdit, onApprove, onReject, onMarkPaid, onRemove, flash,
}) {
  const initial = (p.name || '?').trim().charAt(0).toUpperCase();
  return (
    <div className="payout-feed__item">
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggleSelect}
        className="shrink-0"
        style={{ width: 15, height: 15, marginTop: '0.6rem' }}
      />
      <div className="relative grid place-items-center w-9 h-9 shrink-0 rounded-full bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] text-sm font-semibold mt-0.5">
        {initial}
        {/* Пунктирный ретикл вместо просто рамки — «Ожидает» читается как
            цель, взятая в прицел, а не декоративная обводка. */}
        {p.status === 'Ожидает' && <span className="payout-fui-reticle" />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 flex-wrap">
          {/* Радар-пинг вместо статичной точки — «Ожидает» это то, что
              требует внимания прямо сейчас, тот же сигнал «живого» статуса,
              что и «в эфире» на Прослушивании, только в форме радара. */}
          {p.status === 'Ожидает' && (
            <span className="fui-radar"><i /><i /><i /><b /></span>
          )}
          <span className="font-medium text-sm">{p.name}</span>
          <span
            className={`badge ${STATUS_BADGE_CLASS[p.status] || 'badge--neutral'} ${flash ? 'payout-feed__badge-flash' : ''}`}
            style={flash ? { '--flash-color': STATUS_FLASH_COLOR[p.status] || 'transparent' } : undefined}
          >
            {p.status}
          </span>
        </div>
        <div className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">
          {p.payout_type} · {p.method} · {formatDateTime(p.timestamp)}
        </div>
      </div>
      <div className="text-right shrink-0">
        {/* Сумма — якорь строки, поэтому набрана основным цветом текста
            и моношкалой. Фиолетовой она была у всех 555 строк подряд, и
            акцент переставал быть акцентом ровно там, где взгляд ищет
            деньги. */}
        <div className="payout-feed__sum">
          {Number(p.amount || 0).toLocaleString('ru-RU')} ₽
        </div>
      </div>
      <div className="flex items-center gap-1 shrink-0 ml-1">
        {findingMove ? (
          <RefreshCw size={13} className="animate-spin text-[color:var(--color-text-faint)]" />
        ) : moveMatch?.matched ? (
          <button onClick={onQuickView} title={`Движение привязано: ${moveMatch.move_id} — нажмите для просмотра`} className="p-1 rounded hover:bg-green-500/10">
            <LinkIcon size={14} className="text-green-500" />
          </button>
        ) : moveMatch != null ? (
          <button onClick={onFindMove} title="Кассовое движение не найдено — нажмите для повторного поиска" className="p-1 rounded">
            <Unlink size={14} className="text-amber-400 hover:text-amber-600" />
          </button>
        ) : (
          <button onClick={onFindMove} title="Найти кассовое движение" className="p-1 rounded">
            <Search size={13} className="text-[color:var(--color-text-faint)] hover:text-[color:var(--color-text-muted)]" />
          </button>
        )}
        <button onClick={onEdit} className="p-1 rounded text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-primary)]" title="Редактировать"><Pencil size={15} /></button>
        {p.status === 'Ожидает' && (
          <>
            <button onClick={onApprove} className="p-1 rounded text-[color:var(--color-success)] hover:bg-[color:var(--color-success)]/10" title="Одобрить"><CheckCircle size={16} /></button>
            <button onClick={onReject} className="p-1 rounded text-[color:var(--color-danger)] hover:bg-[color:var(--color-danger)]/10" title="Отказать"><XCircle size={16} /></button>
          </>
        )}
        {p.status === 'Одобрено' && (
          <button onClick={onMarkPaid} className="p-1 rounded text-[color:var(--color-primary)] hover:bg-[color:var(--color-primary)]/10" title="Отметить выплаченным"><Download size={16} /></button>
        )}
        <button onClick={onRemove} className="p-1 rounded text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-danger)]" title="Удалить"><Trash2 size={15} /></button>
      </div>
    </div>
  );
}

export default function Payouts() {
  const { user } = useAuth();
  const { toast } = useToast();
  const canManageDates = Boolean(
    user?.permissions?.includes('*') || user?.permissions?.includes(MANAGE_DATES_PERMISSION),
  );
  const emptyForm = {
    id: null,
    user_id: '',
    name: '',
    phone: '',
    card_number: '',
    bank: '',
    amount: '',
    payout_type: 'Аванс',
    method: '💳 На карту',
    status: 'Ожидает',
    sync_to_bot: false,
    notify_user: true,
    note: '',
    show_note_in_bot: false,
    timestamp: '',
    force_notify_cashier: false,
  };

  const [payouts, setPayouts] = useState([]);
  const [moveMatches, setMoveMatches] = useState({});
  const [moveMatchesLoading, setMoveMatchesLoading] = useState(false);
  const [findingMoves, setFindingMoves] = useState(new Set());
  const [bulkFinding, setBulkFinding] = useState(false);
  const [editingMoveDetails, setEditingMoveDetails] = useState(null);
  const [loadingMoveDetails, setLoadingMoveDetails] = useState(false);
  const [moveLinkPickerPayout, setMoveLinkPickerPayout] = useState(null);
  const [quickViewPayout, setQuickViewPayout] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [useFullName, setUseFullName] = useState(true);
  const [filters, setFilters] = useState({
    query: '',
    type: '',
    status: '',
    method: '',
    from: '',
    to: '',
    position: '',
  });
  const [showEditor, setShowEditor] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(new Set());
  // Подсвечивает бейдж только что изменённой заявки — сбрасывается по
  // истечении анимации, см. .payout-feed__badge-flash.
  const [flashId, setFlashId] = useState(null);
  const [activity, setActivity] = useState([]);
  const [showActivity, setShowActivity] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [dayFilter, setDayFilter] = useState(null);
  const [salaryContext, setSalaryContext] = useState(null);
  const [salaryContextLoading, setSalaryContextLoading] = useState(false);
  const [salaryMonth, setSalaryMonth] = useState(currentSalaryMonth);
  // Живые часы для телеметрии ленты и реальная задержка последнего
  // запроса payouts/ — не выдуманные цифры для красоты, а фактическое
  // состояние страницы.
  const [now, setNow] = useState(() => new Date());
  const [loadMs, setLoadMs] = useState(null);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    loadEmployees();
    loadActivity();
    window.refreshPage = load;
  }, []);
  useEffect(() => {
    load();
  }, [filters]);

  // Сбрасываем период на текущий месяц при каждом открытии формы — но не
  // при смене сотрудника внутри уже открытой формы, чтобы можно было
  // проверить несколько человек за один выбранный (например, прошлый) месяц.
  useEffect(() => {
    if (showEditor) setSalaryMonth(currentSalaryMonth());
  }, [showEditor]);

  // Общая ЗП / к выплате для выбранного в форме сотрудника и периода —
  // маршрутизация по должности происходит на бэкенде (payouts/salary-context).
  useEffect(() => {
    if (!showEditor || !form.user_id) {
      setSalaryContext(null);
      return undefined;
    }
    let cancelled = false;
    setSalaryContextLoading(true);
    api
      .get('payouts/salary-context', {
        params: { employee_id: form.user_id, year: salaryMonth.year, month: salaryMonth.month },
      })
      .then((res) => {
        if (!cancelled) setSalaryContext(res.data);
      })
      .catch(() => {
        if (!cancelled) setSalaryContext(null);
      })
      .finally(() => {
        if (!cancelled) setSalaryContextLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [showEditor, form.user_id, salaryMonth]);

  const employeesByPosition = useMemo(() => {
    const displayName = (e) => (useFullName ? e.full_name || e.name : e.name || e.full_name) || '';
    return groupEmployeesByPosition(employees, displayName);
  }, [employees, useFullName]);

  const employeeById = useMemo(() => {
    const map = {};
    for (const e of employees) map[String(e.id)] = e;
    return map;
  }, [employees]);

  const positionOptions = useMemo(
    () => employeesByPosition.map(([position]) => position),
    [employeesByPosition],
  );

  const totalSum = useMemo(() => payouts.reduce((s, p) => s + Number(p.amount || 0), 0), [payouts]);

  const statusSummary = useMemo(() => {
    const map = {};
    for (const p of payouts) {
      const key = p.status || '—';
      if (!map[key]) map[key] = { count: 0, sum: 0 };
      map[key].count += 1;
      map[key].sum += Number(p.amount || 0);
    }
    return map;
  }, [payouts]);

  const statusDonutData = useMemo(
    () => STATUS_OPTIONS.map((s) => ({ name: s, value: statusSummary[s]?.count || 0 })).filter((d) => d.value > 0),
    [statusSummary],
  );

  const typeDonutData = useMemo(() => {
    const map = {};
    for (const p of payouts) {
      const key = p.payout_type || 'Прочее';
      map[key] = (map[key] || 0) + Number(p.amount || 0);
    }
    return Object.entries(map).map(([name, value]) => ({ name, value }));
  }, [payouts]);

  const methodData = useMemo(() => {
    const map = {};
    for (const p of payouts) {
      const key = (p.method || 'Прочее').replace(/^[^\sа-яА-Я]+\s*/, '');
      map[key] = (map[key] || 0) + Number(p.amount || 0);
    }
    return Object.entries(map)
      .map(([name, sum]) => ({ name, sum }))
      .sort((a, b) => b.sum - a.sum);
  }, [payouts]);

  const timeData = useMemo(() => {
    const map = {};
    for (const p of payouts) {
      if (!p.timestamp) continue;
      const d = new Date(p.timestamp.replace(' ', 'T'));
      if (isNaN(d)) continue;
      const key = d.toISOString().slice(0, 10);
      map[key] = (map[key] || 0) + Number(p.amount || 0);
    }
    return Object.entries(map)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, sum]) => ({
        date,
        label: `${date.slice(8, 10)}.${date.slice(5, 7)}`,
        sum,
      }));
  }, [payouts]);

  const dayData = useMemo(() => {
    const sums = Array(7).fill(0);
    for (const p of payouts) {
      if (!p.timestamp) continue;
      const d = new Date(p.timestamp.replace(' ', 'T'));
      if (isNaN(d)) continue;
      sums[d.getDay()] += Number(p.amount || 0);
    }
    return DAY_NAMES.map((day, i) => ({ day, sum: sums[i] }));
  }, [payouts]);

  const employeeLeaderboard = useMemo(() => {
    const map = {};
    for (const p of payouts) {
      const key = p.name || 'Без имени';
      if (!map[key]) map[key] = { sum: 0, count: 0 };
      map[key].sum += Number(p.amount || 0);
      map[key].count += 1;
    }
    return Object.entries(map).sort(([, a], [, b]) => b.sum - a.sum);
  }, [payouts]);

  // Client-side day-of-week narrowing on top of the server-filtered `payouts` —
  // used only for chart drill-down, kept separate from `filters` (which round-trips to the API).
  const visiblePayouts = useMemo(() => {
    if (dayFilter == null) return payouts;
    return payouts.filter((p) => {
      if (!p.timestamp) return false;
      const d = new Date(p.timestamp.replace(' ', 'T'));
      return !isNaN(d) && d.getDay() === dayFilter;
    });
  }, [payouts, dayFilter]);

  // Лента: свежие заявки сверху, сгруппированы по дню.
  const feedGroups = useMemo(() => {
    const sorted = [...visiblePayouts].sort(
      (a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0)
    );
    const groups = [];
    for (const p of sorted) {
      const label = dayLabel(p.timestamp);
      const last = groups[groups.length - 1];
      if (last && last.label === label) last.items.push(p);
      else groups.push({ label, items: [p] });
    }
    return groups;
  }, [visiblePayouts]);

  // Chart-driven drill-down: clicking a chart segment applies the matching filter and jumps to the list.
  function selectStatus(name) {
    setFilters((f) => ({ ...f, status: f.status === name ? '' : name }));
    setActiveTab('list');
  }
  function selectType(name) {
    setFilters((f) => ({ ...f, type: f.type === name ? '' : name }));
    setActiveTab('list');
  }
  function selectMethod(name) {
    const raw = METHOD_RAW[name] || name;
    setFilters((f) => ({ ...f, method: f.method === raw ? '' : raw }));
    setActiveTab('list');
  }
  function selectEmployee(name) {
    setFilters((f) => ({ ...f, query: f.query === name ? '' : name }));
    setActiveTab('list');
  }
  function selectDay(i) {
    setDayFilter((prev) => (prev === i ? null : i));
    setActiveTab('list');
  }

  const mainTabs = [
    { key: 'overview', label: 'Обзор', icon: <BarChart3 size={14} /> },
    { key: 'list', label: 'Заявки', icon: <TrendingUp size={14} />, badge: payouts.length },
  ];

  async function loadEmployees() {
    try {
      const res = await api.get('employees/', { params: { archived: false } });
      setEmployees(res.data.filter((e) => e.status !== 'inactive'));
    } catch (err) {
      console.error(err);
    }
  }

  async function loadActivity() {
    try {
      const res = await api.get('payouts/activity', { params: { limit: 100 } });
      setActivity(res.data || []);
    } catch (err) {
      console.error(err);
    }
  }

  async function load() {
    setLoading(true);
    setSelected(new Set());
    const t0 = performance.now();
    try {
      const params = {
        payout_type: filters.type || undefined,
        status: filters.status || undefined,
        method: filters.method || undefined,
        from_date: filters.from || undefined,
        to_date: filters.to || undefined,
      };
      const res = await api.get('payouts/', { params });
      setLoadMs(Math.round(performance.now() - t0));
      let list = res.data;
      if (filters.query) {
        const q = filters.query.toLowerCase();
        list = list.filter((p) => p.name?.toLowerCase().includes(q));
      }
      if (filters.position) {
        list = list.filter((p) => {
          const position = employeeById[String(p.user_id)]?.position || 'Без должности';
          return position === filters.position;
        });
      }
      setPayouts(list);
      if (params.from_date || params.to_date) {
        loadMoveMatches(params.from_date, params.to_date);
      } else {
        // Build matches from cash_move_id stored on each payout (no Firebird query needed)
        const map = {};
        for (const p of list) {
          if (p.cash_move_id) {
            map[p.id] = { payout_id: p.id, matched: true, move_id: p.cash_move_id };
          }
        }
        setMoveMatches(map);
      }
    } catch (err) {
      console.error(err);
      toast('Ошибка загрузки выплат', 'error');
    } finally {
      setLoading(false);
    }
  }

  async function loadMoveMatches(fromDate, toDate) {
    setMoveMatchesLoading(true);
    try {
      const params = {};
      if (fromDate) params.date_from = fromDate;
      if (toDate)   params.date_to   = toDate;
      const res = await api.get('cash-moves/match-payouts', { params });
      const map = {};
      for (const item of res.data || []) map[item.payout_id] = item;
      setMoveMatches(map);
    } catch {
      // Firebird may be unavailable — silently ignore
    } finally {
      setMoveMatchesLoading(false);
    }
  }

  async function findMoveForPayout(payoutId) {
    setFindingMoves((prev) => new Set([...prev, payoutId]));
    try {
      const res = await api.post(`payouts/${payoutId}/find-move`);
      setMoveMatches((prev) => ({ ...prev, [payoutId]: res.data }));
      if (res.data.matched) {
        setPayouts((prev) => prev.map((p) =>
          p.id === payoutId ? { ...p, cash_move_id: res.data.move_id } : p
        ));
        toast('Движение найдено и привязано', 'success');
      } else {
        toast('Совпадение не найдено', 'warning');
      }
    } catch {
      toast('Ошибка поиска движения', 'error');
    } finally {
      setFindingMoves((prev) => { const s = new Set(prev); s.delete(payoutId); return s; });
    }
  }

  async function bulkFindMoves() {
    if (selected.size === 0) return;
    setBulkFinding(true);
    try {
      const res = await api.post('payouts/bulk-find-moves', { ids: [...selected] });
      const updated = {};
      for (const item of res.data || []) updated[item.payout_id] = item;
      setMoveMatches((prev) => ({ ...prev, ...updated }));
      const found = (res.data || []).filter((r) => r.matched).length;
      toast(`Найдено движений: ${found} из ${selected.size}`, found > 0 ? 'success' : 'warning');
    } catch {
      toast('Ошибка поиска движений', 'error');
    } finally {
      setBulkFinding(false);
    }
  }

  function resetFilters() {
    setFilters({ query: '', type: '', status: '', method: '', from: '', to: '', position: '' });
    load();
  }

  async function updateStatus(id, status) {
    try {
      let endpoint = '';
      switch (status) {
        case 'Одобрено':
          endpoint = `payouts/${id}/approve`;
          break;
        case 'Отклонено':
          endpoint = `payouts/${id}/reject`;
          break;
        case 'Выплачено':
          endpoint = `payouts/${id}/mark_paid`;
          break;
        default:
          return;
      }
      await api.post(endpoint);
      toast('Статус обновлён', 'success');
      setFlashId(id);
      setTimeout(() => setFlashId((cur) => (cur === id ? null : cur)), 700);
      load();
      loadActivity();
    } catch (err) {
      console.error(err);
      toast('Ошибка обновления статуса', 'error');
    }
  }

  async function remove(id) {
    if (!window.confirm('Удалить выплату?')) return;
    try {
      await api.delete(`payouts/${id}`);
      toast('Выплата удалена', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка удаления', 'error');
    }
  }

  function toggleSelect(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selected.size === visiblePayouts.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(visiblePayouts.map((p) => p.id)));
    }
  }

  async function bulkDelete() {
    if (selected.size === 0) return;
    if (!window.confirm(`Удалить ${selected.size} выплат?`)) return;
    let deleted = 0;
    let failed = 0;
    for (const id of selected) {
      try {
        await api.delete(`payouts/${id}`);
        deleted++;
      } catch (err) {
        console.error(err);
        failed++;
      }
    }
    setSelected(new Set());
    if (failed > 0) {
      toast(`Удалено: ${deleted}, ошибок: ${failed}`, 'warning');
    } else {
      toast(`Удалено: ${deleted}`, 'success');
    }
    load();
  }

  async function bulkSetStatus(status) {
    if (selected.size === 0 || !status) return;
    try {
      const res = await api.post('payouts/bulk-status', { ids: [...selected], status });
      toast(`Статус «${status}» установлен: ${res.data.updated} выплат`, 'success');
      setSelected(new Set());
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка массового изменения статуса', 'error');
    }
  }

  function openCreate() {
    setForm({
      ...emptyForm,
      timestamp: canManageDates ? toInputTimestamp(new Date()) : '',
    });
    setShowEditor(true);
  }

  function openEdit(p) {
    setForm({
      ...emptyForm,
      ...p,
      timestamp: canManageDates ? toInputTimestamp(p.timestamp) : '',
      notify_user: true,
      note: p.note || '',
      show_note_in_bot: p.show_note_in_bot || false,
      force_notify_cashier: Boolean(p.force_notify_cashier),
    });
    setEditingMoveDetails(null);
    setMoveLinkPickerPayout(null);
    setShowEditor(true);
    if (p.cash_move_id) fetchMoveDetails(p.cash_move_id);
  }

  async function fetchMoveDetails(moveId) {
    setLoadingMoveDetails(true);
    try {
      const res = await api.get(`cash-moves/by-id/${moveId}`);
      setEditingMoveDetails(res.data);
    } catch {
      setEditingMoveDetails(null);
    } finally {
      setLoadingMoveDetails(false);
    }
  }

  async function unlinkMove(payoutId) {
    const res = await api.delete(`payouts/${payoutId}/move-link`);
    setPayouts((prev) => prev.map((p) => (p.id === payoutId ? res.data : p)));
    setForm((prev) => ({ ...prev, cash_move_id: null }));
    setEditingMoveDetails(null);
    setQuickViewPayout(null);
    setMoveMatches((prev) => ({ ...prev, [payoutId]: { payout_id: payoutId, matched: false, move_id: null } }));
    toast('Движение отвязано', 'success');
  }

  async function linkMove(payoutId, moveId) {
    try {
      const res = await api.post(`payouts/${payoutId}/link-move`, { move_id: moveId });
      setPayouts((prev) => prev.map((p) => (p.id === payoutId ? res.data : p)));
      setForm((prev) => ({ ...prev, cash_move_id: moveId }));
      setMoveMatches((prev) => ({ ...prev, [payoutId]: { payout_id: payoutId, matched: true, move_id: moveId } }));
      toast('Движение привязано', 'success');
      fetchMoveDetails(moveId);
    } catch {
      toast('Ошибка привязки', 'error');
    }
  }

  async function saveForm() {
    const amount = Number(form.amount || 0);
    if (!form.user_id || !amount || amount > MAX_AMOUNT) {
      toast('Неверные данные', 'warning');
      return;
    }
    const payload = { ...form, amount };
    if (canManageDates && form.timestamp) {
      payload.timestamp = toPayloadTimestamp(form.timestamp);
    } else {
      delete payload.timestamp;
    }
    try {
      if (form.id) {
        await api.put(`payouts/${form.id}`, payload);
      } else {
        await api.post('payouts/', payload);
      }
      setShowEditor(false);
      setForm(emptyForm);
      toast('Выплата сохранена', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка сохранения', 'error');
    }
  }

  function handleSelect(id) {
    const emp = employees.find((e) => String(e.id) === String(id));
    if (emp) {
      setForm((f) => ({
        ...f,
        user_id: emp.id,
        name: useFullName ? emp.full_name || emp.name : emp.name || emp.full_name,
        phone: emp.phone || '',
        bank: emp.bank || emp.card_number || '',
        card_number: emp.card_number || '',
      }));
    }
  }

  function exportPdf() {
    const q = new URLSearchParams({
      payout_type: filters.type,
      status: filters.status,
      method: filters.method,
      date_from: filters.from,
      date_to: filters.to,
    });
    window.open(`/api/payouts/export.pdf?${q.toString()}`, '_blank');
  }

  async function checkTelegram() {
    try {
      await api.get('payouts/unconfirmed');
      load();
      toast('Заявки обновлены', 'success');
    } catch (err) {
      console.error(err);
      toast('Ошибка обновления', 'error');
    }
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <TopProgressBar active={loading} />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <span className="ui-eyebrow mb-3">
            {payouts.length ? `Заявок в списке: ${payouts.length}` : 'Заявок нет'}
          </span>
          <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)] flex items-center gap-2">
            Выплаты
            <button
              onClick={checkTelegram}
              title="Проверить бот"
              className="ui-tap-44 ml-2 text-blue-600 hover:text-blue-800"
            >
              <RefreshCw size={18} />
            </button>
          </h2>
        </div>
        {/* HUD-кластер: не декоративные цифры — оператор и задержка
            берутся из реального состояния (useAuth, время последнего
            payouts/ запроса). */}
        <div className="payout-fui-hud">
          <div>УЗЕЛ: <b>ВЫПЛАТЫ</b></div>
          <div>ОПЕРАТОР: <b>{(user?.display_name || user?.login || '—').toUpperCase()}</b></div>
          <div>ЗАДЕРЖКА: <b>{loadMs != null ? `${loadMs}ms` : '—'}</b></div>
        </div>
      </div>

      <NotificationJournal
        entries={activity}
        open={showActivity}
        onToggle={() => setShowActivity((v) => !v)}
        onRefresh={loadActivity}
      />

      <Tabs tabs={mainTabs} active={activeTab} onChange={setActiveTab} />

      {/* ── Обзор ─────────────────────────────────────────────── */}
      {activeTab === 'overview' && (
        <div className="space-y-5">
          {loading ? (
            <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]">
              <RefreshCw size={24} className="animate-spin mx-auto mb-2" />
              Загрузка…
            </div>
          ) : (
            <>
              {/* Сумма-якорь и конвейер стадий вместо четырёх равных
                  карточек-светофоров. Порядок стадий — путь заявки. */}
              <div className="pay-flow">
                <div className="pay-flow__total">
                  <span className="pay-flow__k">Общая сумма</span>
                  <span className="pay-flow__n">{fmtMoneyShort(totalSum)}</span>
                  <span className="pay-flow__m">{payouts.length} заявок за период</span>
                </div>
                <div className="pay-flow__stages">
                  {PAYOUT_STAGES.map((st) => {
                    const count = statusSummary[st.key]?.count || 0;
                    return (
                      <button
                        key={st.key}
                        type="button"
                        style={{ '--stage': st.ink }}
                        className={`pay-flow__stage fui-press ${count > 0 ? 'pay-flow__stage--live' : 'pay-flow__stage--idle'}`}
                        onClick={() => selectStatus(st.key)}
                      >
                        <span className="pay-flow__stage-k">{st.key}</span>
                        <span className="pay-flow__stage-v">{count}</span>
                        <span className="pay-flow__stage-m">{fmtMoneyShort(statusSummary[st.key]?.sum || 0)}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {timeData.length > 0 && (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  <div className="app-card p-5 lg:col-span-2">
                    <div className="text-sm font-semibold mb-4 flex items-center gap-2">
                      <TrendingUp size={15} className="text-[color:var(--color-primary)]" />
                      Динамика выплат
                    </div>
                    <ResponsiveContainer width="100%" height={220}>
                      <AreaChart data={timeData} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
                        <defs>
                          <linearGradient id="payoutGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="var(--color-primary)" stopOpacity={0.35} />
                            <stop offset="95%" stopColor="var(--color-primary)" stopOpacity={0.02} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid vertical={false} stroke="var(--fui-edge)" />
                        {/* Подписи через одну и без наклона: тридцать дат
                            подряд слипались в «01.1216.1204.0121.01» —
                            строку, которую нельзя прочитать. */}
                        <XAxis
                          dataKey="label"
                          tick={{ fontSize: 9.5, fill: 'var(--color-text-faint)' }}
                          tickLine={false}
                          axisLine={{ stroke: 'var(--fui-edge)' }}
                          interval="preserveStartEnd"
                          minTickGap={28}
                        />
                        <YAxis tickFormatter={fmtMoneyShort} tick={{ fontSize: 9.5, fill: 'var(--color-text-faint)' }} tickLine={false} axisLine={false} width={78} />
                        <Tooltip content={<CustomTooltip />} cursor={{ stroke: 'var(--fui-edge-strong)', strokeWidth: 1 }} />
                        <Area
                          type="monotone"
                          dataKey="sum"
                          stroke="var(--color-primary)"
                          strokeWidth={1.5}
                          fill="url(#payoutGrad)"
                          dot={false}
                          activeDot={{ r: 3.5, strokeWidth: 2, stroke: 'var(--color-surface)' }}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                  {/* Шкала долей вместо кольца. На разбивке 548 / 5 / 1 / 1
                      сектор в 0,2% физически не виден, а легенда кольца
                      резала названия до «Ожида…» и «Одобре…». Полоса
                      показывает ту же пропорцию честно, а проценты стоят
                      колонкой и сравниваются. */}
                  <div className="app-card p-5">
                    <div className="mb-4 flex items-center gap-2 text-sm font-semibold">
                      <BarChart3 size={15} className="text-[color:var(--color-primary)]" />
                      Статусы
                    </div>
                    <div className="fui-mixbar mb-4">
                      {statusDonutData.map((d) => (
                        <span
                          key={d.name}
                          title={`${d.name}: ${d.value}`}
                          style={{ width: `${(d.value / Math.max(1, payouts.length)) * 100}%`, background: STATUS_COLORS[d.name] || 'var(--color-text-muted)' }}
                        />
                      ))}
                    </div>
                    <div className="fui-breakdown">
                      {statusDonutData.map((d) => (
                        <button
                          key={d.name}
                          type="button"
                          onClick={() => selectStatus(d.name)}
                          style={{ '--cat': STATUS_COLORS[d.name] || 'var(--color-text-muted)' }}
                          className={`fui-breakdown__row fui-press ${filters.status === d.name ? 'is-on' : ''}`}
                        >
                          <span className="fui-breakdown__sw" />
                          <span className="fui-breakdown__k">{d.name}</span>
                          <span className="fui-breakdown__v">{d.value}</span>
                          <span className="fui-breakdown__p">{payouts.length ? `${((d.value / payouts.length) * 100).toFixed(d.value / payouts.length < 0.01 ? 1 : 0)}%` : '—'}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <EmployeeLeaderboard data={employeeLeaderboard} total={totalSum} activeName={filters.query || null} onSelect={selectEmployee} />
                <PayoutDayHeatmap data={dayData} activeDay={dayFilter} onSelect={selectDay} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <StatusDonut
                  data={typeDonutData.map((d) => ({ name: d.name, value: d.value }))}
                  total={totalSum}
                  title="По типам"
                  icon={Layers}
                  formatValue={fmtMoneyShort}
                  tooltipLabel="Сумма"
                  activeName={filters.type || null}
                  onSelect={selectType}
                />
                {methodData.length > 0 && (
                  <div className="app-card p-5">
                    <div className="text-sm font-semibold mb-4 flex items-center gap-2">
                      <BarChart3 size={15} className="text-[color:var(--color-primary)]" />
                      По способам выплаты
                    </div>
                    <ResponsiveContainer width="100%" height={Math.max(120, methodData.length * 48)}>
                      <BarChart
                        data={methodData}
                        layout="vertical"
                        margin={{ top: 0, right: 12, bottom: 0, left: 0 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--color-border)" />
                        <XAxis type="number" tickFormatter={fmtMoneyShort} tick={{ fontSize: 10, fill: 'var(--color-muted-foreground)' }} tickLine={false} axisLine={false} />
                        <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: 'var(--color-muted-foreground)' }} tickLine={false} width={100} />
                        <Tooltip formatter={(v) => [fmtMoneyShort(v), 'Сумма']} />
                        <Bar dataKey="sum" radius={[0, 4, 4, 0]} onClick={(entry) => selectMethod(entry.name)} cursor="pointer">
                          {methodData.map((d, i) => (
                            <Cell key={d.name} fill={CHART_COLORS[i % CHART_COLORS.length]} opacity={filters.method && METHOD_RAW[d.name] !== filters.method ? 0.35 : 1} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Заявки ────────────────────────────────────────────── */}
      {activeTab === 'list' && (
        <>
      <div className="payout-fui-readout">
        <span>SYS://payouts.stream</span><span className="sep">·</span>
        <span>ЗАПИСЕЙ: <b>{payouts.length}</b></span><span className="sep">·</span>
        <span>ОЖИДАЕТ: <b style={{ color: 'var(--color-warning)' }}>{statusSummary['Ожидает']?.count || 0}</b></span><span className="sep">·</span>
        <span>СИНХРОНИЗАЦИЯ: <b style={{ color: loading ? 'var(--color-warning)' : 'var(--color-success)' }}>{loading ? 'ИДЁТ…' : 'OK'}</b></span><span className="sep">·</span>
        <span>{now.toLocaleDateString('ru-RU')} {now.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}:<span className="fui-cursor">{String(now.getSeconds()).padStart(2, '0')}</span></span>
      </div>
      {timeData.length > 1 && (
        <div className="payout-fui-ticker">
          <span className="payout-fui-ticker__label">Активность, {Math.min(7, timeData.length)} дн</span>
          <div className="payout-fui-spark">
            {timeData.slice(-7).map((d) => {
              const max = Math.max(...timeData.slice(-7).map((x) => x.sum), 1);
              return <i key={d.date} style={{ height: `${Math.max(4, (d.sum / max) * 30)}px`, opacity: 0.4 + (d.sum / max) * 0.6 }} title={`${d.label}: ${fmtMoneyShort(d.sum)}`} />;
            })}
          </div>
          <span className="payout-fui-ticker__label" style={{ marginLeft: 'auto' }}>{payouts.length} заявок · {fmtMoneyShort(totalSum)}</span>
        </div>
      )}
      {dayFilter != null && (
        <div className="flex items-center gap-2 text-sm">
          <span className="text-[color:var(--color-muted-foreground)]">Фильтр из графика:</span>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] font-medium">
            {DAY_NAMES[dayFilter]}
            <button onClick={() => setDayFilter(null)} className="hover:opacity-70"><X size={12} /></button>
          </span>
        </div>
      )}
      {/* Фильтры решёткой, а не переносящимся рядом: поля .input тянутся
          на всю ширину, поэтому каждое вставало отдельной строкой — шесть
          контролов в столбик занимали 380px до первой строки данных. */}
      <div className="pay-filters">
        <input
          className="input pay-filters__q"
          placeholder="Поиск по ФИО"
          value={filters.query}
          onChange={(e) => setFilters({ ...filters, query: e.target.value })}
        />
        <select
          className="input"
          value={filters.type}
          onChange={(e) => setFilters({ ...filters, type: e.target.value })}
        >
          <option value="">Все типы</option>
          <option value="Аванс">Аванс</option>
          <option value="Зарплата">Зарплата</option>
        </select>
        <select
          className="input"
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        >
          <option value="">Все статусы</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          className="input"
          value={filters.method}
          onChange={(e) => setFilters({ ...filters, method: e.target.value })}
        >
          <option value="">Все способы</option>
          <option value="💳 На карту">На карту</option>
          <option value="🏦 Из кассы">Из кассы</option>
          <option value="🤝 Наличными">Наличными</option>
        </select>
        <select
          className="input"
          value={filters.position}
          onChange={(e) => setFilters({ ...filters, position: e.target.value })}
        >
          <option value="">Все должности</option>
          {positionOptions.map((position) => (
            <option key={position} value={position}>
              {position}
            </option>
          ))}
        </select>
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
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button className="btn btn--primary" onClick={openCreate}>
          Новая заявка
        </button>
        <button className="btn btn--secondary" onClick={resetFilters}>
          Сбросить фильтры
        </button>
      </div>

      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 bg-[color:var(--color-primary-muted)] p-3 rounded border border-[color:var(--color-primary)]/30">
          <span className="text-sm text-[color:var(--color-primary)] font-medium">
            Выбрано: <strong>{selected.size}</strong>
          </span>
          <div className="flex items-center gap-2">
            <select
              className="border border-[color:var(--color-primary)]/40 rounded px-2 py-1 text-sm bg-[color:var(--color-surface)]"
              defaultValue=""
              onChange={(e) => { if (e.target.value) { bulkSetStatus(e.target.value); e.target.value = ''; } }}
            >
              <option value="" disabled>Установить статус…</option>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <button
            className="btn text-sm px-3 py-1 flex items-center gap-1.5 disabled:opacity-50"
            onClick={bulkFindMoves}
            disabled={bulkFinding}
            title="Найти кассовые движения для выбранных выплат"
          >
            {bulkFinding
              ? <RefreshCw size={14} className="animate-spin" />
              : <Search size={14} />}
            Найти движения
          </button>
          <button
            className="btn bg-red-600 hover:bg-red-700 text-white text-sm px-3 py-1"
            onClick={bulkDelete}
          >
            <Trash2 size={14} className="inline mr-1" />
            Удалить
          </button>
          <button
            className="text-sm text-[color:var(--color-text-muted)] hover:text-[color:var(--color-text)] underline"
            onClick={() => setSelected(new Set())}
          >
            Снять выделение
          </button>
        </div>
      )}

      {loading ? (
        <div className="ui-shell"><div className="ui-core" style={{ padding: '1.25rem 1.5rem' }}>
          <SkeletonTable rows={6} cols={3} />
        </div></div>
      ) : (
        <>
          {visiblePayouts.length > 0 && (
            <label className="flex items-center gap-2 text-sm text-[color:var(--color-muted-foreground)]">
              <input
                type="checkbox"
                checked={selected.size === visiblePayouts.length}
                onChange={toggleSelectAll}
              />
              Выбрать все ({visiblePayouts.length})
            </label>
          )}
          {visiblePayouts.length === 0 ? (
            <div className="app-card p-10 text-center text-[color:var(--color-muted-foreground)]">
              Заявок нет — новые заявки приходят из бота и появляются здесь сразу.
            </div>
          ) : (
            <div className="payout-fui-split payout-fui-dotgrid">
              <div className="payout-fui-rail">
                {visiblePayouts.map((p) => (
                  <i key={p.id} style={{ background: STATUS_DOT_COLOR[p.status] || 'var(--color-border)' }} title={`${p.name} · ${p.status}`} />
                ))}
              </div>
              <div className="ui-shell payout-fui-frame" style={{ flex: 1 }}>
                <span className="payout-fui-corner-tr" />
                <span className="payout-fui-corner-bl" />
                <span className="payout-fui-scan" />
                <div className="ui-core" style={{ padding: '1.1rem 1.5rem', position: 'relative' }}>
                  {feedGroups.map((g) => (
                    <div key={g.label}>
                      <div className="payout-feed__day">{g.label}</div>
                      {g.items.map((p) => (
                        <PayoutFeedItem
                          key={p.id}
                          p={p}
                          selected={selected.has(p.id)}
                          onToggleSelect={() => toggleSelect(p.id)}
                          moveMatch={moveMatches[p.id]}
                          findingMove={findingMoves.has(p.id) || (moveMatchesLoading && moveMatches[p.id] == null)}
                          onFindMove={() => findMoveForPayout(p.id)}
                          onQuickView={() => setQuickViewPayout(p)}
                          onEdit={() => openEdit(p)}
                          onApprove={() => updateStatus(p.id, 'Одобрено')}
                          onReject={() => updateStatus(p.id, 'Отклонено')}
                          onMarkPaid={() => updateStatus(p.id, 'Выплачено')}
                          onRemove={() => remove(p.id)}
                          flash={flashId === p.id}
                        />
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}

      <div className="flex gap-3 items-center">
        <button onClick={exportPdf} className="btn bg-green-600 hover:bg-green-700 flex items-center gap-1">
          <Download size={16} /> PDF
        </button>
      </div>
        </>
      )}

      {showEditor && (
        <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setShowEditor(false)}>
          <div className="modal-card max-w-lg">
            <h2 className="text-xl font-semibold">
              {form.id ? 'Редактирование' : 'Новая выплата'}
            </h2>
            <label className="flex items-center gap-1 text-sm">
              <input
                type="checkbox"
                checked={useFullName}
                onChange={(e) => setUseFullName(e.target.checked)}
              />
              Использовать ФИО
            </label>
            <select
              className="modal-control"
              value={form.user_id}
              onChange={(e) => handleSelect(e.target.value)}
            >
              <option value="">Сотрудник</option>
              {employeesByPosition.map(([position, list]) => (
                <optgroup key={position} label={position}>
                  {list.map((e) => (
                    <option key={e.id} value={e.id}>
                      {useFullName ? e.full_name || e.name : e.name || e.full_name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            {form.user_id && (
              <label className="flex items-center gap-2 text-sm">
                <span className="text-[color:var(--color-text-muted)] flex-shrink-0">Месяц ЗП:</span>
                <select
                  className="modal-control"
                  value={`${salaryMonth.year}-${salaryMonth.month}`}
                  onChange={(e) => {
                    const [year, month] = e.target.value.split('-').map(Number);
                    setSalaryMonth({ year, month });
                  }}
                >
                  {salaryMonthOptions().map(({ year, month }) => (
                    <option key={`${year}-${month}`} value={`${year}-${month}`}>
                      {MONTH_LABELS[month - 1]} {year}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {form.user_id && (
              <div className="text-sm border rounded-md p-2 bg-[color:var(--color-bg-subtle)] space-y-0.5">
                {salaryContextLoading ? (
                  <div className="text-[color:var(--color-text-muted)]">Загрузка данных о зарплате…</div>
                ) : salaryContext?.found ? (
                  <>
                    <div className="flex justify-between">
                      <span className="text-[color:var(--color-text-muted)]">Общая ЗП</span>
                      <span className="font-medium">
                        {salaryContext.total_salary != null
                          ? `${salaryContext.total_salary.toLocaleString('ru-RU')} ₽`
                          : '—'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[color:var(--color-text-muted)]">Аванс с посл. ЗП</span>
                      <span className="font-medium">
                        {salaryContext.advances_since_last_salary.toLocaleString('ru-RU')} ₽
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[color:var(--color-text-muted)]">К выплате</span>
                      <span className="font-semibold">
                        {salaryContext.to_pay != null
                          ? `${salaryContext.to_pay.toLocaleString('ru-RU')} ₽`
                          : '—'}
                      </span>
                    </div>
                    {salaryContext.note && (
                      <div className="text-xs text-amber-600 pt-1">{salaryContext.note}</div>
                    )}
                  </>
                ) : (
                  <div className="text-[color:var(--color-text-muted)]">Нет данных о зарплате</div>
                )}
              </div>
            )}
            <div className="text-sm text-[color:var(--color-text-muted)]">
              Карта: <span className="font-medium">{form.card_number || '—'}</span>
            </div>
            <div className="text-sm text-[color:var(--color-text-muted)]">
              Банк: <span className="font-medium">{form.bank || '—'}</span>
            </div>
            <input
              className="modal-control"
              placeholder="Сумма"
              type="number"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
            <select
              className="modal-control"
              value={form.payout_type}
              onChange={(e) => setForm({ ...form, payout_type: e.target.value })}
            >
              <option value="Аванс">Аванс</option>
              <option value="Зарплата">Зарплата</option>
            </select>
            <select
              className="modal-control"
              value={form.method}
              onChange={(e) => setForm({ ...form, method: e.target.value })}
            >
              <option value="💳 На карту">На карту</option>
              <option value="🏦 Из кассы">Из кассы</option>
              <option value="🤝 Наличными">Наличными</option>
            </select>
            {canManageDates && (
              <div className="w-full">
                <label className="block text-sm font-medium text-[color:var(--color-text)] mb-1">
                  Дата выплаты
                </label>
                <input
                  type="datetime-local"
                  step="1"
                  className="modal-control"
                  value={form.timestamp}
                  onChange={(e) => setForm({ ...form, timestamp: e.target.value })}
                />
              </div>
            )}
            {form.id && (
              <select
                className="modal-control"
                value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            )}
            {form.id && (
              <label className="flex items-center gap-1 text-sm">
                <input
                  type="checkbox"
                  checked={form.notify_user}
                  onChange={(e) => setForm({ ...form, notify_user: e.target.checked })
                  }
                />
                Уведомить сотрудника
              </label>
            )}
            <textarea
              className="modal-control"
              placeholder="Примечание"
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
            <label className="flex items-center gap-1 text-sm">
              <input
                type="checkbox"
                checked={form.show_note_in_bot}
                onChange={(e) => setForm({ ...form, show_note_in_bot: e.target.checked })
                }
              />
              Показывать примечание в боте
            </label>
            <label className="flex items-center gap-1 text-sm">
              <input
                type="checkbox"
                checked={form.force_notify_cashier}
                onChange={(e) =>
                  setForm({ ...form, force_notify_cashier: e.target.checked })
                }
              />
              Всегда уведомлять кассира
            </label>
            <label className="flex items-center gap-1 text-sm">
              <input
                type="checkbox"
                checked={form.sync_to_bot}
                onChange={(e) => setForm({ ...form, sync_to_bot: e.target.checked })
                }
              />
              Отразить в боте
            </label>
            {/* Linked movement block (edit mode only) */}
            {form.id && (
              <div className="rounded-lg border border-[color:var(--color-border)] bg-[color:var(--color-bg-subtle)] p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium flex items-center gap-1.5">
                    <LinkIcon size={13} className={form.cash_move_id ? 'text-green-500' : 'text-[color:var(--color-text-faint)]'} />
                    Кассовое движение
                  </span>
                  <div className="flex items-center gap-2">
                    {form.cash_move_id && (
                      <button
                        className="text-xs text-red-500 hover:text-red-700 underline"
                        onClick={async () => {
                          try { await unlinkMove(form.id); }
                          catch { toast('Ошибка отвязки', 'error'); }
                        }}
                      >
                        Отвязать
                      </button>
                    )}
                    <button
                      className="text-xs text-blue-500 hover:text-blue-700 underline"
                      onClick={() => setMoveLinkPickerPayout({ id: form.id, timestamp: form.timestamp })}
                    >
                      {form.cash_move_id ? 'Изменить' : 'Привязать'}
                    </button>
                  </div>
                </div>
                {form.cash_move_id ? (
                  loadingMoveDetails ? (
                    <div className="text-xs text-[color:var(--color-text-faint)] flex items-center gap-1">
                      <RefreshCw size={11} className="animate-spin" /> Загрузка…
                    </div>
                  ) : editingMoveDetails ? (
                    <div className="text-sm space-y-1">
                      <div className="flex justify-between">
                        <span className="text-[color:var(--color-text-muted)]">Дата</span>
                        <span>{editingMoveDetails.DK_DATE || '—'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[color:var(--color-text-muted)]">Сумма</span>
                        <span className="font-semibold text-blue-700">
                          {Number(editingMoveDetails.SUMM).toLocaleString('ru-RU')} ₽
                        </span>
                      </div>
                      {editingMoveDetails.dep_name && (
                        <div className="flex justify-between">
                          <span className="text-[color:var(--color-text-muted)]">Филиал</span>
                          <span>{editingMoveDetails.dep_name}</span>
                        </div>
                      )}
                      {editingMoveDetails.BASIS && (
                        <div className="flex justify-between gap-4">
                          <span className="text-[color:var(--color-text-muted)] shrink-0">Основание</span>
                          <span className="font-mono text-xs text-right truncate">{editingMoveDetails.BASIS}</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-xs text-[color:var(--color-text-faint)]">ID: {form.cash_move_id}</div>
                  )
                ) : (
                  <div className="text-xs text-[color:var(--color-text-faint)] italic">Движение не привязано</div>
                )}
              </div>
            )}

            <div className="flex justify-end space-x-2 pt-2">
              <button
                className="btn btn--secondary"
                onClick={() => {
                  setShowEditor(false);
                  setForm(emptyForm);
                }}
              >
                Отмена
              </button>
              <button className="btn" onClick={saveForm}>
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}

      {moveLinkPickerPayout && (
        <MovementPickerModal
          payout={moveLinkPickerPayout}
          onLink={(moveId) => linkMove(moveLinkPickerPayout.id, moveId)}
          onClose={() => setMoveLinkPickerPayout(null)}
        />
      )}

      {quickViewPayout && (
        <MovementQuickViewModal
          payout={quickViewPayout}
          onUnlink={() => unlinkMove(quickViewPayout.id)}
          onChangeMove={() => setMoveLinkPickerPayout({ id: quickViewPayout.id, timestamp: quickViewPayout.timestamp })}
          onClose={() => setQuickViewPayout(null)}
        />
      )}
    </div>
  );
}
