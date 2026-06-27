import { useState, useEffect, useMemo } from 'react';
import api from '../api';
import { useViewport } from '../providers/ViewportProvider.jsx';

// ── Status config ────────────────────────────────────────────────
const STATUS = {
  active:     { label: 'Работает',   cls: 'bg-emerald-100 text-emerald-700' },
  renovation: { label: 'Ремонт',     cls: 'bg-amber-100 text-amber-700' },
  closed:     { label: 'Закрыт',     cls: 'bg-red-100 text-red-700' },
};

const POINT_TYPE_OPTIONS = ['ТЦ', 'Улица', 'Рынок', 'Другое'];
const STATUS_OPTIONS = Object.entries(STATUS).map(([k, v]) => ({ value: k, label: v.label }));

const TABS = [
  { key: 'main',    label: 'Основное' },
  { key: 'legal',   label: 'Юридическое' },
  { key: 'staff',   label: 'Персонал' },
  { key: 'tc',      label: 'Арендодатель' },
  { key: 'notes',   label: 'Заметки' },
];

// ── Helpers ──────────────────────────────────────────────────────
function Badge({ status }) {
  const cfg = STATUS[status] || STATUS.active;
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${cfg.cls}`}>
      {cfg.label}
    </span>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <div className="text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">{label}</div>
      <div className="text-sm">{children || <span className="text-[color:var(--color-muted-foreground)] italic">—</span>}</div>
    </div>
  );
}

function InputField({ label, name, value, onChange, type = 'text', placeholder = '' }) {
  return (
    <div>
      <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">{label}</label>
      <input
        type={type}
        name={name}
        value={value ?? ''}
        onChange={onChange}
        placeholder={placeholder}
        className="input w-full text-sm"
      />
    </div>
  );
}

function TextAreaField({ label, name, value, onChange, rows = 3, placeholder = '' }) {
  return (
    <div>
      <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">{label}</label>
      <textarea
        name={name}
        value={value ?? ''}
        onChange={onChange}
        rows={rows}
        placeholder={placeholder}
        className="input w-full text-sm resize-none"
      />
    </div>
  );
}

function SelectField({ label, name, value, onChange, options }) {
  return (
    <div>
      <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">{label}</label>
      <select name={name} value={value ?? ''} onChange={onChange} className="input w-full text-sm">
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

// ── Empty form state ─────────────────────────────────────────────
function emptyForm() {
  return {
    name: '', code: '', address: '', phone: '',
    status: 'active', point_type: 'ТЦ',
    area_sqm: '', opening_date: '',
    work_hours_weekday: '', work_hours_weekend: '',
    legal_entity: '',
    employees: [],
    tc_name: '', tc_contacts: [],
    rent_rate: '', rent_payment_day: '', rent_notes: '',
    notes: '',
  };
}

function salonToForm(s) {
  return {
    name: s.name ?? '',
    code: s.code ?? '',
    address: s.address ?? '',
    phone: s.phone ?? '',
    status: s.status ?? 'active',
    point_type: s.point_type ?? 'ТЦ',
    area_sqm: s.area_sqm ?? '',
    opening_date: s.opening_date ?? '',
    work_hours_weekday: s.work_hours_weekday ?? '',
    work_hours_weekend: s.work_hours_weekend ?? '',
    legal_entity: s.legal_entity ?? '',
    employees: s.employees ?? [],
    tc_name: s.tc_name ?? '',
    tc_contacts: s.tc_contacts ?? [],
    rent_rate: s.rent_rate ?? '',
    rent_payment_day: s.rent_payment_day ?? '',
    rent_notes: s.rent_notes ?? '',
    notes: s.notes ?? '',
  };
}

// ── TC Contact sub-form ──────────────────────────────────────────
function ContactRow({ contact, index, onChange, onRemove }) {
  function handleChange(e) {
    onChange(index, { ...contact, [e.target.name]: e.target.value });
  }
  return (
    <div className="rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-muted)]/30 p-3 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <input name="name"  value={contact.name  ?? ''} onChange={handleChange} placeholder="Имя" className="input text-sm" />
        <input name="role"  value={contact.role  ?? ''} onChange={handleChange} placeholder="Должность" className="input text-sm" />
        <input name="phone" value={contact.phone ?? ''} onChange={handleChange} placeholder="Телефон" className="input text-sm" />
        <input name="email" value={contact.email ?? ''} onChange={handleChange} placeholder="Email" className="input text-sm" />
      </div>
      <button onClick={() => onRemove(index)} className="text-xs text-red-500 hover:text-red-700">Удалить контакт</button>
    </div>
  );
}

// ── Modal / Drawer ────────────────────────────────────────────────
function SalonModal({ salon, employees, onSave, onClose }) {
  const isNew = !salon;
  const [form, setForm] = useState(isNew ? emptyForm() : salonToForm(salon));
  const [tab, setTab] = useState('main');
  const [saving, setSaving] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm(f => ({ ...f, [name]: value }));
  }

  function handleEmployeeToggle(code) {
    setForm(f => {
      const next = new Set(f.employees);
      next.has(code) ? next.delete(code) : next.add(code);
      return { ...f, employees: [...next] };
    });
  }

  function handleContactChange(idx, contact) {
    setForm(f => {
      const tc_contacts = [...f.tc_contacts];
      tc_contacts[idx] = contact;
      return { ...f, tc_contacts };
    });
  }

  function handleContactRemove(idx) {
    setForm(f => ({ ...f, tc_contacts: f.tc_contacts.filter((_, i) => i !== idx) }));
  }

  function handleAddContact() {
    setForm(f => ({ ...f, tc_contacts: [...f.tc_contacts, { name: '', role: '', phone: '', email: '' }] }));
  }

  async function handleSave() {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const payload = {
        ...form,
        area_sqm: form.area_sqm !== '' ? parseFloat(form.area_sqm) : null,
        rent_rate: form.rent_rate !== '' ? parseFloat(form.rent_rate) : null,
        rent_payment_day: form.rent_payment_day !== '' ? parseInt(form.rent_payment_day) : null,
        opening_date: form.opening_date || null,
      };
      await onSave(payload, salon?.id);
    } finally {
      setSaving(false);
    }
  }

  const empByCode = useMemo(() => {
    const m = {};
    (employees || []).forEach(e => { m[e.id] = e; });
    return m;
  }, [employees]);

  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-2xl w-full flex flex-col overflow-hidden" style={{ maxHeight: '90vh' }}>
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-[color:var(--color-border)]">
          <h3 className="text-lg font-bold">{isNew ? 'Новый салон' : form.name}</h3>
          <button onClick={onClose} className="text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] text-xl leading-none">&times;</button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 pt-4 pb-2 border-b border-[color:var(--color-border)] overflow-x-auto">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
                tab === t.key
                  ? 'bg-[color:var(--color-primary)] text-white'
                  : 'text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-muted)]'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto py-4 space-y-4">

          {tab === 'main' && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <InputField label="Название *" name="name" value={form.name} onChange={handleChange} placeholder="Пассаж" />
                <InputField label="Код точки" name="code" value={form.code} onChange={handleChange} placeholder="П" />
              </div>
              <InputField label="Адрес" name="address" value={form.address} onChange={handleChange} placeholder="Лиговский пр., 30" />
              <div className="grid grid-cols-2 gap-3">
                <InputField label="Телефон" name="phone" value={form.phone} onChange={handleChange} placeholder="+7 (812) 000-00-00" />
                <SelectField
                  label="Статус"
                  name="status"
                  value={form.status}
                  onChange={handleChange}
                  options={STATUS_OPTIONS}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <SelectField
                  label="Тип точки"
                  name="point_type"
                  value={form.point_type}
                  onChange={handleChange}
                  options={POINT_TYPE_OPTIONS.map(o => ({ value: o, label: o }))}
                />
                <InputField label="Площадь, м²" name="area_sqm" type="number" value={form.area_sqm} onChange={handleChange} placeholder="25" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <InputField label="Часы работы (будни)" name="work_hours_weekday" value={form.work_hours_weekday} onChange={handleChange} placeholder="10:00–21:00" />
                <InputField label="Часы работы (вых.)" name="work_hours_weekend" value={form.work_hours_weekend} onChange={handleChange} placeholder="10:00–20:00" />
              </div>
              <InputField label="Дата открытия" name="opening_date" type="date" value={form.opening_date} onChange={handleChange} />
            </div>
          )}

          {tab === 'legal' && (
            <div className="space-y-4">
              <InputField label="Юридическое лицо" name="legal_entity" value={form.legal_entity} onChange={handleChange} placeholder='ООО "Бонжур"' />
              <div className="grid grid-cols-2 gap-3">
                <InputField label="Ставка аренды (₽/м²/мес)" name="rent_rate" type="number" value={form.rent_rate} onChange={handleChange} placeholder="2500" />
                <InputField label="День оплаты аренды" name="rent_payment_day" type="number" value={form.rent_payment_day} onChange={handleChange} placeholder="10" />
              </div>
              <TextAreaField label="Условия аренды / примечания" name="rent_notes" value={form.rent_notes} onChange={handleChange} rows={4} placeholder="Договор №..., особые условия..." />
            </div>
          )}

          {tab === 'staff' && (
            <div className="space-y-3">
              <p className="text-sm text-[color:var(--color-muted-foreground)]">Выберите сотрудников, закреплённых за этим салоном:</p>
              <div className="space-y-1 max-h-80 overflow-y-auto pr-1">
                {(employees || []).filter(e => !e.archived).map(emp => (
                  <label key={emp.id} className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-[color:var(--color-muted)]/50 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.employees.includes(emp.id)}
                      onChange={() => handleEmployeeToggle(emp.id)}
                      className="accent-[color:var(--color-primary)] h-4 w-4"
                    />
                    <span className="text-sm font-medium">{emp.name}</span>
                    {emp.position && <span className="text-xs text-[color:var(--color-muted-foreground)]">{emp.position}</span>}
                  </label>
                ))}
                {(!employees || employees.length === 0) && (
                  <p className="text-sm text-[color:var(--color-muted-foreground)] italic py-4 text-center">Нет сотрудников в системе</p>
                )}
              </div>
            </div>
          )}

          {tab === 'tc' && (
            <div className="space-y-4">
              <InputField label="Название ТЦ / арендодателя" name="tc_name" value={form.tc_name} onChange={handleChange} placeholder="ТЦ Галерея" />
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-[color:var(--color-muted-foreground)]">Контактные лица администрации</span>
                  <button onClick={handleAddContact} className="text-xs text-[color:var(--color-primary)] hover:underline font-medium">+ Добавить</button>
                </div>
                <div className="space-y-2">
                  {form.tc_contacts.map((c, i) => (
                    <ContactRow key={i} contact={c} index={i} onChange={handleContactChange} onRemove={handleContactRemove} />
                  ))}
                  {form.tc_contacts.length === 0 && (
                    <p className="text-sm text-[color:var(--color-muted-foreground)] italic text-center py-3">Контакты не добавлены</p>
                  )}
                </div>
              </div>
            </div>
          )}

          {tab === 'notes' && (
            <TextAreaField label="Примечания" name="notes" value={form.notes} onChange={handleChange} rows={8} placeholder="Свободные заметки, особенности, история..." />
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 pt-4 border-t border-[color:var(--color-border)]">
          <button onClick={onClose} className="btn btn-secondary">Отмена</button>
          <button onClick={handleSave} disabled={saving || !form.name.trim()} className="btn btn-primary">
            {saving ? 'Сохранение...' : (isNew ? 'Создать' : 'Сохранить')}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Salon Card ────────────────────────────────────────────────────
function SalonCard({ salon, employees, onClick }) {
  const empMap = useMemo(() => {
    const m = {};
    (employees || []).forEach(e => { m[e.id] = e; });
    return m;
  }, [employees]);

  const assignedNames = (salon.employees || [])
    .map(id => empMap[id]?.name || id)
    .slice(0, 3);

  return (
    <div
      onClick={onClick}
      className="card p-5 cursor-pointer hover:shadow-md transition-shadow group"
    >
      {/* Top row */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          {salon.code && (
            <span className="flex-shrink-0 w-8 h-8 rounded-lg bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] text-sm font-bold flex items-center justify-center">
              {salon.code}
            </span>
          )}
          <h3 className="font-semibold text-base truncate group-hover:text-[color:var(--color-primary)] transition-colors">{salon.name}</h3>
        </div>
        <Badge status={salon.status} />
      </div>

      {/* Info rows */}
      <div className="space-y-1.5 text-sm text-[color:var(--color-muted-foreground)]">
        {salon.address && (
          <div className="flex items-start gap-2">
            <span className="mt-px flex-shrink-0">📍</span>
            <span className="line-clamp-1">{salon.address}</span>
          </div>
        )}
        {(salon.work_hours_weekday || salon.work_hours_weekend) && (
          <div className="flex items-center gap-2">
            <span>🕐</span>
            <span>{[salon.work_hours_weekday, salon.work_hours_weekend].filter(Boolean).join(' / ')}</span>
          </div>
        )}
        {salon.phone && (
          <div className="flex items-center gap-2">
            <span>📞</span>
            <span>{salon.phone}</span>
          </div>
        )}
        {salon.legal_entity && (
          <div className="flex items-center gap-2">
            <span>🏢</span>
            <span className="truncate">{salon.legal_entity}</span>
          </div>
        )}
      </div>

      {/* Staff chips */}
      {assignedNames.length > 0 && (
        <div className="mt-3 pt-3 border-t border-[color:var(--color-border)] flex flex-wrap gap-1">
          {assignedNames.map((n, i) => (
            <span key={i} className="inline-block bg-[color:var(--color-muted)] text-[color:var(--color-muted-foreground)] rounded-full px-2 py-0.5 text-xs">{n}</span>
          ))}
          {salon.employees.length > 3 && (
            <span className="inline-block bg-[color:var(--color-muted)] text-[color:var(--color-muted-foreground)] rounded-full px-2 py-0.5 text-xs">+{salon.employees.length - 3}</span>
          )}
        </div>
      )}
    </div>
  );
}

// ── Detail Drawer ────────────────────────────────────────────────
function SalonDrawer({ salon, employees, onEdit, onDelete, onClose }) {
  const [tab, setTab] = useState('main');
  const [confirmDelete, setConfirmDelete] = useState(false);

  const empMap = useMemo(() => {
    const m = {};
    (employees || []).forEach(e => { m[e.id] = e; });
    return m;
  }, [employees]);

  const assignedEmps = (salon.employees || []).map(id => empMap[id]).filter(Boolean);

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end backdrop-blur-sm"
      style={{ background: 'var(--color-modal-backdrop)' }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="w-full max-w-lg bg-[color:var(--color-modal-bg)] shadow-2xl flex flex-col h-full overflow-hidden border-l border-[color:var(--color-border)]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-[color:var(--color-border)]">
          <div className="flex items-center gap-3 min-w-0">
            {salon.code && (
              <span className="flex-shrink-0 w-10 h-10 rounded-xl bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] font-bold text-base flex items-center justify-center">
                {salon.code}
              </span>
            )}
            <div className="min-w-0">
              <h2 className="font-bold text-lg truncate">{salon.name}</h2>
              <Badge status={salon.status} />
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button onClick={onEdit} className="btn btn-secondary text-sm">Изменить</button>
            <button onClick={onClose} className="text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] text-xl">&times;</button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-6 py-3 border-b border-[color:var(--color-border)] overflow-x-auto">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
                tab === t.key
                  ? 'bg-[color:var(--color-primary)] text-white'
                  : 'text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-muted)]'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">

          {tab === 'main' && (
            <div className="space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <Field label="Тип точки">{salon.point_type}</Field>
                <Field label="Площадь">{salon.area_sqm ? `${salon.area_sqm} м²` : null}</Field>
              </div>
              <Field label="Адрес">{salon.address}</Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Телефон">{salon.phone}</Field>
                <Field label="Дата открытия">{salon.opening_date}</Field>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Часы (будни)">{salon.work_hours_weekday}</Field>
                <Field label="Часы (вых.)">{salon.work_hours_weekend}</Field>
              </div>
            </div>
          )}

          {tab === 'legal' && (
            <div className="space-y-5">
              <Field label="Юридическое лицо">{salon.legal_entity}</Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Ставка аренды">{salon.rent_rate ? `${Number(salon.rent_rate).toLocaleString('ru')} ₽/м²` : null}</Field>
                <Field label="День оплаты">{salon.rent_payment_day ? `${salon.rent_payment_day}-е число` : null}</Field>
              </div>
              {salon.rent_notes && (
                <Field label="Условия аренды">
                  <p className="whitespace-pre-wrap text-sm">{salon.rent_notes}</p>
                </Field>
              )}
            </div>
          )}

          {tab === 'staff' && (
            <div className="space-y-3">
              {assignedEmps.length === 0 ? (
                <p className="text-sm text-[color:var(--color-muted-foreground)] italic text-center py-8">Сотрудники не закреплены</p>
              ) : (
                <div className="space-y-2">
                  {assignedEmps.map(emp => (
                    <div key={emp.id} className="flex items-center gap-3 rounded-xl border border-[color:var(--color-border)] px-4 py-3">
                      <div className="w-8 h-8 rounded-full bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] font-bold text-sm flex items-center justify-center flex-shrink-0">
                        {(emp.name || '?')[0]}
                      </div>
                      <div>
                        <div className="text-sm font-medium">{emp.name}</div>
                        {emp.position && <div className="text-xs text-[color:var(--color-muted-foreground)]">{emp.position}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === 'tc' && (
            <div className="space-y-4">
              <Field label="ТЦ / Арендодатель">{salon.tc_name}</Field>
              {(salon.tc_contacts || []).length > 0 && (
                <div className="space-y-3">
                  <div className="text-xs font-medium text-[color:var(--color-muted-foreground)]">Контактные лица</div>
                  {salon.tc_contacts.map((c, i) => (
                    <div key={i} className="rounded-xl border border-[color:var(--color-border)] p-4 space-y-1.5">
                      <div className="font-medium text-sm">{c.name || '—'} {c.role && <span className="font-normal text-[color:var(--color-muted-foreground)]">· {c.role}</span>}</div>
                      {c.phone && <div className="text-sm text-[color:var(--color-muted-foreground)]">📞 {c.phone}</div>}
                      {c.email && <div className="text-sm text-[color:var(--color-muted-foreground)]">✉️ {c.email}</div>}
                    </div>
                  ))}
                </div>
              )}
              {(!salon.tc_contacts || salon.tc_contacts.length === 0) && (
                <p className="text-sm text-[color:var(--color-muted-foreground)] italic text-center py-4">Контакты не добавлены</p>
              )}
            </div>
          )}

          {tab === 'notes' && (
            <div>
              {salon.notes
                ? <p className="text-sm whitespace-pre-wrap">{salon.notes}</p>
                : <p className="text-sm text-[color:var(--color-muted-foreground)] italic text-center py-8">Нет заметок</p>
              }
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-[color:var(--color-border)]">
          {!confirmDelete ? (
            <button onClick={() => setConfirmDelete(true)} className="text-sm text-red-500 hover:text-red-700">Удалить салон</button>
          ) : (
            <div className="flex items-center gap-3">
              <span className="text-sm text-red-600 font-medium">Удалить «{salon.name}»?</span>
              <button onClick={onDelete} className="text-sm text-red-600 underline font-medium">Да, удалить</button>
              <button onClick={() => setConfirmDelete(false)} className="text-sm text-[color:var(--color-muted-foreground)]">Отмена</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────
export default function Salons() {
  const { isMobile } = useViewport();
  const [salons, setSalons]       = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);

  const [search, setSearch]               = useState('');
  const [statusFilter, setStatusFilter]   = useState('');
  const [modal, setModal]                 = useState(null);   // null | 'new' | salon-object (edit)
  const [drawer, setDrawer]               = useState(null);   // null | salon-object

  useEffect(() => {
    Promise.all([
      api.get('/salons/'),
      api.get('/employees/'),
    ]).then(([s, e]) => {
      setSalons(s.data);
      setEmployees(e.data);
    }).catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    let r = salons;
    if (statusFilter) r = r.filter(s => s.status === statusFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      r = r.filter(s =>
        s.name.toLowerCase().includes(q) ||
        s.address?.toLowerCase().includes(q) ||
        s.code?.toLowerCase().includes(q)
      );
    }
    return r;
  }, [salons, statusFilter, search]);

  const stats = useMemo(() => ({
    total: salons.length,
    active: salons.filter(s => s.status === 'active').length,
    renovation: salons.filter(s => s.status === 'renovation').length,
    closed: salons.filter(s => s.status === 'closed').length,
  }), [salons]);

  async function handleSave(payload, id) {
    if (id) {
      const res = await api.patch(`/salons/${id}`, payload);
      setSalons(prev => prev.map(s => s.id === id ? res.data : s));
      if (drawer?.id === id) setDrawer(res.data);
    } else {
      const res = await api.post('/salons/', payload);
      setSalons(prev => [...prev, res.data]);
    }
    setModal(null);
  }

  async function handleDelete(id) {
    await api.delete(`/salons/${id}`);
    setSalons(prev => prev.filter(s => s.id !== id));
    setDrawer(null);
  }

  if (loading) return <div className="p-8 text-center text-[color:var(--color-muted-foreground)]">Загрузка...</div>;
  if (error)   return <div className="p-8 text-center text-red-500">{error}</div>;

  return (
    <div className="p-6 space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold">Управление салонами</h1>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">Сеть точек продаж и обслуживания</p>
        </div>
        <button onClick={() => setModal('new')} className="btn btn-primary">+ Добавить салон</button>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Всего',    value: stats.total,      cls: 'text-[color:var(--color-foreground)]' },
          { label: 'Работает', value: stats.active,     cls: 'text-emerald-600' },
          { label: 'Ремонт',   value: stats.renovation, cls: 'text-amber-600' },
          { label: 'Закрыт',   value: stats.closed,     cls: 'text-red-500' },
        ].map(({ label, value, cls }) => (
          <div key={label} className="card p-4 text-center">
            <div className={`text-3xl font-bold ${cls}`}>{value}</div>
            <div className="text-xs text-[color:var(--color-muted-foreground)] mt-1">{label}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Поиск по названию, адресу..."
          className="input text-sm w-64"
        />
        <div className="flex gap-1.5">
          {[{ value: '', label: 'Все' }, ...STATUS_OPTIONS].map(o => (
            <button
              key={o.value}
              onClick={() => setStatusFilter(o.value)}
              className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                statusFilter === o.value
                  ? 'bg-[color:var(--color-primary)] text-white'
                  : 'bg-[color:var(--color-muted)] text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-muted)]/80'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      {filtered.length === 0 ? (
        <div className="card p-16 text-center text-[color:var(--color-muted-foreground)]">
          {salons.length === 0
            ? <div><p className="text-lg font-medium mb-2">Нет салонов</p><p className="text-sm">Нажмите «+ Добавить салон» чтобы начать</p></div>
            : <p>Ничего не найдено</p>
          }
        </div>
      ) : isMobile ? (
        <div className="space-y-3">
          {filtered.map(s => (
            <div key={s.id} className="border rounded-xl bg-[color:var(--color-surface)] shadow-sm overflow-hidden" onClick={() => setDrawer(s)}>
              <div className="px-4 py-3 border-b bg-[color:var(--color-bg-subtle)] text-sm font-medium flex items-center justify-between">
                <span>{s.name}{s.code ? ` (${s.code})` : ''}</span>
                <Badge status={s.status} />
              </div>
              <div className="px-4 py-2 space-y-1.5 text-sm">
                {s.address && <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Адрес</span><span className="text-right max-w-[60%]">{s.address}</span></div>}
                {s.phone && <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Телефон</span><span>{s.phone}</span></div>}
                {(s.work_hours_weekday || s.work_hours_weekend) && (
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Часы</span><span>{[s.work_hours_weekday, s.work_hours_weekend].filter(Boolean).join(' / ')}</span></div>
                )}
              </div>
              <div className="px-4 py-2 border-t flex justify-end gap-3">
                <button className="btn btn-secondary text-sm" onClick={e => { e.stopPropagation(); setDrawer(s); }}>Подробнее</button>
                <button className="btn btn-primary text-sm" onClick={e => { e.stopPropagation(); setDrawer(null); setModal(s); }}>Изменить</button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map(s => (
            <SalonCard
              key={s.id}
              salon={s}
              employees={employees}
              onClick={() => setDrawer(s)}
            />
          ))}
        </div>
      )}

      {/* Edit / Create modal */}
      {modal && (
        <SalonModal
          salon={modal === 'new' ? null : modal}
          employees={employees}
          onSave={handleSave}
          onClose={() => setModal(null)}
        />
      )}

      {/* Detail drawer */}
      {drawer && (
        <SalonDrawer
          salon={drawer}
          employees={employees}
          onEdit={() => { setModal(drawer); setDrawer(null); }}
          onDelete={() => handleDelete(drawer.id)}
          onClose={() => setDrawer(null)}
        />
      )}
    </div>
  );
}
