import { useCallback, useEffect, useRef, useState } from 'react';
import { Search, Square, Shield, ExternalLink, Loader2 } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

// Быстрый набор — площадки, на которых у нас реально что-то ищут. Полный
// прогон идёт по 400+ сайтам и занимает около минуты; когда нужен ответ
// «есть ли этот ник вообще», хватает десятка.
const QUICK_SITES = [
  'VK', 'Telegram', 'Instagram', 'GitHub', 'Reddit', 'Pinterest',
  'YouTube', 'TikTok', 'X', 'Facebook',
];

export default function UsernameSearch() {
  const { toast } = useToast();
  const [username, setUsername] = useState('');
  const [scope, setScope] = useState('quick'); // quick | all
  const [useProxy, setUseProxy] = useState(false);
  const [running, setRunning] = useState(false);
  const [hits, setHits] = useState([]);
  const [checked, setChecked] = useState(0);
  const [total, setTotal] = useState(null);
  const [lastSite, setLastSite] = useState('');
  const [finished, setFinished] = useState(false);
  const abortRef = useRef(null);

  useEffect(() => {
    api.get('osint/sites')
      .then((r) => setTotal(r.data.total))
      .catch(() => setTotal(null));
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setRunning(false);
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function run() {
    const name = username.trim();
    if (!name) return;
    setHits([]); setChecked(0); setLastSite(''); setFinished(false); setRunning(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      // Не axios: ответ приходит потоком NDJSON минутами, и его нужно читать
      // по мере поступления, а axios отдаёт тело целиком в конце.
      const res = await fetch('/api/osint/username', {
        method: 'POST',
        signal: ctrl.signal,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('auth_token') || ''}`,
        },
        body: JSON.stringify({
          username: name,
          sites: scope === 'quick' ? QUICK_SITES : [],
          use_proxy: useProxy,
          timeout: 15,
        }),
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try { detail = (await res.json()).detail || detail; } catch { /* тело не JSON */ }
        throw new Error(detail);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        // Последняя строка может быть обрезана посередине — дочитываем её
        // следующим куском, иначе JSON.parse свалится на половине объекта.
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.trim()) continue;
          let ev;
          try { ev = JSON.parse(line); } catch { continue; }
          if (ev.type === 'hit') {
            setHits((h) => [...h, { site: ev.site, url: ev.url }]);
            setChecked(ev.n); setLastSite(ev.site);
          } else if (ev.type === 'miss') {
            setChecked(ev.n); setLastSite(ev.site);
          } else if (ev.type === 'done') {
            setFinished(true);
          } else if (ev.type === 'error') {
            toast(ev.message, 'error');
          }
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') toast(e.message || 'Поиск не удался', 'error');
    } finally {
      abortRef.current = null;
      setRunning(false);
    }
  }

  const plannedTotal = scope === 'quick' ? QUICK_SITES.length : total;
  const pct = plannedTotal ? Math.min(100, Math.round((checked / plannedTotal) * 100)) : 0;

  return (
    <div className="space-y-5 max-w-4xl mx-auto pb-12">
      <div>
        <span className="ui-eyebrow mb-3">
          {total ? `База · ${total} площадок` : 'База площадок'}
        </span>
        <h2 className="text-2xl font-semibold tracking-tight">Поиск по нику</h2>
        <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">
          Проверяет, занят ли ник на публичных площадках, и даёт ссылки на найденные профили.
        </p>
      </div>

      <div className="app-card p-4 space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="block flex-1">
            <span className="block text-xs font-medium uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-1">Ник</span>
            <input
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !running) run(); }}
              placeholder="например bonjourspb"
              disabled={running}
            />
          </label>
          {running ? (
            <button className="btn btn--secondary flex items-center gap-2 justify-center shrink-0" onClick={stop}>
              <Square size={14} /> Остановить
            </button>
          ) : (
            <button className="btn btn--primary flex items-center gap-2 justify-center shrink-0" onClick={run} disabled={!username.trim()}>
              <Search size={15} /> Искать
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            className={`ui-chip ${scope === 'quick' ? 'is-active' : ''}`}
            aria-pressed={scope === 'quick'}
            onClick={() => setScope('quick')}
            disabled={running}
          >
            Основные · {QUICK_SITES.length}
          </button>
          <button
            className={`ui-chip ${scope === 'all' ? 'is-active' : ''}`}
            aria-pressed={scope === 'all'}
            onClick={() => setScope('all')}
            disabled={running}
          >
            Все площадки{total ? ` · ${total}` : ''}
          </button>
          <button
            className={`ui-chip ${useProxy ? 'is-active' : ''}`}
            aria-pressed={useProxy}
            onClick={() => setUseProxy((v) => !v)}
            disabled={running}
            title="Через локальный vpn-proxy — часть площадок из РФ напрямую не открывается"
          >
            <Shield size={12} className="mr-1 inline-block align-[-1px]" /> Через VPN
          </button>
          {scope === 'all' && (
            <span className="text-[11px] text-[color:var(--color-muted-foreground)]">
              полный прогон занимает около минуты
            </span>
          )}
        </div>
      </div>

      {(running || checked > 0) && (
        <div className="space-y-3">
          <div className="fui-section">
            <span className="fui-section__label">Ход поиска</span>
            <span className="fui-section__line" />
            <span className="fui-section__meta">
              {running ? lastSite || 'старт' : finished ? 'завершено' : 'остановлено'}
            </span>
          </div>
          <div className="fui-band">
            <div className={`fui-band__cell ${hits.length ? 'fui-band__cell--flag' : ''}`} style={{ '--flag': 'var(--color-success)' }}>
              <span className="fui-band__k">Найдено</span>
              <span className="fui-band__v">{hits.length}</span>
              <span className="fui-band__m"><span>профилей с этим ником</span></span>
            </div>
            <div className="fui-band__cell">
              <span className="fui-band__k">Проверено</span>
              <span className="fui-band__v">{checked}</span>
              <span className="fui-band__m"><span>{plannedTotal ? `из ${plannedTotal}` : 'площадок'}</span></span>
            </div>
            <div className="fui-band__cell">
              <span className="fui-band__k">Прогресс</span>
              <span className="fui-band__v">{pct}<small>%</small></span>
              <span className="fui-band__m">
                <span className={`fui-status fui-status--always ${running ? 'fui-status--processing' : finished ? 'fui-status--success' : 'fui-status--paused'}`}>
                  <span className="fui-status__t">{running ? 'Идёт опрос' : finished ? 'Готово' : 'Остановлено'}</span>
                </span>
              </span>
            </div>
          </div>
        </div>
      )}

      {hits.length > 0 && (
        <div className="app-card overflow-hidden">
          <ul className="divide-y divide-[color:var(--color-border)]">
            {hits.map((h) => (
              <li key={h.site} className="px-5 py-3 flex items-center justify-between gap-3">
                <span className="text-sm font-medium truncate">{h.site}</span>
                <a
                  href={h.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-sm text-[color:var(--color-primary)] flex items-center gap-1.5 shrink-0 min-w-0"
                >
                  <span className="truncate">{h.url}</span>
                  <ExternalLink size={13} className="shrink-0" />
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!running && checked === 0 && (
        <div className="app-card">
          <div className="fui-datastate">
            <span className="fui-datastate__code fui-datastate__code--icon"><Search size={13} /> Готов к поиску</span>
            <span className="fui-datastate__rule" />
            <span className="fui-datastate__title">Введите ник</span>
            <span className="fui-datastate__text">
              Опрос идёт по публичным страницам профилей. Совпадение ника не означает, что аккаунт принадлежит одному человеку.
            </span>
          </div>
        </div>
      )}

      {finished && hits.length === 0 && checked > 0 && (
        <div className="app-card">
          <div className="fui-datastate fui-datastate--compact">
            <span className="fui-datastate__code">Пусто</span>
            <span className="fui-datastate__rule" />
            <span className="fui-datastate__text">Ник не найден ни на одной из проверенных площадок.</span>
          </div>
        </div>
      )}

      {running && (
        <div className="flex items-center gap-2 text-xs text-[color:var(--color-muted-foreground)]">
          <Loader2 size={13} className="animate-spin" />
          Результаты появляются по мере ответа площадок — можно не ждать конца.
        </div>
      )}
    </div>
  );
}
