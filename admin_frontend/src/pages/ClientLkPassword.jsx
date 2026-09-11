import { useState } from 'react';
import { KeyRound, Search, Copy, Check, Phone, User, AlertTriangle } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

// Восстановление пароля от личного кабинета клиента по телефону.
// Пароль в Agbis хранится несолёным SHA-1 от 4-значного PIN, поэтому сервер
// возвращает уже восстановленный PIN — здесь остаётся только показать и дать
// скопировать.

function normalizePhoneHint(raw) {
  const d = (raw || '').replace(/\D/g, '');
  return d.length >= 7 ? d.slice(-10) : '';
}

export default function ClientLkPassword() {
  const { toast } = useToast();
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null); // null = не искали, [] = не нашли
  const [error, setError] = useState('');
  const [copiedId, setCopiedId] = useState(null);
  const [revealed, setRevealed] = useState(() => new Set());

  async function search(e) {
    e?.preventDefault();
    const tail = normalizePhoneHint(phone);
    if (!tail) {
      setError('Введите не меньше 7 цифр номера.');
      return;
    }
    setError('');
    setLoading(true);
    setResults(null);
    try {
      const res = await api.get('client-passwords/lookup', { params: { phone } });
      setResults(res.data || []);
      setRevealed(new Set());
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Ошибка запроса');
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  async function copyPin(pin, id) {
    try {
      await navigator.clipboard.writeText(pin);
      setCopiedId(id);
      setTimeout(() => setCopiedId((c) => (c === id ? null : c)), 1500);
    } catch {
      toast('Не удалось скопировать', 'error');
    }
  }

  function toggleReveal(id) {
    setRevealed((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  return (
    <div className="space-y-5 max-w-[760px] mx-auto pb-12">
      <div className="ui-reveal">
        <span className="ui-eyebrow mb-3">Клиенты · личный кабинет</span>
        <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)] flex items-center gap-2">
          <KeyRound size={22} style={{ color: 'var(--color-primary)' }} /> Пароль клиента от ЛК
        </h2>
        <p className="text-sm text-[color:var(--color-muted-foreground)] mt-2 max-w-[62ch]">
          Введите номер телефона — вернём пароль от личного кабинета. Номер можно вводить в любом
          формате: <span className="whitespace-nowrap">+7 900…</span>, <span className="whitespace-nowrap">8 900…</span> или просто последние цифры — сверяются последние 10.
        </p>
      </div>

      <form onSubmit={search} className="app-card p-5 flex flex-wrap items-end gap-3">
        <label className="flex-1 min-w-[240px] block">
          <span className="block text-[11px] font-medium uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-1">
            Телефон клиента
          </span>
          <div className="relative">
            <Phone size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)]" />
            <input
              type="tel"
              className="input pl-9 w-full"
              placeholder="+7 900 123-45-67"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              autoFocus
            />
          </div>
        </label>
        <button type="submit" className="btn btn--primary flex items-center gap-1.5" disabled={loading}>
          <Search size={15} className={loading ? 'animate-pulse' : ''} /> {loading ? 'Ищу…' : 'Найти'}
        </button>
      </form>

      {error && (
        <div className="app-card p-4 flex items-center gap-2 text-sm" style={{ color: 'var(--color-danger)' }}>
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {results && results.length === 0 && (
        <div className="app-card p-6 text-center text-sm text-[color:var(--color-muted-foreground)]">
          Клиент с таким телефоном и зарегистрированным личным кабинетом не найден.
        </div>
      )}

      {results && results.length > 0 && (
        <div className="space-y-3">
          {results.length > 1 && (
            <div className="text-[13px] text-[color:var(--color-muted-foreground)]">
              На этот номер заведено карточек: {results.length}
            </div>
          )}
          {results.map((r) => {
            const id = r.contragent_id;
            const shown = revealed.has(id);
            return (
              <div key={id} className="app-card p-5">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-base font-semibold text-[color:var(--color-text)]">
                      <User size={16} style={{ color: 'var(--color-primary)' }} />
                      <span className="truncate">{r.name || 'Без имени'}</span>
                    </div>
                    <div className="mt-1 text-[13px] text-[color:var(--color-muted-foreground)] flex flex-wrap gap-x-4 gap-y-1">
                      <span>{r.phone || '—'}</span>
                      <span>код клиента: {r.contragent_id}</span>
                      <span>{r.registered ? 'ЛК активирован' : 'ЛК не активирован'}</span>
                    </div>
                  </div>

                  {r.recoverable ? (
                    <div className="flex items-center gap-2 shrink-0">
                      <code
                        className="px-3 py-1.5 rounded-lg text-xl font-bold tabular-nums tracking-[0.25em] select-all"
                        style={{ background: 'var(--color-control-bg)', color: 'var(--color-text)' }}
                      >
                        {shown ? r.password : '••••'}
                      </code>
                      <button className="btn btn--secondary btn--sm" onClick={() => toggleReveal(id)}>
                        {shown ? 'Скрыть' : 'Показать'}
                      </button>
                      <button
                        className="btn btn--secondary btn--sm flex items-center gap-1"
                        onClick={() => copyPin(r.password, id)}
                        title="Скопировать пароль"
                      >
                        {copiedId === id ? <Check size={14} /> : <Copy size={14} />}
                      </button>
                    </div>
                  ) : (
                    <div className="shrink-0 text-[13px] max-w-[220px]" style={{ color: 'var(--color-warning)' }}>
                      Пароль не 4-значный — восстановить из хэша нельзя. Клиенту доступен сброс пароля в ЛК.
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
