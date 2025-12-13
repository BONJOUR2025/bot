import { useEffect, useState } from 'react';
import {
  CheckCircle,
  Download,
  MoreVertical,
  Plus,
  Pencil,
  RefreshCw,
  Trash2,
  XCircle,
} from 'lucide-react';
import api from '../api';
import { useAuth } from '../providers/AuthProvider.jsx';
import { toast } from 'sonner';
import StatusBadge from '../components/StatusBadge.jsx';
import { Button } from '../components/ui/button.jsx';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card.jsx';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '../components/ui/dropdown-menu.jsx';
import { Input } from '../components/ui/input.jsx';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table.jsx';
import { Textarea } from '../components/ui/textarea.jsx';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/dialog.jsx';
import { Label } from '../components/ui/label.jsx';

const MAX_AMOUNT = 100000;
const STATUS_OPTIONS = ['Ожидает', 'Одобрено', 'Отклонено', 'Выплачено'];
const MANAGE_DATES_PERMISSION = 'payouts-manage-dates';

const pad = (value) => String(value).padStart(2, '0');

function toInputTimestamp(value) {
  if (!value) return '';
  const source = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(source.getTime())) {
    if (typeof value === 'string') {
      const fallback = new Date(value.replace(' ', 'T'));
      if (!Number.isNaN(fallback.getTime())) {
        return toInputTimestamp(fallback);
      }
    }
    return '';
  }
  return (
    `${source.getFullYear()}-${pad(source.getMonth() + 1)}-${pad(source.getDate())}` +
    `T${pad(source.getHours())}:${pad(source.getMinutes())}:${pad(source.getSeconds())}`
  );
}

function toPayloadTimestamp(value) {
  if (!value) return undefined;
  if (!value.includes('T')) {
    return value;
  }
  const [datePart, timePart] = value.split('T');
  const [hours = '00', minutes = '00', seconds = '00'] = timePart.split(':');
  return `${datePart} ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}

function Summary({ list }) {
  const total = list.reduce((sum, p) => sum + Number(p.amount || 0), 0);
  const statusStats = list.reduce((acc, p) => {
    acc[p.status] = (acc[p.status] || 0) + 1;
    return acc;
  }, {});
  const typeStats = list.reduce((acc, p) => {
    acc[p.payout_type] = (acc[p.payout_type] || 0) + Number(p.amount || 0);
    return acc;
  }, {});
  const sumAll = Object.values(typeStats).reduce((s, v) => s + v, 0) || 1;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-lg font-semibold">Сводка по выплатам</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-3">
        <div className="space-y-1 rounded-lg border border-border/60 bg-card/60 p-4 shadow-sm">
          <p className="text-sm text-muted-foreground">Всего заявок</p>
          <div className="text-2xl font-semibold">{list.length}</div>
          <p className="text-sm text-muted-foreground">
            На сумму <span className="font-semibold text-foreground">{total.toLocaleString('ru-RU')} ₽</span>
          </p>
        </div>
        <div className="space-y-3 rounded-lg border border-border/60 bg-card/60 p-4 shadow-sm">
          <p className="text-sm font-medium">По статусу</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(statusStats).map(([k, v]) => (
              <StatusBadge key={k} status={`${k} · ${v}`} />
            ))}
          </div>
        </div>
        <div className="space-y-3 rounded-lg border border-border/60 bg-card/60 p-4 shadow-sm">
          <p className="text-sm font-medium">По типам</p>
          <div className="space-y-2">
            {Object.entries(typeStats).map(([k, v]) => (
              <div key={k} className="space-y-1">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{k}</span>
                  <span className="font-medium text-foreground">{v.toLocaleString('ru-RU')} ₽</span>
                </div>
                <div className="h-2 rounded-full bg-muted/50">
                  <div
                    className="h-2 rounded-full bg-primary/60"
                    style={{ width: `${(v / sumAll) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function formatDateTime(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    const fixed = value.replace(' ', 'T');
    const dt = new Date(fixed);
    if (Number.isNaN(dt.getTime())) return value;
    return (
      dt.toLocaleDateString('ru-RU') +
      ' ' +
      dt.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    );
  }
  return (
    d.toLocaleDateString('ru-RU') +
    ' ' +
    d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  );
}

export default function Payouts() {
  const { user } = useAuth();
  const canManageDates = Boolean(
    user?.permissions?.includes('*') || user?.permissions?.includes(MANAGE_DATES_PERMISSION),
  );
  const emptyForm = {
    id: null,
    user_id: '',
    name: '',
    phone: '',
    card_number: '',
    bank: '',
    amount: '',
    payout_type: 'Аванс',
    method: '💳 На карту',
    status: 'Ожидает',
    sync_to_bot: false,
    notify_user: true,
    note: '',
    show_note_in_bot: false,
    timestamp: '',
    force_notify_cashier: false,
  };

  const [payouts, setPayouts] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [useFullName, setUseFullName] = useState(true);
  const [filters, setFilters] = useState({
    query: '',
    type: '',
    status: '',
    method: '',
    from: '',
    to: '',
  });
  const [showEditor, setShowEditor] = useState(false);
  const [form, setForm] = useState(emptyForm);

  useEffect(() => {
    load();
    loadEmployees();
    window.refreshPage = load;
  }, []);

  async function loadEmployees() {
    try {
      const res = await api.get('employees/', { params: { archived: false } });
      setEmployees(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function load() {
    try {
      const params = {
        payout_type: filters.type || undefined,
        status: filters.status || undefined,
        method: filters.method || undefined,
        date_from: filters.from || undefined,
        date_to: filters.to || undefined,
      };
      const res = await api.get('payouts/', { params });
      let list = res.data;
      if (filters.query) {
        const q = filters.query.toLowerCase();
        list = list.filter((p) => p.name?.toLowerCase().includes(q));
      }
      setPayouts(list);
    } catch (err) {
      console.error(err);
    }
  }

  function resetFilters() {
    setFilters({ query: '', type: '', status: '', method: '', from: '', to: '' });
    load();
  }

  async function updateStatus(id, status) {
    try {
      let endpoint = '';
      switch (status) {
        case 'Одобрено':
          endpoint = `payouts/${id}/approve`;
          break;
        case 'Отклонено':
          endpoint = `payouts/${id}/reject`;
          break;
        case 'Выплачено':
          endpoint = `payouts/${id}/mark_paid`;
          break;
        default:
          return;
      }
      await api.post(endpoint);
      toast.success('Статус обновлён');
      load();
    } catch (err) {
      console.error(err);
      toast.error('Ошибка запроса');
    }
  }

  async function remove(id) {
    if (!window.confirm('Удалить выплату?')) return;
    try {
      await api.delete(`payouts/${id}`);
      toast.success('Выплата удалена');
      load();
    } catch (err) {
      console.error(err);
      toast.error('Ошибка удаления');
    }
  }

  function openCreate() {
    setForm({
      ...emptyForm,
      timestamp: canManageDates ? toInputTimestamp(new Date()) : '',
    });
    setShowEditor(true);
  }

  function openEdit(p) {
    setForm({
      ...emptyForm,
      ...p,
      timestamp: canManageDates ? toInputTimestamp(p.timestamp) : '',
      notify_user: true,
      note: p.note || '',
      show_note_in_bot: p.show_note_in_bot || false,
      force_notify_cashier: Boolean(p.force_notify_cashier),
    });
    setShowEditor(true);
  }

  async function saveForm() {
    const amount = Number(form.amount || 0);
    if (!form.user_id || !amount || amount > MAX_AMOUNT) {
      toast.error('Неверные данные');
      return;
    }
    const payload = { ...form, amount };
    if (canManageDates && form.timestamp) {
      payload.timestamp = toPayloadTimestamp(form.timestamp);
    } else {
      delete payload.timestamp;
    }
    try {
      if (form.id) {
        await api.put(`payouts/${form.id}`, payload);
      } else {
        await api.post('payouts/', payload);
      }
      setShowEditor(false);
      setForm(emptyForm);
      toast.success('Сохранено');
      load();
    } catch (err) {
      console.error(err);
      toast.error('Ошибка сохранения');
    }
  }

  function handleSelect(id) {
    const emp = employees.find((e) => String(e.id) === String(id));
    if (emp) {
      setForm((f) => ({
        ...f,
        user_id: emp.id,
        name: useFullName ? emp.full_name || emp.name : emp.name || emp.full_name,
        phone: emp.phone || '',
        bank: emp.bank || emp.card_number || '',
        card_number: emp.card_number || '',
      }));
    }
  }

  function exportPdf() {
    const q = new URLSearchParams({
      payout_type: filters.type,
      status: filters.status,
      method: filters.method,
      date_from: filters.from,
      date_to: filters.to,
    });
    window.open(`/api/payouts/export.pdf?${q.toString()}`, '_blank');
  }

  async function checkTelegram() {
    try {
      await api.get('payouts/unconfirmed');
      load();
      toast.success('Заявки обновлены');
    } catch (err) {
      console.error(err);
      toast.error('Ошибка обновления');
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">Статусы и суммы начислений с контролем сроков.</p>
          <h2 className="text-3xl font-semibold tracking-tight">Выплаты</h2>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={checkTelegram} aria-label="Проверить бот">
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button onClick={openCreate} className="gap-2">
            <Plus className="h-4 w-4" />
            Новая заявка
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg font-medium">Фильтры</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3 lg:grid-cols-4">
          <div className="md:col-span-2 lg:col-span-2">
            <Input
              placeholder="Поиск по ФИО"
              value={filters.query}
              onChange={(e) => setFilters({ ...filters, query: e.target.value })}
            />
          </div>
          <select
            className="h-10 w-full rounded-md border border-border/60 bg-card px-3 text-sm text-foreground"
            value={filters.type}
            onChange={(e) => setFilters({ ...filters, type: e.target.value })}
          >
            <option value="">Все типы</option>
            <option value="Аванс">Аванс</option>
            <option value="Зарплата">Зарплата</option>
          </select>
          <select
            className="h-10 w-full rounded-md border border-border/60 bg-card px-3 text-sm text-foreground"
            value={filters.status}
            onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          >
            <option value="">Все статусы</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            className="h-10 w-full rounded-md border border-border/60 bg-card px-3 text-sm text-foreground"
            value={filters.method}
            onChange={(e) => setFilters({ ...filters, method: e.target.value })}
          >
            <option value="">Все способы</option>
            <option value="💳 На карту">На карту</option>
            <option value="🏦 Из кассы">Из кассы</option>
            <option value="🤝 Наличными">Наличными</option>
          </select>
          <Input
            type="date"
            value={filters.from}
            onChange={(e) => setFilters({ ...filters, from: e.target.value })}
          />
          <Input
            type="date"
            value={filters.to}
            onChange={(e) => setFilters({ ...filters, to: e.target.value })}
          />
          <div className="flex flex-wrap gap-2 md:col-span-2 lg:col-span-4">
            <Button onClick={load}>Применить</Button>
            <Button variant="secondary" onClick={resetFilters}>
              Сбросить
            </Button>
            <Button variant="outline" className="ml-auto gap-2" onClick={exportPdf}>
              <Download className="h-4 w-4" />
              PDF
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="border border-border/60 bg-card/90 shadow-sm">
        <CardHeader className="flex flex-col gap-1 pb-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-lg font-semibold">Текущие заявки</CardTitle>
            <p className="text-sm text-muted-foreground">Всего {payouts.length} записей</p>
          </div>
          <Button variant="ghost" size="sm" className="gap-2" onClick={load}>
            <RefreshCw className="h-4 w-4" />
            Обновить
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          {payouts.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ФИО</TableHead>
                  <TableHead>Тип</TableHead>
                  <TableHead>Способ</TableHead>
                  <TableHead className="text-right">Сумма</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead>Дата</TableHead>
                  <TableHead className="text-right" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {payouts.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium text-foreground">{p.name}</TableCell>
                    <TableCell className="text-muted-foreground">{p.payout_type}</TableCell>
                    <TableCell className="text-muted-foreground">{p.method}</TableCell>
                    <TableCell className="text-right font-semibold text-foreground">
                      {Number(p.amount || 0).toLocaleString('ru-RU')} ₽
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={p.status} />
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs sm:text-sm">
                      {formatDateTime(p.timestamp)}
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-9 w-9">
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-48">
                          <DropdownMenuItem onClick={() => openEdit(p)}>
                            <Pencil className="mr-2 h-4 w-4" /> Редактировать
                          </DropdownMenuItem>
                          {p.status === 'Ожидает' && (
                            <DropdownMenuItem onClick={() => updateStatus(p.id, 'Одобрено')}>
                              <CheckCircle className="mr-2 h-4 w-4" /> Одобрить
                            </DropdownMenuItem>
                          )}
                          {p.status === 'Ожидает' && (
                            <DropdownMenuItem onClick={() => updateStatus(p.id, 'Отклонено')}>
                              <XCircle className="mr-2 h-4 w-4" /> Отклонить
                            </DropdownMenuItem>
                          )}
                          {p.status === 'Одобрено' && (
                            <DropdownMenuItem onClick={() => updateStatus(p.id, 'Выплачено')}>
                              <Download className="mr-2 h-4 w-4" /> Выплачено
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuItem className="text-destructive" onClick={() => remove(p.id)}>
                            <Trash2 className="mr-2 h-4 w-4" /> Удалить
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="flex min-h-[200px] flex-col items-center justify-center gap-3 p-8 text-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted/40">
                <Plus className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-medium text-foreground">Нет данных</p>
                <p className="text-sm text-muted-foreground">Создайте новую заявку или уточните фильтры.</p>
              </div>
              <Button size="sm" className="gap-2" onClick={openCreate}>
                <Plus className="h-4 w-4" /> Новая заявка
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Summary list={payouts} />

      <Dialog
        open={showEditor}
        onOpenChange={(open) => {
          setShowEditor(open);
          if (!open) {
            setForm(emptyForm);
          }
        }}
      >
        <DialogContent className="sm:max-w-[560px] bg-popover">
          <DialogHeader>
            <DialogTitle className="text-2xl font-semibold">
              {form.id ? 'Редактирование выплаты' : 'Новая выплата'}
            </DialogTitle>
            <DialogDescription className="text-sm text-muted-foreground">
              Уточните данные сотрудника, сумму и уведомления. Поля проверяются автоматически.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-6">
            <div className="space-y-3">
              <p className="text-sm font-medium text-foreground">Сотрудник</p>
              <div className="space-y-2">
                <Label className="text-sm text-muted-foreground">Профиль</Label>
                <select
                  className="h-10 w-full rounded-md border border-border/60 bg-background px-3 text-sm"
                  value={form.user_id}
                  onChange={(e) => handleSelect(e.target.value)}
                >
                  <option value="">Сотрудник</option>
                  {employees.map((e) => (
                    <option key={e.id} value={e.id}>
                      {useFullName ? e.full_name || e.name : e.name || e.full_name}
                    </option>
                  ))}
                </select>
                <label className="flex items-center gap-2 text-sm text-muted-foreground">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-border/70 bg-background"
                    checked={useFullName}
                    onChange={(e) => setUseFullName(e.target.checked)}
                  />
                  Использовать ФИО вместо никнейма
                </label>
                <p className="text-sm text-muted-foreground">
                  Карта: <span className="font-medium text-foreground">{form.card_number || '—'}</span>
                </p>
                <p className="text-sm text-muted-foreground">
                  Банк: <span className="font-medium text-foreground">{form.bank || '—'}</span>
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <p className="text-sm font-medium text-foreground">Платёж</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label className="text-sm text-muted-foreground">Сумма</Label>
                  <Input
                    placeholder="Сумма"
                    type="number"
                    value={form.amount}
                    onChange={(e) => setForm({ ...form, amount: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-sm text-muted-foreground">Тип выплаты</Label>
                  <select
                    className="h-10 w-full rounded-md border border-border/60 bg-background px-3 text-sm"
                    value={form.payout_type}
                    onChange={(e) => setForm({ ...form, payout_type: e.target.value })}
                  >
                    <option value="Аванс">Аванс</option>
                    <option value="Зарплата">Зарплата</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <Label className="text-sm text-muted-foreground">Способ</Label>
                  <select
                    className="h-10 w-full rounded-md border border-border/60 bg-background px-3 text-sm"
                    value={form.method}
                    onChange={(e) => setForm({ ...form, method: e.target.value })}
                  >
                    <option value="💳 На карту">На карту</option>
                    <option value="🏦 Из кассы">Из кассы</option>
                    <option value="🤝 Наличными">Наличными</option>
                  </select>
                </div>
                {canManageDates && (
                  <div className="space-y-2">
                    <Label className="text-sm text-muted-foreground">Дата выплаты</Label>
                    <Input
                      type="datetime-local"
                      step="1"
                      value={form.timestamp}
                      onChange={(e) => setForm({ ...form, timestamp: e.target.value })}
                    />
                  </div>
                )}
                {form.id && (
                  <div className="space-y-2">
                    <Label className="text-sm text-muted-foreground">Статус</Label>
                    <select
                      className="h-10 w-full rounded-md border border-border/60 bg-background px-3 text-sm"
                      value={form.status}
                      onChange={(e) => setForm({ ...form, status: e.target.value })}
                    >
                      {STATUS_OPTIONS.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-3">
              <p className="text-sm font-medium text-foreground">Уведомления</p>
              <div className="space-y-3">
                <Textarea
                  placeholder="Примечание"
                  value={form.note}
                  onChange={(e) => setForm({ ...form, note: e.target.value })}
                />
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm text-muted-foreground">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-border/70 bg-background"
                      checked={form.show_note_in_bot}
                      onChange={(e) => setForm({ ...form, show_note_in_bot: e.target.checked })}
                    />
                    Показывать примечание в боте
                  </label>
                  <label className="flex items-center gap-2 text-sm text-muted-foreground">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-border/70 bg-background"
                      checked={form.force_notify_cashier}
                      onChange={(e) =>
                        setForm({ ...form, force_notify_cashier: e.target.checked })
                      }
                    />
                    Всегда уведомлять кассира
                  </label>
                  <label className="flex items-center gap-2 text-sm text-muted-foreground">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-border/70 bg-background"
                      checked={form.sync_to_bot}
                      onChange={(e) => setForm({ ...form, sync_to_bot: e.target.checked })}
                    />
                    Отразить в боте
                  </label>
                  {form.id && (
                    <label className="flex items-center gap-2 text-sm text-muted-foreground">
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-border/70 bg-background"
                        checked={form.notify_user}
                        onChange={(e) => setForm({ ...form, notify_user: e.target.checked })}
                      />
                      Уведомить сотрудника
                    </label>
                  )}
                </div>
              </div>
            </div>
          </div>

          <DialogFooter className="pt-2 sm:space-x-2">
            <Button
              variant="secondary"
              onClick={() => {
                setShowEditor(false);
                setForm(emptyForm);
              }}
            >
              Отмена
            </Button>
            <Button onClick={saveForm}>Сохранить</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}






