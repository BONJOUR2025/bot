import { useEffect, useMemo, useRef, useState } from 'react';
import { Headphones, Square, Radio, CircleAlert } from 'lucide-react';
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

  const pump = () => {
    const sb = sbRef.current;
    if (!sb || sb.updating || queueRef.current.length === 0) return;
    try {
      sb.appendBuffer(queueRef.current.shift());
    } catch (e) {
      // QuotaExceeded и подобное — подрежем буфер и попробуем снова
      try {
        if (sb.buffered.length) {
          sb.remove(0, Math.max(0, sb.buffered.end(0) - 2));
        }
      } catch { /* ignore */ }
    }
  };

  const stop = () => {
    if (wsRef.current) {
      try { wsRef.current.close(); } catch { /* ignore */ }
      wsRef.current = null;
    }
    queueRef.current = [];
    sbRef.current = null;
    if (msRef.current) {
      try {
        if (msRef.current.readyState === 'open') msRef.current.endOfStream();
      } catch { /* ignore */ }
      msRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.removeAttribute('src');
      audioRef.current.load();
    }
  };

  const start = (salonId, onError) => {
    stop();
    const ms = new MediaSource();
    msRef.current = ms;
    audioRef.current.src = URL.createObjectURL(ms);

    ms.addEventListener('sourceopen', () => {
      let sb;
      try {
        sb = ms.addSourceBuffer('audio/webm; codecs="opus"');
      } catch (e) {
        onError?.('Браузер не поддерживает WebM/Opus в MediaSource');
        return;
      }
      sbRef.current = sb;
      sb.mode = 'sequence';
      sb.addEventListener('updateend', pump);

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
        if (ev.code === 4403) onError?.('Нет права на прослушивание');
        else if (ev.code === 4401) onError?.('Сессия истекла, войдите заново');
      };
      ws.onerror = () => onError?.('Обрыв соединения с сервером');
    });
  };

  return { audioRef, start, stop };
}

export default function SalonAudio() {
  const [salons, setSalons] = useState([]);
  const [statuses, setStatuses] = useState({}); // id -> {agent_online, listeners}
  const [listening, setListening] = useState(null); // id активного сеанса
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const { audioRef, start, stop } = useMediaSourcePlayer();

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
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-1">
        <Headphones className="w-6 h-6 text-slate-500" />
        <h1 className="text-2xl font-semibold">Прослушивание салонов</h1>
      </div>
      <p className="text-sm text-slate-500 mb-4">
        Открытый аудиоконтроль рабочих процессов. Микрофон включается только на
        время сеанса. Каждое прослушивание фиксируется в аудите: кто, какой
        салон и когда слушал.
      </p>

      <div className="flex items-start gap-2 mb-5 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
        <CircleAlert className="w-4 h-4 mt-0.5 shrink-0" />
        <span>
          Использование допустимо только при выполненном основании: работники
          ознакомлены с ЛНА об аудиоконтроле под подпись, посетители уведомлены,
          цель и порядок зафиксированы. Прослушивайте лишь в предусмотренных
          правилами ситуациях.
        </span>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <audio ref={audioRef} className="hidden" />

      {loading ? (
        <div className="text-slate-400">Загрузка…</div>
      ) : (
        <div className="divide-y rounded-lg border border-slate-200 bg-white">
          {rows.map(({ salon, id }) => {
            const st = statuses[id] || {};
            const online = !!st.agent_online;
            const active = listening === id;
            return (
              <div key={id} className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <div className="font-medium text-slate-800 truncate">{salon.name}</div>
                  <div className="text-xs text-slate-400 flex items-center gap-2 mt-0.5">
                    {online ? (
                      <span className="inline-flex items-center gap-1 text-emerald-600">
                        <Radio className="w-3 h-3" /> агент на связи
                      </span>
                    ) : (
                      <span className="text-slate-400">агент офлайн</span>
                    )}
                    {st.listeners > 0 && (
                      <span className="text-slate-400">· слушают: {st.listeners}</span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => toggle(id)}
                  disabled={!online && !active}
                  className={
                    'inline-flex items-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium transition ' +
                    (active
                      ? 'bg-red-600 text-white hover:bg-red-700'
                      : online
                        ? 'bg-slate-800 text-white hover:bg-slate-900'
                        : 'bg-slate-100 text-slate-400 cursor-not-allowed')
                  }
                >
                  {active ? (<><Square className="w-4 h-4" /> Остановить</>)
                          : (<><Headphones className="w-4 h-4" /> Слушать</>)}
                </button>
              </div>
            );
          })}
          {rows.length === 0 && (
            <div className="px-4 py-6 text-center text-slate-400">Нет салонов</div>
          )}
        </div>
      )}
    </div>
  );
}
