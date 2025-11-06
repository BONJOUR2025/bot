import { useState, useEffect } from 'react';
import { Send, User, MessageSquare, Trash2, FileText } from 'lucide-react';
import api from '../api';

export default function Broadcast() {
  const [message, setMessage] = useState('');
  const [employees, setEmployees] = useState([]);
  const [selected, setSelected] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [selectedTpl, setSelectedTpl] = useState('');
  const [status, setStatus] = useState('active');
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
    api.get('employees/').then((r) => setEmployees(r.data));
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
    if (!message.trim()) return;
    if (mode !== 'test' && !window.confirm('Отправить сообщение всем?')) return;
    try {
      await api.post('telegram/broadcast', {
        message,
        status,
        test_user_id: mode === 'test' ? selected[0] : undefined,
      });
      setMessage('');
      fetchSent();
    } catch (err) {
      console.error(err);
    }
  }

  async function sendOne() {
    if (!message.trim() || selected.length === 0) return;
    const batchId = generateBatchId();
    for (const id of selected) {
      try {
        await api.post('telegram/send_message', {
          user_id: id,
          message,
          require_ack: true,
          batch_id: batchId,
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
      <h2 className="text-2xl font-semibold tracking-tight text-gray-800 flex items-center gap-2">
        <MessageSquare size={24} /> Рассылка сообщений
      </h2>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Текст сообщения</label>
        <textarea
          className="w-full min-h-[100px] p-3 border border-gray-300 rounded shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
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
            className="border p-2"
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
            className="border p-2"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="active">Активные</option>
            <option value="inactive">Неактивные</option>
          </select>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <button onClick={() => sendAll()} className="btn shadow">
          <Send size={16} /> Отправить всем
        </button>

        <div className="relative flex-1 min-w-[180px]">
          <button
            type="button"
            onClick={() => setOpenRecipients((o) => !o)}
            className="w-full border border-gray-300 rounded px-3 py-2 shadow-sm text-left"
          >
            {selected.length ? `Выбрано: ${selected.length}` : 'Получатели'}
          </button>
          {openRecipients && (
            <div className="absolute z-10 mt-1 w-full max-h-60 overflow-auto bg-white border border-gray-300 rounded shadow">
              {employees.map((e) => (
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
          )}
        </div>

        <button
          onClick={sendOne}
          className="btn bg-green-600 hover:bg-green-700 shadow"
        >
          <User size={16} /> Отправить выбранным
        </button>

        <button
          onClick={() => sendAll('test')}
          className="btn bg-purple-600 hover:bg-purple-700 shadow"
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
                      <div className="text-xs text-gray-500">
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
                  <table className="w-full text-sm border">
                    <thead>
                      <tr className="bg-gray-100">
                        <th className="text-left p-1 border">Получатель</th>
                        <th className="text-left p-1 border">Статус</th>
                      </tr>
                    </thead>
                    <tbody>
                      {m.recipients?.map((r) => (
                        <tr key={r.user_id}>
                          <td className="p-1 border">{r.name}</td>
                          <td className="p-1 border">{r.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>
      {showTemplates && (
        <div className="modal-backdrop">
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
              className="btn w-full mt-1 bg-gray-200 text-gray-700 hover:bg-gray-300"
            >
              Закрыть
            </button>
          </div>
        </div>
      )}
    </div>
  );
}





