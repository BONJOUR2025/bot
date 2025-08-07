import { useState, useEffect } from 'react';
import { Send, User, MessageSquare } from 'lucide-react';
import api from '../api';

export default function Broadcast() {
  const [message, setMessage] = useState('');
  const [employees, setEmployees] = useState([]);
  const [selected, setSelected] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [selectedTpl, setSelectedTpl] = useState('');
  const [status, setStatus] = useState('active');

  useEffect(() => {
    const saved = localStorage.getItem('broadcast_draft');
    if (saved) setMessage(saved);
    api.get('messages/templates').then(r => setTemplates(r.data));
    api.get('employees/').then(r => setEmployees(r.data));
    window.refreshPage = () => {
      setMessage('');
      setSelected([]);
    };
  }, []);

  useEffect(() => {
    localStorage.setItem('broadcast_draft', message);
  }, [message]);

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
    } catch (err) {
      console.error(err);
    }
  }

  async function sendOne() {
    if (!message.trim() || selected.length === 0) return;
    for (const id of selected) {
      try {
        await api.post('telegram/send_message', {
          user_id: id,
          message,
          require_ack: true,
        });
      } catch (err) {
        console.error(err);
      }
    }
    setMessage('');
    setSelected([]);
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
        <div className="mt-2 flex gap-2">
          <select className="border p-2" value={selectedTpl} onChange={(e) => {
            const id = e.target.value; setSelectedTpl(id); const tpl = templates.find(t => t.id === id); if (tpl) setMessage(tpl.text);
          }}>
            <option value="">-- шаблон --</option>
            {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <select className="border p-2" value={status} onChange={e => setStatus(e.target.value)}>
            <option value="active">Активные</option>
            <option value="inactive">Неактивные</option>
          </select>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <button onClick={() => sendAll()} className="btn shadow">
          <Send size={16} /> Отправить всем
        </button>

        <select
          multiple
          className="flex-1 min-w-[180px] border border-gray-300 rounded px-3 py-2 shadow-sm focus:outline-none"
          value={selected}
          onChange={(e) =>
            setSelected(Array.from(e.target.selectedOptions).map((o) => o.value))
          }
        >
          {employees.map((e) => (
            <option key={e.id} value={e.id}>
              {e.full_name || e.name}
            </option>
          ))}
        </select>

        <button onClick={sendOne} className="btn bg-green-600 hover:bg-green-700 shadow">
          <User size={16} /> Отправить выбранным
        </button>

        <button onClick={() => sendAll('test')} className="btn bg-purple-600 hover:bg-purple-700 shadow">
          <Send size={16} /> Тест
        </button>
      </div>
    </div>
  );
}
