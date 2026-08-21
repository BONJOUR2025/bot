import { useEffect, useMemo, useRef, useState } from 'react';
import { Headphones, Square, CircleAlert } from 'lucide-react';
import api from '../api';

// Живое прослушивание микрофонов салонов.
//
// Модель — открытый аудиоконтроль рабочих процессов: работники уведомлены по
// ЛНА под подпись, посетители — табличками, цель и порядок зафиксированы,
// доступ ограничен правом salon-audio, каждый сеанс пишется в аудит на сервере.
// Индикатор реального времени на устройстве не обязателен (информирование
// обеспечено организационно), поэтому здесь его нет; при желании оператор
// включает физический индикатор отдельно — это опция, а не условие.
//
// Поток приходит из agent → сервер → сюда по WebSocket в WebM/Opus и играется
// через MediaSource. Микрофон салона включается только на время активного
// сеанса: сервер сигналит агенту START при первом слушателе и STOP при уходе
// последнего. Нет прослушивания — нет захвата.

function audioSalonId(salon) {
  // Ключ салона для аудио должен совпадать с salon_id в конфиге агента и
  // в salon_audio_tokens на сервере. Договорённость: это order_code салона
  // (короткий числовой id), иначе — его uuid.
  return String(salon.order_code || salon.id || '').trim();
}

function useMediaSourcePlayer() {
  const audioRef = useRef(null);
  const msRef = useRef(null);
  const sbRef = useRef(null);
  const queueRef = useRef([]);
  const wsRef = useRef(null);
  const activeRef = useRef(false);   // идёт ли сеанс (для авто-переподключения)
  const salonRef = useRef(null);
  const errRef = useRef(null);
  const reconnectRef = useRef(null);

  const pump = () => {
    const sb = sbRef.current;
    if (!sb || sb.updating || queueRef.current.length === 0) return;
    try {
      sb.appendBuffer(queueRef.current.shift());
    } catch {
      // QuotaExceeded — подрежем буфер, кадр придёт следующим проходом
      try {
        if (sb.buffered.length) {
          sb.remove(sb.buffered.start(0), Math.max(0, sb.buffered.end(sb.buffered.length - 1) - 5));
        }
      } catch { /* ignore */ }
    }
  };

  // После каждого append: держим плейхед у живого края (иначе латентность
  // растёт и звук «из кэша»), и подрезаем старое (память не течёт).
  const onUpdateEnd = () => {
    const sb = sbRef.current;
    const audio = audioRef.current;
    if (!sb) return;
    if (sb.buffered.length && audio) {
      const end = sb.buffered.end(sb.buffered.length - 1);
      if (end - audio.currentTime > 3) {
        try { audio.currentTime = end - 0.5; } catch { /* ignore */ }
      }
      if (!sb.updating) {
        const start = sb.buffered.start(0);
        const cutoff = (audio.currentTime || end) - 20;
        if (cutoff > start + 5) {
          try { sb.remove(start, cutoff); return; } catch { /* ignore */ }
        }
      }
    }
    pump();
  };

  const teardown = () => {
    if (reconnectRef.current) { clearTimeout(reconnectRef.current); reconnectRef.current = null; }
    if (wsRef.current) {
      try { wsRef.current.onclose = null; wsRef.current.close(); } catch { /* ignore */ }
      wsRef.current = null;
    }
    queueRef.current = [];
    sbRef.current = null;
    if (msRef.current) {
      try { if (msRef.current.readyState === 'open') msRef.current.endOfStream(); } catch { /* ignore */ }
      msRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.removeAttribute('src');
      audioRef.current.load();
    }
  };

  const stop = () => {
    activeRef.current = false;
    teardown();
  };

  // Один заход: свежий MediaSource + WebSocket. Используется и при старте, и при
  // авто-переподключении — после обрыва нужен НОВЫЙ поток с новым заголовком.
  const connect = () => {
    teardown();
    if (!activeRef.current || !audioRef.current) return;
    const salonId = salonRef.current;
    const onError = errRef.current;

    // Safari/WKWebView (iOS-приложение) отдаёт ManagedMediaSource, а не
    // MediaSource; на iOS < 17.1 нет ни того, ни другого.
    const MS = window.ManagedMediaSource || window.MediaSource;
    if (!MS) {
      onError?.('Прослушивание недоступно на этой версии iOS (нужен iOS 17.1+) или в этом браузере.');
      activeRef.current = false;
      return;
    }
    // ManagedMediaSource требует отключённой удалённой передачи на элементе.
    try { audioRef.current.disableRemotePlayback = true; } catch { /* ignore */ }

    const ms = new MS();
    msRef.current = ms;
    audioRef.current.src = URL.createObjectURL(ms);

    ms.addEventListener('sourceopen', () => {
      // fMP4/AAC — единый формат для desktop и iOS (WebM/Opus в Safari не играет).
      const mime = 'audio/mp4; codecs="mp4a.40.2"';
      if (MS.isTypeSupported && !MS.isTypeSupported(mime)) {
        onError?.('Браузер не поддерживает воспроизведение аудио (AAC/MP4).');
        return;
      }
      let sb;
      try {
        sb = ms.addSourceBuffer(mime);
      } catch {
        onError?.('Браузер не поддерживает воспроизведение аудио (AAC/MP4).');
        return;
      }
      sbRef.current = sb;
      sb.mode = 'sequence';
      sb.addEventListener('updateend', onUpdateEnd);

      const token = localStorage.getItem('auth_token') || '';
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const ws = new WebSocket(
        `${proto}://${location.host}/api/audio/listen/${encodeURIComponent(salonId)}?token=${encodeURIComponent(token)}`
      );
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onmessage = (ev) => {
        queueRef.current.push(new Uint8Array(ev.data));
        pump();
        audioRef.current?.play?.().catch(() => { /* автоплей может требовать жеста */ });
      };
      ws.onclose = (ev) => {
        if (ev.code === 4403) { onError?.('Нет права на прослушивание'); return; }
        if (ev.code === 4401) { onError?.('Сессия истекла, войдите заново'); return; }
        // Непредвиденный обрыв во время активного сеанса — тихо переподключаемся
        // свежим потоком (пауза, чтобы не долбить сервер).
        if (activeRef.current) {
          reconnectRef.current = setTimeout(connect, 1500);
        }
      };
      ws.onerror = () => { /* onclose доберёт */ };
    });
  };

  const start = (salonId, onError) => {
    activeRef.current = true;
    salonRef.current = salonId;
    errRef.current = onError;
    connect();
  };

  return { audioRef, start, stop };
}

function formatElapsed(totalSeconds) {
  const h = String(Math.floor(totalSeconds / 3600)).padStart(2, '0');
  const m = String(Math.floor((totalSeconds % 3600) / 60)).padStart(2, '0');
  const s = String(totalSeconds % 60).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

export default function SalonAudio() {
  const [salons, setSalons] = useState([]);
  const [statuses, setStatuses] = useState({}); // id -> {agent_online, listeners}
  const [listening, setListening] = useState(null); // id активного сеанса
  const [elapsedSec, setElapsedSec] = useState(0);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const { audioRef, start, stop } = useMediaSourcePlayer();

  // Счётчик длительности текущего сеанса — с момента, когда нажали
  // «Слушать», а не с момента появления агента в сети (сервер такое не
  // отдаёт).
  useEffect(() => {
    if (!listening) return undefined;
    setElapsedSec(0);
    const t = setInterval(() => setElapsedSec((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [listening]);

  useEffect(() => {
    api.get('/salons/')
      .then((r) => setSalons(r.data || []))
      .catch(() => setError('Не удалось загрузить список салонов'))
      .finally(() => setLoading(false));
    return () => stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Периодически опрашиваем статус агентов — чтобы кнопка «слушать» была
  // активна только там, где агент реально на связи.
  useEffect(() => {
    if (!salons.length) return;
    let cancelled = false;
    const poll = async () => {
      const next = {};
      await Promise.all(salons.map(async (s) => {
        const id = audioSalonId(s);
        if (!id) return;
        try {
          const r = await api.get(`/audio/salons/${encodeURIComponent(id)}/status`);
          next[id] = r.data;
        } catch { next[id] = { agent_online: false, listeners: 0 }; }
      }));
      if (!cancelled) setStatuses(next);
    };
    poll();
    const t = setInterval(poll, 10000);
    return () => { cancelled = true; clearInterval(t); };
  }, [salons]);

  const rows = useMemo(
    () => salons
      .map((s) => ({ salon: s, id: audioSalonId(s) }))
      .filter((r) => r.id)
      .sort((a, b) => a.salon.name.localeCompare(b.salon.name, 'ru')),
    [salons]
  );

  const onlineCount = useMemo(
    () => rows.filter(({ id }) => statuses[id]?.agent_online).length,
    [rows, statuses],
  );

  const toggle = (id) => {
    setError(null);
    if (listening === id) {
      stop();
      setListening(null);
      return;
    }
    setListening(id);
    start(id, (msg) => { setError(msg); setListening(null); stop(); });
  };

  return (
    <div className="mx-auto max-w-3xl">
      {/* Надзаголовок считает агентов на связи — это первое, что нужно
          знать на этом экране, и раньше оно читалось только перебором
          строк списка. */}
      <span className="ui-eyebrow mb-3">
        {onlineCount > 0 ? `На связи: ${onlineCount} из ${rows.length}` : 'Нет агентов на связи'}
      </span>
      <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)]">
        Прослушивание салонов
      </h2>
      <p className="mt-2 max-w-[60ch] text-sm text-[color:var(--color-text-muted)]">
        Открытый аудиоконтроль рабочих процессов. Микрофон включается только на время сеанса.
        Каждое прослушивание фиксируется в аудите: кто, какой салон и когда слушал.
      </p>

      <div className="mt-5 flex items-start gap-2.5 rounded-[var(--radius-lg)] border border-[color:var(--color-warning)] bg-[color:var(--color-warning-muted)] px-4 py-3 text-[13px] text-[color:var(--color-warning)]">
        <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.4} />
        <span>
          Использование допустимо только при выполненном основании: работники ознакомлены с ЛНА
          об аудиоконтроле под подпись, посетители уведомлены, цель и порядок зафиксированы.
          Прослушивайте лишь в предусмотренных правилами ситуациях.
        </span>
      </div>

      {error && (
        <div
          role="alert"
          className="mt-4 rounded-[var(--radius-lg)] border border-[color:var(--color-danger)] bg-[color:var(--color-danger-muted)] px-4 py-3 text-sm text-[color:var(--color-danger)]"
        >
          {error}
        </div>
      )}

      <audio ref={audioRef} className="hidden" />

      {loading ? (
        <div className="mt-5 text-[color:var(--color-text-faint)]">Загрузка…</div>
      ) : rows.length === 0 ? (
        <div className="ui-shell mt-5">
          <div className="ui-core border border-[color:var(--color-border)] bg-[color:var(--color-surface)] px-5 py-8 text-center text-[color:var(--color-text-faint)]">
            Нет салонов
          </div>
        </div>
      ) : (
        <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map(({ salon, id }) => {
            const st = statuses[id] || {};
            const online = !!st.agent_online;
            const active = listening === id;
            return (
              <div key={id} className="ui-shell">
                <div className="ui-core border border-[color:var(--color-border)] bg-[color:var(--color-surface)] px-5 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate font-medium text-[color:var(--color-text)]">
                        {salon.name}
                      </div>
                      <div className="mt-1 text-xs text-[color:var(--color-text-faint)]">
                        {online ? 'агент на связи' : 'агент офлайн'}
                        {st.listeners > 0 && <span> · слушают: {st.listeners}</span>}
                      </div>
                    </div>
                    <span className={`badge ${online ? 'badge--success' : 'badge--neutral'} shrink-0 gap-1.5`}>
                      {/* Пульсирующая точка вместо статичной иконки: в сетке
                          из шести салонов «в эфире» должно выделяться
                          движением, а не только цветом. */}
                      {online && <i className="ui-live-dot" />}
                      {online ? 'В эфире' : 'Не в сети'}
                    </span>
                  </div>

                  <div
                    className={`audio-wave mt-4 ${active ? 'is-active' : online ? 'is-idle-live' : ''}`}
                    aria-hidden="true"
                  >
                    {Array.from({ length: 28 }, (_, k) => (
                      <i
                        key={k}
                        style={{ animationDelay: `${(k * 57) % 900}ms`, animationDuration: `${900 + (k % 5) * 160}ms` }}
                      />
                    ))}
                  </div>

                  <div className="mt-4 flex items-center gap-3">
                    <button
                      onClick={() => toggle(id)}
                      disabled={!online && !active}
                      className={
                        'flex-1 inline-flex items-center justify-center gap-2 rounded-full px-4 py-2.5 text-sm font-medium transition-all duration-300 ' +
                        (active
                          ? 'bg-[color:var(--fill-danger)] text-[color:var(--color-on-fill)] hover:brightness-110'
                          : online
                            ? 'bg-[color:var(--fill-success)] text-[color:var(--color-on-fill)] hover:brightness-110'
                            : 'cursor-not-allowed bg-[color:var(--color-control-bg)] text-[color:var(--color-text-faint)]')
                      }
                    >
                      {active ? (
                        <>
                          <Square className="h-4 w-4" strokeWidth={1.4} /> Остановить
                        </>
                      ) : (
                        <>
                          <Headphones className="h-4 w-4" strokeWidth={1.4} /> Слушать
                        </>
                      )}
                    </button>
                    <span className="font-mono text-xs text-[color:var(--color-text-faint)]">
                      {active ? formatElapsed(elapsedSec) : '—'}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
