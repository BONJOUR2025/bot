import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeft, Pencil, FileDown, Archive, ExternalLink,
  Phone, CreditCard, MapPin, Shirt, Cake, StickyNote,
  ShieldCheck, Building2, MessageCircle, Hash, FileText, Upload,
} from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

function InfoRow({ icon: Icon, label, value }) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-[color:var(--color-border)] last:border-0">
      {Icon && <Icon size={15} className="mt-0.5 shrink-0 text-[color:var(--color-muted-foreground)]" />}
      <span className="text-sm text-[color:var(--color-muted-foreground)] w-28 sm:w-36 shrink-0">{label}</span>
      <span className="text-sm font-medium break-words min-w-0">{value}</span>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="app-card p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-3">{title}</div>
      {children}
    </div>
  );
}

export default function AdminEmployeeProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [employee, setEmployee] = useState(null);
  const [cashierChats, setCashierChats] = useState([]);
  const [loading, setLoading] = useState(true);
  const passportInputRef = useRef(null);

  useEffect(() => {
    Promise.all([
      api.get(`employees/${id}`),
      api.get('config/'),
    ])
      .then(([empRes, cfgRes]) => {
        setEmployee(empRes.data);
        const data = cfgRes.data || {};
        const rawChats = Array.isArray(data.card_dispatch_chats) ? data.card_dispatch_chats : [];
        const normalized = rawChats
          .map((chat, idx) => {
            if (typeof chat !== 'object' || chat === null) return null;
            const chatId = Number(chat.chat_id ?? chat.id);
            if (!Number.isFinite(chatId)) return null;
            const key = String(chat.key ?? chat.id ?? `chat_${idx + 1}`);
            const name = String(chat.name ?? `Кассир ${idx + 1}`);
            return { key, name, chat_id: chatId };
          })
          .filter(Boolean);
        const fallbackId = Number(data.card_dispatch_chat_id);
        if (!normalized.length && Number.isFinite(fallbackId) && fallbackId !== 0) {
          normalized.push({ key: 'default', name: 'Основной кассир', chat_id: fallbackId });
        }
        setCashierChats(normalized);
      })
      .catch(() => toast('Ошибка загрузки профиля', 'error'))
      .finally(() => setLoading(false));
  }, [id]);

  function resolveChatName(key) {
    if (!cashierChats.length) return key || '';
    if (!key) {
      const first = cashierChats[0];
      return first ? `По умолчанию — ${first.name}` : 'По умолчанию';
    }
    const found = cashierChats.find((c) => c.key === key);
    return found ? found.name : `Неизвестный чат (${key})`;
  }

  function formatDate(val) {
    if (!val) return '';
    return new Date(val).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
  }

  async function uploadPassport(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await api.post(`employees/${id}/passport`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setEmployee(prev => ({ ...prev, passport_url: res.data?.passport_url || prev.passport_url }));
      toast('Паспорт загружен', 'success');
    } catch { toast('Ошибка загрузки паспорта', 'error'); }
  }

  async function archiveEmployee() {
    if (employee?.status === 'active') {
      toast('Сначала переведите статус в inactive', 'warning');
      return;
    }
    if (!window.confirm('Перенести сотрудника в архив?')) return;
    try {
      await api.post(`employees/${id}/archive`);
      toast('Сотрудник перемещён в архив', 'success');
      navigate('/admin/employees');
    } catch { toast('Ошибка архивирования', 'error'); }
  }

  if (loading) {
    return (
      <div className="space-y-6 max-w-2xl">
        <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-sm text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-text-primary)]">
          <ArrowLeft size={15} /> Назад
        </button>
        <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)] text-sm">Загрузка…</div>
      </div>
    );
  }

  if (!employee) {
    return (
      <div className="space-y-4 max-w-2xl">
        <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-sm text-[color:var(--color-muted-foreground)]">
          <ArrowLeft size={15} /> Назад
        </button>
        <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)] text-sm">Сотрудник не найден</div>
      </div>
    );
  }

  const canArchive = employee.status !== 'active';

  return (
    <div className="space-y-5 max-w-2xl">
      {/* Back + actions */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <button
          onClick={() => navigate('/admin/employees')}
          className="flex items-center gap-1.5 text-sm text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-text-primary)] transition-colors"
        >
          <ArrowLeft size={15} /> Сотрудники
        </button>
        <div className="flex items-center gap-2">
          <a
            href={`/api/employees/${id}/profile.pdf`}
            className="btn flex items-center gap-1.5 text-sm"
            title="Скачать PDF"
          >
            <FileDown size={15} /> PDF
          </a>
          <button
            className={`btn flex items-center gap-1.5 text-sm ${canArchive ? 'text-amber-600 hover:bg-amber-50' : 'opacity-40 cursor-not-allowed'}`}
            onClick={archiveEmployee}
            disabled={!canArchive}
            title={canArchive ? 'В архив' : 'Сначала переведите в inactive'}
          >
            <Archive size={15} /> В архив
          </button>
        </div>
      </div>

      {/* Header card */}
      <div className="app-card p-5">
      <div className="flex items-center gap-4">
        {employee.photo_url ? (
          <img
            src={employee.photo_url}
            alt={employee.name}
            className="w-16 h-16 rounded-full object-cover shrink-0 cursor-pointer"
            onClick={() => window.open(employee.photo_url, '_blank')}
          />
        ) : (
          <div className="w-16 h-16 rounded-full bg-[color:var(--color-bg-secondary)] flex items-center justify-center shrink-0 text-2xl font-semibold text-[color:var(--color-muted-foreground)]">
            {(employee.full_name || employee.name || '?')[0].toUpperCase()}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="text-xl font-semibold leading-tight">{employee.full_name || employee.name}</div>
          {employee.position && <div className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">{employee.position}</div>}
          <div className="flex flex-wrap gap-2 mt-2">
            {employee.is_admin && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700 border border-orange-200">
                <ShieldCheck size={11} /> Администратор
              </span>
            )}
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${employee.status === 'active' ? 'bg-green-100 text-green-700 border-green-200' : 'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)] border-[color:var(--color-border)]'}`}>
              {employee.status === 'active' ? 'Активен' : 'Неактивен'}
            </span>
          </div>
        </div>
        <Link
          to={`/admin/employees`}
          state={{ editId: employee.id }}
          className="btn flex items-center gap-1.5 text-sm shrink-0"
          onClick={(e) => {
            e.preventDefault();
            navigate('/admin/employees', { state: { editId: employee.id } });
          }}
        >
          <Pencil size={14} /> Редактировать
        </Link>
      </div>
      </div>

      {/* Details */}
      <Section title="Контакты">
        <InfoRow icon={Phone} label="Телефон" value={employee.phone} />
        <InfoRow icon={CreditCard} label="Номер карты" value={employee.card_number} />
        <InfoRow icon={Building2} label="Банк" value={employee.bank} />
      </Section>

      <Section title="О сотруднике">
        <InfoRow icon={MapPin} label="Место работы" value={employee.work_place} />
        <InfoRow icon={Shirt} label="Размер одежды" value={employee.clothing_size} />
        <InfoRow icon={Cake} label="День рождения" value={formatDate(employee.birthdate)} />
        <InfoRow icon={MessageCircle} label="Чат кассира" value={resolveChatName(employee.payout_chat_key)} />
        {employee.note && <InfoRow icon={StickyNote} label="Заметка" value={employee.note} />}
      </Section>

      <Section title="Системная информация">
        <InfoRow label="ID" value={employee.id} />
        {employee.external_code && <InfoRow icon={Hash} label="Внешний код" value={employee.external_code} />}
        <InfoRow label="Создан" value={employee.created_at ? new Date(employee.created_at).toLocaleString('ru-RU') : ''} />
      </Section>

      <Section title="Документы">
        <div className="flex flex-wrap items-center gap-3 py-1">
          {employee.passport_url ? (
            <a
              href={employee.passport_url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn flex items-center gap-1.5 text-sm"
            >
              <FileText size={14} /> Скан паспорта
            </a>
          ) : (
            <span className="text-sm text-[color:var(--color-muted-foreground)]">Скан паспорта не загружен</span>
          )}
          <button
            className="btn flex items-center gap-1.5 text-sm"
            onClick={() => passportInputRef.current?.click()}
          >
            <Upload size={14} /> {employee.passport_url ? 'Обновить паспорт' : 'Загрузить паспорт'}
          </button>
          <input
            ref={passportInputRef}
            type="file"
            accept="image/*,application/pdf"
            className="hidden"
            onChange={uploadPassport}
          />
        </div>
      </Section>

      {/* Related links */}
      <Section title="Связанные разделы">
        <div className="flex flex-wrap gap-2 pt-1">
          <a
            href={`/admin/incentives?employee_id=${employee.id}`}
            className="btn flex items-center gap-1.5 text-sm"
          >
            <ExternalLink size={13} /> История начислений
          </a>
          <a
            href={`/admin/payroll`}
            className="btn flex items-center gap-1.5 text-sm"
          >
            <ExternalLink size={13} /> Расчёт зарплаты
          </a>
          <Link
            to={`/admin/masters?master=${encodeURIComponent(employee.full_name || employee.name)}`}
            className="btn flex items-center gap-1.5 text-sm"
          >
            <ExternalLink size={13} /> Работы мастера
          </Link>
        </div>
      </Section>
    </div>
  );
}
