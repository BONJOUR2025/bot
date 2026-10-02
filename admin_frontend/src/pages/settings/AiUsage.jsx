import { Fragment, useEffect, useState } from 'react';
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
          Разбивка по сотрудникам, обращавшимся к базе знаний через Telegram-бота, плюс отдельная
          строка «Быстрый режим (кандидаты)» — распознавание встречных вопросов кандидатов в
          быстром опросе (hh/Авито), не привязанное к конкретному сотруднику. Polza не знает, кто
          сделал запрос — эти данные считаются и хранятся у нас, при каждом обращении.
        </p>
        <EmployeeLlmUsagePanel />
      </Section>

      <Section title="Помощь в админке">
        <p className="text-sm text-[color:var(--color-muted-foreground)] -mt-2">
          Сколько стоили вопросы помощнику на странице «Помощь». На каждый вопрос — проверка
          «вопрос о работе в панели?» и, если проверка пройдена, сам ответ; отклонённые вопросы
          стоят только проверку.
        </p>
        <HelpLlmUsagePanel />
      </Section>
    </div>
  );
}

const HELP_PERIODS = [[1, '24 часа'], [7, '7 дней'], [30, '30 дней'], [0, 'Всё время']];

function HelpLlmUsagePanel() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [openIdx, setOpenIdx] = useState(null);

  async function load(d = days) {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('config/llm-usage/help', { params: { days: d } });
      setData(res.data);
      setOpenIdx(null);
    } catch {
      setError('Не удалось загрузить расход помощника');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(days); }, [days]); // eslint-disable-line react-hooks/exhaustive-deps

  // Вопрос стоит копейки — с двумя знаками было бы «0.00 ₽».
  const fmtRub = (v, digits = 2) => (v == null ? '—' : `${Number(v).toFixed(digits)} ₽`);
  const fmtInt = (v) => Number(v || 0).toLocaleString('ru-RU');
  const fmtDate = (v) => (v ? new Date(v).toLocaleString('ru-RU') : '—');

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex flex-wrap gap-1.5">
          {HELP_PERIODS.map(([d, label]) => (
            <button key={d} type="button" onClick={() => setDays(d)}
              className={`btn btn--sm ${days === d ? 'btn--primary' : 'btn--secondary'}`}>
              {label}
            </button>
          ))}
        </div>
        <button type="button" onClick={() => load()} disabled={loading} className="btn btn--secondary">
          {loading ? 'Обновление…' : 'Обновить'}
        </button>
      </div>
      {error && <p className="text-sm text-red-500 mb-2">{error}</p>}
      {data && data.questions === 0 && (
        <p className="text-sm text-[color:var(--color-muted-foreground)]">За этот период вопросов помощнику не было.</p>
      )}
      {data && data.questions > 0 && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div className="rounded border border-[color:var(--color-border)] p-3">
              <p className="text-[color:var(--color-muted-foreground)] mb-1">Потрачено</p>
              <p className="font-mono text-base font-semibold">{fmtRub(data.cost_rub)}</p>
              <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">
                ответы {fmtRub(data.answer_cost_rub)} · проверки {fmtRub(data.filter_cost_rub)}
              </p>
            </div>
            <div className="rounded border border-[color:var(--color-border)] p-3">
              <p className="text-[color:var(--color-muted-foreground)] mb-1">Вопросов</p>
              <p className="font-mono text-base font-semibold">{fmtInt(data.questions)}</p>
              <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">
                с ответом {fmtInt(data.answered)} · отклонено {fmtInt(data.rejected)}
              </p>
            </div>
            <div className="rounded border border-[color:var(--color-border)] p-3">
              <p className="text-[color:var(--color-muted-foreground)] mb-1">Цена вопроса</p>
              <p className="font-mono text-base font-semibold">{fmtRub(data.avg_cost_rub, 3)}</p>
              <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">в среднем</p>
            </div>
            <div className="rounded border border-[color:var(--color-border)] p-3">
              <p className="text-[color:var(--color-muted-foreground)] mb-1">Токенов</p>
              <p className="font-mono text-base font-semibold">{fmtInt(data.tokens)}</p>
            </div>
          </div>

          {data.by_user.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[color:var(--color-muted-foreground)]">
                    <th className="pr-3 py-1 font-normal">Кто спрашивал</th>
                    <th className="pr-3 py-1 font-normal text-right">Вопросов</th>
                    <th className="pr-3 py-1 font-normal text-right">Отклонено</th>
                    <th className="pr-3 py-1 font-normal text-right">Рублей</th>
                    <th className="pr-3 py-1 font-normal">Последний вопрос</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_user.map((u) => (
                    <tr key={u.employee_id} className="border-t border-[color:var(--color-border)]">
                      <td className="pr-3 py-1">{u.employee_name}</td>
                      <td className="pr-3 py-1 text-right font-mono">{fmtInt(u.questions)}</td>
                      <td className="pr-3 py-1 text-right font-mono">{fmtInt(u.rejected)}</td>
                      <td className="pr-3 py-1 text-right font-mono">{fmtRub(u.cost_rub)}</td>
                      <td className="pr-3 py-1">{fmtDate(u.last_used_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div>
            <p className="text-xs text-[color:var(--color-muted-foreground)] mb-2">
              Последние вопросы (до 50) — нажмите, чтобы увидеть ответ.
            </p>
            <div className="space-y-1.5">
              {data.recent.map((q, i) => {
                const open = openIdx === i;
                return (
                  <div key={i} className="rounded border border-[color:var(--color-border)] text-sm">
                    <button type="button" onClick={() => setOpenIdx(open ? null : i)}
                      className="w-full flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2 text-left hover:bg-[color:var(--color-bg-secondary)]">
                      <span className="flex-1 min-w-[12rem]">{q.question || '—'}</span>
                      <span className={`text-xs ${q.answered ? 'text-green-600' : 'text-[color:var(--color-muted-foreground)]'}`}>
                        {q.answered ? 'ответ' : 'отклонён'}
                      </span>
                      <span className="font-mono text-xs">{fmtRub(q.cost_rub, 4)}</span>
                      <span className="text-xs text-[color:var(--color-muted-foreground)]">
                        {q.employee_name} · {fmtDate(q.created_at)}
                      </span>
                    </button>
                    {open && (
                      <div className="border-t border-[color:var(--color-border)] px-3 py-2 text-[color:var(--color-muted-foreground)] whitespace-pre-wrap">
                        {q.answered ? q.answer : 'Фильтр решил, что вопрос не о работе в панели, — ответ не запрашивался.'}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
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
  const [openId, setOpenId] = useState(null);

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
        <p className="text-sm text-[color:var(--color-muted-foreground)]">Пока нет обращений к базе знаний через бота и запросов быстрого режима.</p>
      )}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto">
          <p className="text-xs text-[color:var(--color-muted-foreground)] mb-2">
            Нажмите на сотрудника, чтобы посмотреть его запросы и ответы.
          </p>
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
              {rows.map((r) => {
                const isOpen = openId === r.employee_id;
                return (
                  <Fragment key={r.employee_id}>
                    <tr
                      className="border-t border-[color:var(--color-border)] cursor-pointer hover:bg-[color:var(--color-bg-secondary)]"
                      onClick={() => setOpenId(isOpen ? null : r.employee_id)}
                    >
                      <td className="pr-3 py-1">
                        <span className="inline-block w-4 text-[color:var(--color-muted-foreground)]">
                          {isOpen ? '▾' : '▸'}
                        </span>
                        {r.employee_name || r.employee_id}
                      </td>
                      <td className="pr-3 py-1 text-right font-mono">{fmtInt(r.requests)}</td>
                      <td className="pr-3 py-1 text-right font-mono">{fmtInt(r.tokens)}</td>
                      <td className="pr-3 py-1 text-right font-mono">{fmtCached(r)}</td>
                      <td className="pr-3 py-1 text-right font-mono">{fmtRub(r.cost_rub)}</td>
                      <td className="pr-3 py-1">{fmtDate(r.last_used_at)}</td>
                    </tr>
                    {isOpen && (
                      <tr className="border-t border-[color:var(--color-border)]">
                        <td colSpan={6} className="py-2">
                          <EmployeeRequests employeeId={r.employee_id} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function EmployeeRequests({ employeeId }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState('');

  // Fetched on expand rather than up-front with the totals: the answers are
  // full text, and pulling them for every employee to show none of them
  // would be the bulk of the payload.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get(`config/llm-usage/by-employee/${employeeId}`, { params: { days: 30 } });
        if (!cancelled) setItems(res.data);
      } catch {
        if (!cancelled) setError('Не удалось загрузить запросы сотрудника');
      }
    })();
    return () => { cancelled = true; };
  }, [employeeId]);

  const fmtRub = (v) => (v == null ? '—' : `${Number(v).toFixed(4)} ₽`);
  const fmtInt = (v) => Number(v || 0).toLocaleString('ru-RU');

  if (error) return <p className="text-sm text-red-500 px-2">{error}</p>;
  if (!items) return <p className="text-sm text-[color:var(--color-muted-foreground)] px-2">Загрузка…</p>;
  if (!items.length) return <p className="text-sm text-[color:var(--color-muted-foreground)] px-2">Запросов за период нет.</p>;

  return (
    <div className="space-y-2 px-2">
      {items.map((it) => (
        <div key={it.id} className="rounded border border-[color:var(--color-border)] p-3 text-sm">
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-[color:var(--color-muted-foreground)] mb-2">
            <span>{it.created_at ? new Date(it.created_at).toLocaleString('ru-RU') : '—'}</span>
            <span className="font-mono">{it.model}</span>
            <span className="font-mono">{fmtInt(it.total_tokens)} ток.</span>
            {it.cached_tokens > 0 && (
              <span className="font-mono text-green-600">из кэша {fmtInt(it.cached_tokens)}</span>
            )}
            <span className="font-mono">{fmtRub(it.cost_rub)}</span>
          </div>
          {it.question
            ? <p className="whitespace-pre-wrap mb-2"><span className="font-medium">Вопрос:</span> {it.question}</p>
            : <p className="text-xs text-[color:var(--color-muted-foreground)] mb-2">
                Текст не сохранён — запрос сделан до того, как включилось сохранение переписки.
              </p>}
          {it.answer && (
            <p className="whitespace-pre-wrap text-[color:var(--color-muted-foreground)]">
              <span className="font-medium text-[color:var(--color-foreground)]">Ответ:</span> {it.answer}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
