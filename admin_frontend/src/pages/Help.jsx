import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, ArrowUpRight, MapPin, RotateCcw, Search, Send, Sparkles } from 'lucide-react';
import api from '../api';
import PageHeader from '../components/ui/PageHeader.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';

/** «Помощь»: инструкции по разделам панели и помощник, который отвечает
 *  на вопросы о том, как что-то сделать в панели. Статьи и их видимость
 *  по правам — с сервера (GET /help/articles); вопрос — POST /help/ask,
 *  сервер сам отсекает всё, что не про работу в панели. */

const EXAMPLES = [
  'Как одобрить заявку на выплату?',
  'Как отправить сотрудника в архив?',
  'Где выставить план продаж точке?',
];

/* ── мини-markdown: ## заголовок, списки «- » и «1. », **жирный** ─── */
function inline(text) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={i} className="font-semibold text-[color:var(--color-text)]">{part.slice(2, -2)}</strong>
      : <Fragment key={i}>{part}</Fragment>,
  );
}

function parseBlocks(md) {
  const blocks = [];
  let list = null;
  for (const raw of md.split('\n')) {
    const line = raw.replace(/\s+$/, '');
    const nested = /^\s{2,}[-*]\s+/.test(line);
    const ul = /^[-*]\s+/.test(line);
    const ol = /^\d+\.\s+/.test(line);
    if (nested && list) {
      const last = list.items[list.items.length - 1];
      if (last) last.children.push(line.replace(/^\s+[-*]\s+/, ''));
      continue;
    }
    if (ul || ol) {
      const type = ul ? 'ul' : 'ol';
      if (!list || list.type !== type) {
        list = { type, items: [] };
        blocks.push(list);
      }
      list.items.push({ text: line.replace(/^([-*]|\d+\.)\s+/, ''), children: [] });
      continue;
    }
    list = null;
    if (!line.trim()) continue;
    if (line.startsWith('## ')) blocks.push({ type: 'h', text: line.slice(3) });
    else if (line.startsWith('**Где:**')) blocks.push({ type: 'where', text: line.slice(8).trim() });
    else blocks.push({ type: 'p', text: line });
  }
  return blocks;
}

/** «Где: Меню → Деньги → Выплаты → вкладка «Заявки»» — самое важное в
 *  инструкции, поэтому плашкой, а не строкой текста. */
function Where({ text, compact = false }) {
  return (
    <div
      className={`flex items-start gap-2 rounded-lg border text-[color:var(--color-text)] ${compact ? 'px-2.5 py-1.5 text-sm' : 'px-3 py-2 text-sm'}`}
      style={{
        background: 'color-mix(in srgb, var(--color-primary) 9%, transparent)',
        borderColor: 'color-mix(in srgb, var(--color-primary) 35%, transparent)',
      }}
    >
      <MapPin size={15} className="mt-0.5 shrink-0 text-[color:var(--color-primary)]" aria-hidden="true" />
      <span><span className="font-semibold">Где: </span>{text.replace(/^Где:\s*/, '')}</span>
    </div>
  );
}

function Markdown({ text }) {
  const blocks = useMemo(() => parseBlocks(text || ''), [text]);
  return (
    <div className="space-y-3 text-[15px] leading-relaxed text-[color:var(--color-text-muted)]">
      {blocks.map((b, i) => {
        if (b.type === 'h') {
          return <h3 key={i} className="pt-3 text-base font-semibold text-[color:var(--color-text)]">{b.text}</h3>;
        }
        if (b.type === 'p') return <p key={i}>{inline(b.text)}</p>;
        if (b.type === 'where') return <Where key={i} text={b.text} />;
        const ListTag = b.type === 'ol' ? 'ol' : 'ul';
        return (
          <ListTag key={i} className={`space-y-1.5 pl-5 ${b.type === 'ol' ? 'list-decimal' : 'list-disc'}`}>
            {b.items.map((it, j) => (
              <li key={j}>
                {inline(it.text)}
                {it.children.length > 0 && (
                  <ul className="mt-1 list-[circle] space-y-1 pl-5">
                    {it.children.map((c, k) => <li key={k}>{inline(c)}</li>)}
                  </ul>
                )}
              </li>
            ))}
          </ListTag>
        );
      })}
    </div>
  );
}

/* ── помощник ─────────────────────────────────────────────────────── */
function Assistant({ articles, onOpenArticle }) {
  const [thread, setThread] = useState([]); // {role, content, refs?, offtopic?, error?}
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const byId = useMemo(() => Object.fromEntries(articles.map((a) => [a.id, a])), [articles]);

  useEffect(() => {
    if (thread.length) endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [thread]);

  const send = async (text) => {
    const question = (text ?? q).trim();
    if (question.length < 3 || busy) return;
    // В историю — только нормальные реплики: отказы и ошибки модели не нужны.
    const history = thread
      .filter((m) => !m.error && !m.offtopic)
      .slice(-4)
      .map(({ role, content }) => ({ role, content }));
    setThread((t) => [...t, { role: 'user', content: question }]);
    setQ('');
    setBusy(true);
    try {
      const r = await api.post('help/ask', { question, history });
      setThread((t) => [...t, { role: 'assistant', content: r.data.answer, refs: r.data.refs || [], offtopic: r.data.offtopic }]);
    } catch (e) {
      const d = e?.response?.data?.detail;
      setThread((t) => [...t, { role: 'assistant', content: typeof d === 'string' ? d : 'Помощник сейчас недоступен. Попробуйте позже.', error: true }]);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  };

  return (
    <section className="app-card p-4 sm:p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-[color:var(--color-primary)]" aria-hidden="true" />
          <h2 className="text-base leading-tight font-semibold text-[color:var(--color-text)]">Спросить помощника</h2>
        </div>
        {thread.length > 0 && (
          <button type="button" onClick={() => setThread([])} className="btn btn--secondary btn--sm flex shrink-0 items-center gap-1.5 whitespace-nowrap">
            <RotateCcw size={13} /> Новый вопрос
          </button>
        )}
      </div>

      {thread.length === 0 ? (
        <div className="mb-3">
          <p className="text-sm text-[color:var(--color-text-muted)]">
            Опишите своими словами, что хотите сделать в панели. Помощник отвечает только о работе в панели — про данные, цифры и прочее он не расскажет.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" onClick={() => send(ex)} disabled={busy}
                className="rounded-full border border-[color:var(--color-border)] px-3 py-1.5 text-xs text-[color:var(--color-text-muted)] transition-colors hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)]">
                {ex}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="mb-3 max-h-[55vh] space-y-3 overflow-y-auto pr-1" aria-live="polite">
          {thread.map((m, i) => (
            m.role === 'user' ? (
              <div key={i} className="flex justify-end">
                <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-[color:var(--color-primary)] px-3.5 py-2 text-sm text-white">
                  {m.content}
                </div>
              </div>
            ) : (
              <div key={i} className="flex justify-start">
                <div className={`max-w-[92%] rounded-2xl rounded-bl-md border px-3.5 py-2.5 text-sm ${
                  m.error ? 'border-[color:var(--color-danger)] text-[color:var(--color-danger)]'
                    : m.offtopic ? 'border-[color:var(--color-border)] text-[color:var(--color-text-muted)] italic'
                      : 'border-[color:var(--color-border)] text-[color:var(--color-text)]'}`}>
                  {(() => {
                    const [first, ...rest] = m.content.split('\n');
                    if (m.error || m.offtopic || !/^Где:/.test(first.trim())) {
                      return <div className="whitespace-pre-wrap leading-relaxed">{m.content}</div>;
                    }
                    return (
                      <>
                        <Where text={first.trim()} compact />
                        <div className="mt-2 whitespace-pre-wrap leading-relaxed">{rest.join('\n').trim()}</div>
                      </>
                    );
                  })()}
                  {m.refs?.some((id) => byId[id]) && (
                    <div className="mt-2.5 flex flex-wrap gap-1.5 border-t border-[color:var(--color-border)] pt-2">
                      {m.refs.filter((id) => byId[id]).map((id) => (
                        <button key={id} type="button" onClick={() => onOpenArticle(id)}
                          className="rounded-md bg-[color:var(--color-bg-subtle)] px-2 py-1 text-xs text-[color:var(--color-primary)] hover:underline">
                          Инструкция: {byId[id].title}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )
          ))}
          {busy && <div className="text-xs text-[color:var(--color-muted-foreground)]">Помощник думает…</div>}
          <div ref={endRef} />
        </div>
      )}

      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex gap-2">
        <input
          ref={inputRef}
          className="input min-w-0 flex-1"
          value={q}
          maxLength={500}
          onChange={(e) => setQ(e.target.value)}
          placeholder={thread.length ? 'Уточните или задайте новый вопрос…' : 'Например: как добавить сотрудника?'}
          aria-label="Вопрос помощнику"
        />
        <button type="submit" disabled={busy || q.trim().length < 3} className="btn btn--primary btn--sm flex items-center gap-1.5">
          <Send size={14} /> <span className="hidden sm:inline">Спросить</span>
        </button>
      </form>
    </section>
  );
}

/* ── страница ─────────────────────────────────────────────────────── */
export default function Help() {
  const { isMobile } = useViewport();
  const [articles, setArticles] = useState([]);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');
  const [params, setParams] = useSearchParams();
  const articleRef = useRef(null);
  const openId = params.get('a');

  useEffect(() => {
    api.get('help/articles')
      .then((r) => setArticles(r.data || []))
      .catch(() => setError('Не удалось загрузить инструкции'));
  }, []);

  const current = articles.find((a) => a.id === openId) || (!isMobile ? articles[0] : null);

  const open = (id) => {
    setParams(id ? { a: id } : {}, { replace: !isMobile });
    requestAnimationFrame(() => articleRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  };

  const groups = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const list = needle
      ? articles.filter((a) => `${a.title} ${a.section} ${a.body}`.toLowerCase().includes(needle))
      : articles;
    const map = new Map();
    for (const a of list) {
      if (!map.has(a.section)) map.set(a.section, []);
      map.get(a.section).push(a);
    }
    return [...map.entries()];
  }, [articles, filter]);

  const list = (
    <nav className="app-card p-3" aria-label="Инструкции">
      <div className="relative mb-3">
        <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)]" />
        <input className="input w-full pl-8 text-sm" placeholder="Поиск по инструкциям…" value={filter}
          onChange={(e) => setFilter(e.target.value)} aria-label="Поиск по инструкциям" />
      </div>
      {groups.length === 0 && (
        <p className="px-2 py-4 text-sm text-[color:var(--color-muted-foreground)]">
          {articles.length ? 'Ничего не найдено — попробуйте спросить помощника.' : 'Загрузка…'}
        </p>
      )}
      <div className="space-y-3">
        {groups.map(([section, items]) => (
          <div key={section}>
            <div className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-[color:var(--color-muted-foreground)]">{section}</div>
            {items.map((a) => (
              <button key={a.id} type="button" onClick={() => open(a.id)}
                aria-current={current?.id === a.id ? 'page' : undefined}
                className={`block w-full rounded-lg px-2 py-1.5 text-left text-sm transition-colors ${
                  current?.id === a.id
                    ? 'bg-[color:var(--color-primary)]/10 font-medium text-[color:var(--color-primary)]'
                    : 'text-[color:var(--color-text)] hover:bg-[color:var(--color-bg-subtle)]'}`}>
                {a.title}
              </button>
            ))}
          </div>
        ))}
      </div>
    </nav>
  );

  const article = current && (
    <article ref={articleRef} className="app-card scroll-mt-4 p-5 sm:p-7">
      {isMobile && (
        <button type="button" onClick={() => open(null)} className="mb-3 flex items-center gap-1 text-sm text-[color:var(--color-primary)]">
          <ArrowLeft size={14} /> Все инструкции
        </button>
      )}
      <div className="text-xs uppercase tracking-wide text-[color:var(--color-muted-foreground)]">{current.section}</div>
      <div className="mt-1 mb-4 flex flex-wrap items-start justify-between gap-3">
        <h2 className="text-xl font-semibold text-[color:var(--color-text)]">{current.title}</h2>
        {current.route && (
          <Link to={current.route} className="btn btn--secondary btn--sm flex items-center gap-1">
            Открыть раздел <ArrowUpRight size={13} />
          </Link>
        )}
      </div>
      {current.menu && (
        <div className="mb-5 space-y-1.5">
          <Where text={`Меню → ${current.menu}`} />
          {current.tabs && (
            <p className="px-1 text-sm text-[color:var(--color-text-muted)]">
              <span className="font-medium text-[color:var(--color-text)]">Вкладки: </span>{current.tabs}
            </p>
          )}
        </div>
      )}
      <Markdown text={current.body} />
    </article>
  );

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Справка"
        title="Помощь"
        description="Инструкции по разделам панели и помощник, который подскажет, как выполнить нужное действие."
      />
      <Assistant articles={articles} onOpenArticle={open} />
      {error && <div className="rounded-lg border border-[color:var(--color-danger)] p-4 text-sm text-[color:var(--color-danger)]">{error}</div>}
      {isMobile ? (
        current ? article : list
      ) : (
        <div className="grid grid-cols-[260px_minmax(0,1fr)] items-start gap-5">
          <div className="sticky top-4 max-h-[calc(100vh-2rem)] overflow-y-auto">{list}</div>
          {article}
        </div>
      )}
    </div>
  );
}
