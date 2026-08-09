import { useEffect, useState } from 'react';
import api from '../../api';
import { Section } from './shared.jsx';

export default function SettingsAiUsage() {
  return (
    <div className="space-y-6 max-w-3xl">
      <Section title="Расход AI — токены и рубли">
        <p className="text-sm text-[color:var(--color-muted-foreground)] -mt-2">
          Общий расход по счёту — цифры приходят напрямую от Polza.ai в реальном времени,
          локально ничего не хранится.
        </p>
        <LlmUsagePanel />
      </Section>

      <Section title="Расход AI по сотрудникам">
        <p className="text-sm text-[color:var(--color-muted-foreground)] -mt-2">
          Разбивка по сотрудникам, обращавшимся к базе знаний через Telegram-бота. Polza не знает,
          какой сотрудник сделал запрос — эти данные считаются и хранятся у нас, при каждом обращении.
        </p>
        <EmployeeLlmUsagePanel />
      </Section>
    </div>
  );
}

function LlmUsagePanel() {
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('config/llm-usage');
      setUsage(res.data);
    } catch {
      setError('Не удалось загрузить статистику расходов');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const fmtRub = (v) => (v == null ? '—' : `${Number(v).toFixed(2)} ₽`);
  const fmtInt = (v) => Number(v || 0).toLocaleString('ru-RU');

  return (
    <div>
      <div className="flex items-center justify-end mb-3">
        <button type="button" onClick={load} disabled={loading} className="btn btn--secondary">
          {loading ? 'Обновление…' : 'Обновить'}
        </button>
      </div>
      {error && <p className="text-sm text-red-500 mb-2">{error}</p>}
      {usage && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
          <div className="rounded border border-[color:var(--color-border)] p-3">
            <p className="text-[color:var(--color-muted-foreground)] mb-1">Сегодня</p>
            <p className="font-mono">{fmtInt(usage.today.tokens)} токенов</p>
            <p className="font-mono">{fmtRub(usage.today.cost_rub)}</p>
            {usage.today.truncated && <p className="text-xs text-amber-500 mt-1">Показана не вся история за период</p>}
          </div>
          <div className="rounded border border-[color:var(--color-border)] p-3">
            <p className="text-[color:var(--color-muted-foreground)] mb-1">За 30 дней</p>
            <p className="font-mono">{fmtInt(usage.period_30d.tokens)} токенов</p>
            <p className="font-mono">{fmtRub(usage.period_30d.cost_rub)}</p>
            {usage.period_30d.truncated && <p className="text-xs text-amber-500 mt-1">Показана не вся история за период</p>}
          </div>
          <div className="rounded border border-[color:var(--color-border)] p-3">
            <p className="text-[color:var(--color-muted-foreground)] mb-1">Баланс Polza.ai</p>
            <p className="font-mono">
              {usage.balance_rub != null
                ? fmtRub(usage.balance_rub)
                : (usage.balance_error ? '—' : 'н/д (провайдер не Polza)')}
            </p>
            {usage.balance_error && <p className="text-xs text-red-500 mt-1">{usage.balance_error}</p>}
          </div>
        </div>
      )}
    </div>
  );
}

function EmployeeLlmUsagePanel() {
  const [rows, setRows] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('config/llm-usage/by-employee', { params: { days: 30 } });
      setRows(res.data);
    } catch {
      setError('Не удалось загрузить расходы по сотрудникам');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const fmtRub = (v) => (v == null ? '—' : `${Number(v).toFixed(2)} ₽`);
  const fmtInt = (v) => Number(v || 0).toLocaleString('ru-RU');
  const fmtDate = (v) => (v ? new Date(v).toLocaleString('ru-RU') : '—');
  // Share of tokens the provider served from its prompt cache. 0% here means
  // caching silently isn't working on the configured model — the whole reason
  // this column exists, since the cost difference is ~10x.
  const fmtCached = (r) => {
    const tokens = Number(r.tokens || 0);
    const cached = Number(r.cached_tokens || 0);
    if (!tokens) return '—';
    return `${fmtInt(cached)} (${Math.round((cached / tokens) * 100)}%)`;
  };

  return (
    <div>
      <div className="flex items-center justify-end mb-3">
        <button type="button" onClick={load} disabled={loading} className="btn btn--secondary">
          {loading ? 'Обновление…' : 'Обновить'}
        </button>
      </div>
      {error && <p className="text-sm text-red-500 mb-2">{error}</p>}
      {rows && rows.length === 0 && (
        <p className="text-sm text-[color:var(--color-muted-foreground)]">Пока нет обращений к базе знаний через бота.</p>
      )}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[color:var(--color-muted-foreground)]">
                <th className="pr-3 py-1 font-normal">Сотрудник</th>
                <th className="pr-3 py-1 font-normal text-right">Запросов</th>
                <th className="pr-3 py-1 font-normal text-right">Токенов</th>
                <th className="pr-3 py-1 font-normal text-right">Из кэша</th>
                <th className="pr-3 py-1 font-normal text-right">Рублей</th>
                <th className="pr-3 py-1 font-normal">Последнее обращение</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.employee_id} className="border-t border-[color:var(--color-border)]">
                  <td className="pr-3 py-1">{r.employee_name || r.employee_id}</td>
                  <td className="pr-3 py-1 text-right font-mono">{fmtInt(r.requests)}</td>
                  <td className="pr-3 py-1 text-right font-mono">{fmtInt(r.tokens)}</td>
                  <td className="pr-3 py-1 text-right font-mono">{fmtCached(r)}</td>
                  <td className="pr-3 py-1 text-right font-mono">{fmtRub(r.cost_rub)}</td>
                  <td className="pr-3 py-1">{fmtDate(r.last_used_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
