import { useState, useEffect, useMemo } from 'react';
import { Send, User, MessageSquare, Trash2, FileText } from 'lucide-react';
import api from '../api';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { groupEmployeesByPosition } from '../utils/employeeGrouping.js';

export default function Broadcast() {
  const [message, setMessage] = useState('');
  const [employees, setEmployees] = useState([]);
  const recipientsByPosition = useMemo(
    () => groupEmployeesByPosition(
      employees.filter(e => e.bot_user || e.vk_id || (!String(e.id).startsWith('nb_') && !!e.id)),
    ),
    [employees],
  );
  const [selected, setSelected] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [selectedTpl, setSelectedTpl] = useState('');
  const [status, setStatus] = useState('active');
  const [channels, setChannels] = useState(['telegram', 'vk']);
  const [openRecipients, setOpenRecipients] = useState(false);
  const [sent, setSent] = useState([]);
  const [showTemplates, setShowTemplates] = useState(false);
  const [tplName, setTplName] = useState('');
  const [tplText, setTplText] = useState('');
  const [openBroadcast, setOpenBroadcast] = useState(null);

  useEffect(() => {
    const saved = localStorage.getItem('broadcast_draft');
    if (saved) setMessage(saved);
    refreshTemplates();
    api
      .get('employees/', { params: { archived: false } })
      .then((r) => setEmployees(r.data));
    fetchSent();
    window.refreshPage = () => {
      setMessage('');
      setSelected([]);
    };
  }, []);

  useEffect(() => {
    localStorage.setItem('broadcast_draft', message);
  }, [message]);

  const generateBatchId = () => {
    if (window.crypto?.randomUUID) {
      return window.crypto.randomUUID();
    }
    return `batch-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  };

  async function refreshTemplates() {
    const r = await api.get('messages/templates');
    setTemplates(r.data);
  }

  async function fetchSent() {
    try {
      const r = await api.get('telegram/sent_messages');
      setSent(r.data);
    } catch (err) {
      console.error(err);
    }
  }

  function toggleRecipient(id) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  }

  function toggleChannel(channel) {
    setChannels((prev) =>
      prev.includes(channel) ? prev.filter((c) => c !== channel) : [...prev, channel]
    );
  }

  async function deleteMessage(id) {
    try {
      await api.delete(`telegram/sent_messages/${id}`);
      setSent((prev) => prev.filter((m) => m.id !== id));
    } catch (err) {
      console.error(err);
    }
  }

  async function createTemplate(e) {
    e.preventDefault();
    const fd = new FormData();
    fd.append('name', tplName);
    fd.append('text', tplText);
    await api.post('messages/templates', fd);
    setTplName('');
    setTplText('');
    setShowTemplates(false);
    refreshTemplates();
  }

  async function removeTemplate(id) {
    await api.delete(`messages/templates/${id}`);
    refreshTemplates();
  }

  async function sendAll(mode) {
    if (!message.trim() || channels.length === 0) return;
    if (mode !== 'test' && !window.confirm('Отправить сообщение всем?')) return;
    try {
      await api.post('telegram/broadcast', {
        message,
        status,
        channels,
        test_user_id: mode === 'test' ? selected[0] : undefined,
      });
      setMessage('');
      fetchSent();
    } catch (err) {
      console.error(err);
    }
  }

  async function sendOne() {
    if (!message.trim() || selected.length === 0 || channels.length === 0) return;
    const batchId = generateBatchId();
    for (const id of selected) {
      try {
        await api.post('telegram/send_message', {
          user_id: id,
          message,
          require_ack: true,
          batch_id: batchId,
          channels,
        });
      } catch (err) {
        console.error(err);
      }
    }
    setMessage('');
    setSelected([]);
    fetchSent();
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)] flex items-center gap-2">
        <MessageSquare size={24} /> Рассылка сообщений
      </h2>

      <div>
        <label className="block text-sm font-medium text-[color:var(--color-text)] mb-1">Текст сообщения</label>
        <textarea
          className="input w-full min-h-[100px] resize-y"
          placeholder="Введите сообщение для рассылки..."
          value={message}
          onChange={(e) => setMessage(e.target.value)}
        />
        <div className="mt-2 flex gap-2 flex-wrap">
          <button
            onClick={() => setShowTemplates(true)}
            className="btn shadow flex items-center gap-1"
          >
            <FileText size={16} /> Шаблоны
          </button>
          <select
            className="input"
            value={selectedTpl}
            onChange={(e) => {
              const id = e.target.value;
              setSelectedTpl(id);
              const tpl = templates.find((t) => t.id === id);
              if (tpl) setMessage(tpl.text);
            }}
          >
            <option value="">-- шаблон --</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <select
            className="input"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="active">Активные</option>
            <option value="inactive">Неактивные</option>
          </select>
        </div>
        <div className="mt-2 flex items-center gap-4">
          <span className="text-sm font-medium text-[color:var(--color-text)]">Куда отправить:</span>
          <label className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={channels.includes('telegram')} onChange={() => toggleChannel('telegram')} />
            Telegram
          </label>
          <label className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={channels.includes('vk')} onChange={() => toggleChannel('vk')} />
            VK
          </label>
          {channels.length === 0 && (
            <span className="text-xs text-[color:var(--color-danger)]">Выберите хотя бы один канал</span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <button onClick={() => sendAll()} disabled={channels.length === 0} className="btn shadow disabled:opacity-50">
          <Send size={16} /> Отправить всем
        </button>

        <div className="relative flex-1 min-w-[180px]">
          <button
            type="button"
            onClick={() => setOpenRecipients((o) => !o)}
            className="input w-full text-left"
          >
            {selected.length ? `Выбрано: ${selected.length}` : 'Получатели'}
          </button>
          {openRecipients && (
            <div className="absolute z-10 mt-1 w-full max-h-60 overflow-auto bg-[color:var(--color-modal-bg)] border border-[color:var(--color-border)] rounded-lg shadow-lg">
              {recipientsByPosition.map(([position, list]) => (
                <div key={position}>
                  <div className="px-2 pt-1.5 pb-0.5 text-[11px] font-semibold uppercase tracking-wide text-[color:var(--color-muted-foreground)]">
                    {position}
                  </div>
                  {list.map((e) => (
                    <label
                      key={e.id}
                      className="flex items-center px-2 py-1 gap-2"
                    >
                      <input
                        type="checkbox"
                        checked={selected.includes(e.id)}
                        onChange={() => toggleRecipient(e.id)}
                      />
                      {e.full_name || e.name}
                    </label>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

        <button
          onClick={sendOne}
          disabled={channels.length === 0}
          className="btn bg-green-600 hover:bg-green-700 shadow disabled:opacity-50"
        >
          <User size={16} /> Отправить выбранным
        </button>

        <button
          onClick={() => sendAll('test')}
          disabled={channels.length === 0}
          className="btn bg-purple-600 hover:bg-purple-700 shadow disabled:opacity-50"
        >
          <Send size={16} /> Тест
        </button>
      </div>

      <div className="mt-8">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xl font-semibold">Отправленные сообщения</h3>
          <button onClick={fetchSent} className="btn">Обновить</button>
        </div>
        <ul className="space-y-2">
          {sent.map((m) => (
            <li key={m.id} className="p-3 border rounded">
              <div className="flex justify-between items-start gap-2">
                <div className="flex-1">
                  {m.broadcast ? (
                    <button
                      onClick={() =>
                        setOpenBroadcast((prev) => (prev === m.id ? null : m.id))
                      }
                      className="font-medium text-blue-600 underline"
                    >
                      {`Рассылка ${new Date(m.timestamp).toLocaleString()}`}
                    </button>
                  ) : (
                    <>
                      <div className="font-medium whitespace-pre-wrap">{m.message}</div>
                      <div className="text-xs text-[color:var(--color-text-muted)]">
                        {new Date(m.timestamp).toLocaleString()} — {m.status}
                      </div>
                    </>
                  )}
                </div>
                <button
                  onClick={() => deleteMessage(m.id)}
                  className="text-red-600 hover:text-red-800"
                >
                  <Trash2 size={16} />
                </button>
              </div>
              {m.broadcast && openBroadcast === m.id && (
                <div className="mt-2">
                  <div className="font-medium whitespace-pre-wrap mb-2">{m.message}</div>
                  <ResponsiveTable
                    data={m.recipients || []}
                    keyFn={(r) => `${r.user_id}_${r.channel}`}
                    emptyText="Нет получателей"
                    columns={[
                      { label: 'Получатель', key: 'name', primary: true },
                      { label: 'Канал', render: (r) => r.channel === 'telegram' ? 'Telegram' : r.channel === 'vk' ? 'VK' : (r.channel || '—') },
                      { label: 'Статус', key: 'status' },
                    ]}
                  />
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>
      {showTemplates && (
        <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setShowTemplates(false)}>
          <div className="modal-card max-w-lg">
            <h3 className="text-xl font-semibold">Шаблоны</h3>
            <ul className="space-y-1 mb-4 max-h-40 overflow-auto">
              {templates.map((t) => (
                <li
                  key={t.id}
                  className="flex justify-between items-center border-b py-1"
                >
                  <span>{t.name}</span>
                  <button
                    onClick={() => removeTemplate(t.id)}
                    className="text-red-600 hover:text-red-800"
                  >
                    <Trash2 size={16} />
                  </button>
                </li>
              ))}
            </ul>
            <form onSubmit={createTemplate} className="space-y-2">
              <input
                className="modal-control"
                placeholder="Название"
                value={tplName}
                onChange={(e) => setTplName(e.target.value)}
              />
              <textarea
                className="modal-control"
                placeholder="Текст"
                value={tplText}
                onChange={(e) => setTplText(e.target.value)}
              />
              <button
                type="submit"
                className="btn w-full bg-green-600 hover:bg-green-700 text-white"
              >
                Добавить
              </button>
            </form>
            <button
              onClick={() => setShowTemplates(false)}
              className="btn w-full mt-1 bg-[color:var(--color-control-bg)] text-[color:var(--color-text)] hover:bg-[color:var(--color-control-bg-hover)]"
            >
              Закрыть
            </button>
          </div>
        </div>
      )}
    </div>
  );
}





