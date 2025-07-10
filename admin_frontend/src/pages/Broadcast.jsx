import { useState, useEffect } from 'react';
import { Send, User, MessageSquare } from 'lucide-react';
import api from '../api';

export default function Broadcast() {
  const [message, setMessage] = useState('');
  const [chatId, setChatId] = useState('');

  useEffect(() => {
    window.refreshPage = () => {
      setMessage('');
      setChatId('');
    };
  }, []);

  async function sendAll() {
    if (!message.trim()) return;
    if (!window.confirm('Отправить сообщение всем?')) return;
    try {
      await api.post('telegram/broadcast', { message });
      setMessage('');
    } catch (err) {
      console.error(err);
    }
  }

  async function sendOne() {
    if (!message.trim() || !chatId.trim()) return;
    try {
      await api.post('telegram/send_message', {
        user_id: chatId,
        message,
      });
      setMessage('');
    } catch (err) {
      console.error(err);
    }
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
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          onClick={sendAll}
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded shadow hover:bg-blue-700"
        >
          <Send size={16} /> Отправить всем
        </button>

        <input
          className="flex-1 min-w-[180px] border border-gray-300 rounded px-3 py-2 shadow-sm focus:outline-none"
          placeholder="Chat ID получателя"
          value={chatId}
          onChange={(e) => setChatId(e.target.value)}
        />

        <button
          onClick={sendOne}
          className="inline-flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded shadow hover:bg-green-700"
        >
          <User size={16} /> Отправить одному
        </button>
      </div>
    </div>
  );
}
