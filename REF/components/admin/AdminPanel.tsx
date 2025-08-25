import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Badge } from '../ui/badge';
import { StatusBadge, StatusBadgeProps } from '../design-system/StatusBadge';
import { ActionCard } from '../design-system/ActionCard';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Calendar } from '../ui/calendar';
import { 
  Users, 
  DollarSign, 
  Clock, 
  BarChart3, 
  Search,
  Bell,
  Settings,
  TrendingUp,
  CheckCircle,
  XCircle,
  AlertCircle,
  Calendar as CalendarIcon,
  Filter,
  MessageSquare,
  Gift,
  Briefcase,
  Package,
  FileText,
  Cake,
  BookOpen,
  Download,
  Upload,
  Eye,
  Edit,
  Trash2,
  UserPlus,
  Send,
  ShieldAlert,
  PlusCircle
} from 'lucide-react';

// Компонент Dashboard
const Dashboard: React.FC = () => {
  const stats = [
    {
      title: 'Продажи косметики сегодня',
      value: '256,400 ₽',
      change: '+18%',
      icon: <TrendingUp className="h-5 w-5" />,
      color: 'text-success'
    },
    {
      title: 'Активные запросы на выплату',
      value: '12',
      change: '+3',
      icon: <DollarSign className="h-5 w-5" />,
      color: 'text-warning'
    },
    {
      title: 'Сотрудники в отпуске',
      value: '5',
      change: '+1',
      icon: <Users className="h-5 w-5" />,
      color: 'text-primary'
    },
    {
      title: 'Общее количество сотрудников',
      value: '89',
      change: '+2',
      icon: <Users className="h-5 w-5" />,
      color: 'text-success'
    }
  ];

  const recentRequests = [
    {
      id: 1,
      employee: 'Алексей Иванов',
      amount: 2500,
      status: 'waiting' as const,
      time: '14:32',
      type: 'Аванс',
      priority: 'normal'
    },
    {
      id: 2,
      employee: 'Мария Петрова',
      amount: 1800,
      status: 'approved' as const,
      time: '13:15',
      type: 'Премия',
      priority: 'normal'
    },
    {
      id: 3,
      employee: 'Дмитрий Сидоров',
      amount: 3200,
      status: 'waiting' as const,
      time: '12:45',
      type: 'Зарплата',
      priority: 'high'
    }
  ];

  const upcomingBirthdays = [
    { name: 'Анна Смирнова', date: '27 июля', department: 'Отдел продаж' },
    { name: 'Петр Козлов', date: '30 июля', department: 'Склад' },
    { name: 'Елена Васильева', date: '2 августа', department: 'Администрация' }
  ];

  const employeesOnLeave = [
    { name: 'Олег Михайлов', period: '25 июля - 10 августа', type: 'Отпуск' },
    { name: 'Светлана Кузнецова', period: '20 июля - 27 июля', type: 'Больничный' }
  ];

  return (
    <div className="space-y-6">
      {/* Статистика */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, index) => (
          <Card key={index}>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-text-secondary">{stat.title}</p>
                  <p className="text-2xl font-semibold">{stat.value}</p>
                  <p className={`text-sm ${stat.color}`}>
                    {stat.change}
                  </p>
                </div>
                <div className={`${stat.color}`}>
                  {stat.icon}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Активные запросы на выплату */}
        <Card className="lg:col-span-8">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <DollarSign className="h-5 w-5" />
              Активные запросы на выплату
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {recentRequests.map((request) => (
                <div key={request.id} className="flex items-center justify-between p-3 border border-border-light rounded-lg">
                  <div className="flex items-center gap-3">
                    {request.priority === 'high' && (
                      <AlertCircle className="h-4 w-4 text-danger" />
                    )}
                    <div>
                      <p className="font-medium">{request.employee}</p>
                      <p className="text-sm text-text-secondary">
                        {request.type} • {request.time}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <p className="font-semibold">{request.amount} ₽</p>
                      <StatusBadge status={request.status} size="sm" />
                    </div>
                    {request.status === 'waiting' && (
                      <div className="flex gap-1">
                        <Button size="sm" variant="default">
                          <CheckCircle className="h-4 w-4" />
                        </Button>
                        <Button size="sm" variant="destructive">
                          <XCircle className="h-4 w-4" />
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Ближайшие дни рождения */}
        <Card className="lg:col-span-4">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Cake className="h-5 w-5" />
              Ближайшие дни рождения
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {upcomingBirthdays.map((birthday, index) => (
                <div key={index} className="flex items-center gap-3 p-2 bg-muted rounded-lg">
                  <div className="w-8 h-8 bg-primary/10 rounded-full flex items-center justify-center">
                    🎂
                  </div>
                  <div>
                    <p className="font-medium text-sm">{birthday.name}</p>
                    <p className="text-xs text-text-secondary">{birthday.date}</p>
                    <p className="text-xs text-text-secondary">{birthday.department}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Сотрудники в отпуске */}
        <Card className="lg:col-span-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CalendarIcon className="h-5 w-5" />
              Сотрудники в отпуске
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {employeesOnLeave.map((employee, index) => (
                <div key={index} className="flex items-center justify-between p-3 border border-border-light rounded-lg">
                  <div>
                    <p className="font-medium">{employee.name}</p>
                    <p className="text-sm text-text-secondary">{employee.period}</p>
                  </div>
                  <Badge variant={employee.type === 'Больничный' ? 'destructive' : 'default'}>
                    {employee.type}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Быстрые действия */}
        <Card className="lg:col-span-6">
          <CardHeader>
            <CardTitle>Быстрые действия</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-2">
              <Button className="justify-start" variant="secondary" size="sm">
                <UserPlus className="h-4 w-4 mr-2" />
                Добавить сотрудника
              </Button>
              <Button className="justify-start" variant="secondary" size="sm">
                <MessageSquare className="h-4 w-4 mr-2" />
                Рассылка
              </Button>
              <Button className="justify-start" variant="secondary" size="sm">
                <FileText className="h-4 w-4 mr-2" />
                Отчет
              </Button>
              <Button className="justify-start" variant="secondary" size="sm">
                <BarChart3 className="h-4 w-4 mr-2" />
                Аналитика
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

// Компонент управления пользователями
const UsersManagement: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState('');

  const users = [
    {
      id: 1,
      name: 'Алексей Иванов',
      email: 'alexey@example.com',
      status: 'active' as const,
      shifts: 12,
      earnings: 45600,
      store: 'ТЦ Мега'
    },
    {
      id: 2,
      name: 'Мария Петрова',
      email: 'maria@example.com',
      status: 'active' as const,
      shifts: 8,
      earnings: 28400,
      store: 'ТЦ Европолис'
    },
    {
      id: 3,
      name: 'Дмитрий Сидоров',
      email: 'dmitry@example.com',
      status: 'inactive' as const,
      shifts: 4,
      earnings: 12800,
      store: 'ТЦ Атлас'
    }
  ];

  const filteredUsers = users.filter(user =>
    user.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    user.email.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Поиск и фильтры */}
      <div className="flex gap-4">
        <div className="flex-1">
          <Input
            placeholder="Поиск сотрудников..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full"
          />
        </div>
        <Button variant="secondary">
          <Filter className="h-4 w-4 mr-2" />
          Фильтры
        </Button>
        <Button>
          <Users className="h-4 w-4 mr-2" />
          Добавить
        </Button>
      </div>

      {/* Таблица пользователей */}
      <Card>
        <CardHeader>
          <CardTitle>Сотрудники ({filteredUsers.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {filteredUsers.map((user) => (
              <div key={user.id} className="flex items-center justify-between p-4 border border-border-light rounded-lg">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center">
                    <Users className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <p className="font-medium">{user.name}</p>
                    <p className="text-sm text-text-secondary">{user.email}</p>
                    <p className="text-sm text-text-secondary">{user.store}</p>
                  </div>
                </div>
                
                <div className="flex items-center gap-6">
                  <div className="text-center">
                    <p className="text-sm text-text-secondary">Смены</p>
                    <p className="font-semibold">{user.shifts}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-sm text-text-secondary">Заработок</p>
                    <p className="font-semibold">{user.earnings.toLocaleString()} ₽</p>
                  </div>
                  <StatusBadge status={user.status} />
                  <div className="flex gap-2">
                    <Button size="sm" variant="secondary">
                      Изменить
                    </Button>
                    <Button size="sm" variant="destructive">
                      Удалить
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Система рассылки сообщений
const MessagingSystem: React.FC = () => {
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [message, setMessage] = useState('');
  const [recipients, setRecipients] = useState('all');

  const templates = [
    { id: 'salary', name: 'Уведомление о зарплате', content: 'Ваша зарплата за {месяц} составляет {сумма} рублей.' },
    { id: 'shift', name: 'Напоминание о смене', content: 'Напоминаем, что завтра у вас смена с {время_начала} до {время_окончания}.' },
    { id: 'birthday', name: 'Поздравление с днем рождения', content: 'Поздравляем с днем рождения! Желаем здоровья и успехов!' }
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MessageSquare className="h-5 w-5" />
              Создание рассылки
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Получатели</label>
              <Select value={recipients} onValueChange={setRecipients}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Все сотрудники</SelectItem>
                  <SelectItem value="active">Только активные</SelectItem>
                  <SelectItem value="department">По отделам</SelectItem>
                  <SelectItem value="custom">Выбрать вручную</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Шаблон сообщения</label>
              <Select value={selectedTemplate} onValueChange={setSelectedTemplate}>
                <SelectTrigger>
                  <SelectValue placeholder="Выберите шаблон" />
                </SelectTrigger>
                <SelectContent>
                  {templates.map((template) => (
                    <SelectItem key={template.id} value={template.id}>
                      {template.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Текст сообщения</label>
              <textarea
                className="w-full h-32 p-3 border border-border-light rounded-lg resize-none"
                placeholder="Введите текст сообщения..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            </div>

            <div className="flex gap-2">
              <Button className="flex-1">
                <Send className="h-4 w-4 mr-2" />
                Отправить сейчас
              </Button>
              <Button variant="secondary" className="flex-1">
                <Clock className="h-4 w-4 mr-2" />
                Запланировать
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Статистика рассылок</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="text-center p-4 bg-muted rounded-lg">
                <p className="text-2xl font-bold">127</p>
                <p className="text-sm text-text-secondary">Отправлено сегодня</p>
              </div>
              <div className="text-center p-4 bg-muted rounded-lg">
                <p className="text-2xl font-bold">94%</p>
                <p className="text-sm text-text-secondary">Доставлено успешно</p>
              </div>
              <div className="text-center p-4 bg-muted rounded-lg">
                <p className="text-2xl font-bold">73</p>
                <p className="text-sm text-text-secondary">Активные получатели</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>История рассылок</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[
              { id: 1, subject: 'Уведомление о зарплате', recipients: 89, sent: '25.07.2025 14:30', status: 'delivered' },
              { id: 2, subject: 'Напоминание о смене', recipients: 12, sent: '25.07.2025 09:00', status: 'delivered' },
              { id: 3, subject: 'Корпоративное сообщение', recipients: 89, sent: '24.07.2025 16:45', status: 'delivered' }
            ].map((broadcast) => (
              <div key={broadcast.id} className="flex items-center justify-between p-3 border border-border-light rounded-lg">
                <div>
                  <p className="font-medium">{broadcast.subject}</p>
                  <p className="text-sm text-text-secondary">
                    {broadcast.recipients} получателей • {broadcast.sent}
                  </p>
                </div>
                <StatusBadge status="approved" size="sm" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Управление штрафами и премиями
const BonusesAndPenalties: React.FC = () => {
  const [filterType, setFilterType] = useState('all');
  const [filterEmployee, setFilterEmployee] = useState('');

  const bonusesData = [
    { id: 1, employee: 'Алексей Иванов', type: 'bonus', amount: 5000, reason: 'Выполнение плана продаж', date: '2025-07-25' },
    { id: 2, employee: 'Мария Петрова', type: 'penalty', amount: -2000, reason: 'Опоздание на работу', date: '2025-07-24' },
    { id: 3, employee: 'Дмитрий Сидоров', type: 'bonus', amount: 3000, reason: 'Отличная работа с клиентами', date: '2025-07-23' }
  ];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Gift className="h-5 w-5" />
            Штрафы и премии
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4 mb-6">
            <Select value={filterType} onValueChange={setFilterType}>
              <SelectTrigger className="w-48">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все типы</SelectItem>
                <SelectItem value="bonus">Премии</SelectItem>
                <SelectItem value="penalty">Штрафы</SelectItem>
              </SelectContent>
            </Select>
            
            <Input
              placeholder="Поиск по сотруднику..."
              value={filterEmployee}
              onChange={(e) => setFilterEmployee(e.target.value)}
              className="flex-1"
            />
            
            <Button>
              <PlusCircle className="h-4 w-4 mr-2" />
              Добавить запись
            </Button>
          </div>

          <div className="space-y-3">
            {bonusesData.map((item) => (
              <div key={item.id} className="flex items-center justify-between p-4 border border-border-light rounded-lg">
                <div className="flex items-center gap-4">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                    item.type === 'bonus' ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'
                  }`}>
                    {item.type === 'bonus' ? '+' : '-'}
                  </div>
                  <div>
                    <p className="font-medium">{item.employee}</p>
                    <p className="text-sm text-text-secondary">{item.reason}</p>
                    <p className="text-xs text-text-secondary">{item.date}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className={`text-lg font-semibold ${
                    item.type === 'bonus' ? 'text-success' : 'text-danger'
                  }`}>
                    {item.amount > 0 ? '+' : ''}{item.amount} ₽
                  </div>
                  <div className="flex gap-1">
                    <Button size="sm" variant="ghost">
                      <Edit className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="ghost">
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Управление выплатами
const PaymentsManagement: React.FC = () => {
  const [payments, setPayments] = useState<Array<{
    id: number | string;
    employee: string;
    type: string;
    amount: number;
    status: StatusBadgeProps['status'];
    date?: string;
    store?: string;
  }>>([]);

  const STATUS_MAP: Record<string, StatusBadgeProps['status']> = {
    'Ожидает': 'waiting',
    'Одобрено': 'approved',
    'Отклонено': 'rejected',
    'Выплачено': 'paid'
  };

  useEffect(() => {
    fetch('/advance_requests.json')
      .then((res) => res.json())
      .then((data) => {
        const mapped = data.map((p: any) => ({
          id: p.id,
          employee: p.name,
          type: p.payout_type,
          amount: p.amount,
          status: STATUS_MAP[p.status] || 'waiting',
          date: p.timestamp,
          store: p.method
        }));
        setPayments(mapped);
      })
      .catch((err) => console.error('Failed to load payouts', err));
  }, []);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <DollarSign className="h-5 w-5" />
            Управление выплатами
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex justify-between items-center mb-6">
            <div className="flex gap-4">
              <Select defaultValue="all">
                <SelectTrigger className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Все статусы</SelectItem>
                  <SelectItem value="waiting">Ожидание</SelectItem>
                  <SelectItem value="approved">Одобрено</SelectItem>
                  <SelectItem value="rejected">Отклонено</SelectItem>
                </SelectContent>
              </Select>
              
              <Input placeholder="Поиск по сотруднику..." className="w-64" />
            </div>
            
            <div className="flex gap-2">
              <Button variant="secondary">
                <Download className="h-4 w-4 mr-2" />
                Экспорт PDF
              </Button>
              <Button variant="secondary">
                <Eye className="h-4 w-4 mr-2" />
                Проверить бота
              </Button>
            </div>
          </div>

          <div className="space-y-3">
            {payments.map((payment) => (
              <div key={payment.id} className="flex items-center justify-between p-4 border border-border-light rounded-lg">
                <div>
                  <p className="font-medium">{payment.employee}</p>
                  <p className="text-sm text-text-secondary">
                    {payment.type} • {payment.store} • {payment.date}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <p className="font-semibold">{payment.amount.toLocaleString()} ₽</p>
                    <StatusBadge status={payment.status} size="sm" />
                  </div>
                  <div className="flex gap-1">
                    <Button size="sm" variant="default">
                      <CheckCircle className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="destructive">
                      <XCircle className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="ghost">
                      <Edit className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Контроль выплат
const PaymentControl: React.FC = () => {
  const warnings = [
    { id: 1, type: 'limit_exceeded', employee: 'Иван Петров', amount: 45000, limit: 35000, message: 'Превышение лимита выплат' },
    { id: 2, type: 'long_waiting', employee: 'Анна Сидорова', days: 5, message: 'Заявка ожидает более 3 дней' },
    { id: 3, type: 'suspicious', employee: 'Петр Козлов', count: 4, message: 'Подозрительно много заявок за неделю' }
  ];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5" />
            Контроль выплат
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {warnings.map((warning) => (
              <div key={warning.id} className="flex items-start gap-4 p-4 border-l-4 border-warning bg-warning/5 rounded-lg">
                <AlertCircle className="h-5 w-5 text-warning mt-0.5" />
                <div className="flex-1">
                  <p className="font-medium">{warning.message}</p>
                  <p className="text-sm text-text-secondary">
                    Сотрудник: {warning.employee}
                    {warning.amount && ` • Сумма: ${warning.amount.toLocaleString()} ₽`}
                    {warning.limit && ` • Лимит: ${warning.limit.toLocaleString()} ₽`}
                    {warning.days && ` • Дней ожидания: ${warning.days}`}
                    {warning.count && ` • Количество заявок: ${warning.count}`}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary">
                    Проверить
                  </Button>
                  <Button size="sm" variant="default">
                    Решить
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Управление отпусками
const VacationsManagement: React.FC = () => {
  const vacations = [
    { id: 1, employee: 'Олег Михайлов', startDate: '2025-07-25', endDate: '2025-08-10', type: 'Отпуск', status: 'active' as const },
    { id: 2, employee: 'Светлана Кузнецова', startDate: '2025-07-20', endDate: '2025-07-27', type: 'Больничный', status: 'active' as const },
    { id: 3, employee: 'Анна Смирнова', startDate: '2025-08-01', endDate: '2025-08-15', type: 'Отпуск', status: 'waiting' as const }
  ];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CalendarIcon className="h-5 w-5" />
            Отпуска и больничные
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex justify-between items-center mb-6">
            <div className="flex gap-4">
              <Select defaultValue="all">
                <SelectTrigger className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Все типы</SelectItem>
                  <SelectItem value="vacation">Отпуска</SelectItem>
                  <SelectItem value="sick">Больничные</SelectItem>
                </SelectContent>
              </Select>
              <Input placeholder="Поиск по месяцу..." className="w-48" />
            </div>
            <Button>
              <PlusCircle className="h-4 w-4 mr-2" />
              Добавить отпуск
            </Button>
          </div>

          <div className="space-y-3">
            {vacations.map((vacation) => (
              <div key={vacation.id} className="flex items-center justify-between p-4 border border-border-light rounded-lg">
                <div>
                  <p className="font-medium">{vacation.employee}</p>
                  <p className="text-sm text-text-secondary">
                    {vacation.startDate} - {vacation.endDate}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  <Badge variant={vacation.type === 'Больничный' ? 'destructive' : 'default'}>
                    {vacation.type}
                  </Badge>
                  <StatusBadge status={vacation.status} size="sm" />
                  <div className="flex gap-1">
                    <Button size="sm" variant="ghost">
                      <Edit className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="ghost">
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Управление имуществом
const PropertyManagement: React.FC = () => {
  const property = [
    { id: 1, employee: 'Алексей Иванов', item: 'Рабочая форма', category: 'Одежда', status: 'issued', date: '2025-07-01' },
    { id: 2, employee: 'Мария Петрова', item: 'Планшет Samsung', category: 'Техника', status: 'issued', date: '2025-06-15' },
    { id: 3, employee: 'Дмитрий Сидоров', item: 'Сканер штрих-кодов', category: 'Оборудование', status: 'returned', date: '2025-07-20' }
  ];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Package className="h-5 w-5" />
            Имущество сотрудников
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex justify-between items-center mb-6">
            <div className="flex gap-4">
              <Select defaultValue="all">
                <SelectTrigger className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Все категории</SelectItem>
                  <SelectItem value="clothes">Одежда</SelectItem>
                  <SelectItem value="tech">Техника</SelectItem>
                  <SelectItem value="equipment">Оборудование</SelectItem>
                </SelectContent>
              </Select>
              <Input placeholder="Поиск по сотруднику..." className="w-64" />
            </div>
            <Button>
              <PlusCircle className="h-4 w-4 mr-2" />
              Выдать имущество
            </Button>
          </div>

          <div className="space-y-3">
            {property.map((item) => (
              <div key={item.id} className="flex items-center justify-between p-4 border border-border-light rounded-lg">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center">
                    <Package className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <p className="font-medium">{item.item}</p>
                    <p className="text-sm text-text-secondary">
                      {item.employee} • {item.category} • {item.date}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <StatusBadge 
                    status={item.status === 'issued' ? 'active' : 'inactive'} 
                    size="sm" 
                  />
                  <div className="flex gap-1">
                    <Button size="sm" variant="ghost">
                      <Edit className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="ghost">
                      <Eye className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Дни рождения
const BirthdaysManagement: React.FC = () => {
  const birthdays = [
    { id: 1, name: 'Анна Смирнова', date: '27 июля', department: 'Отдел продаж', age: 28 },
    { id: 2, name: 'Петр Козлов', date: '30 июля', department: 'Склад', age: 35 },
    { id: 3, name: 'Елена Васильева', date: '2 августа', department: 'Администрация', age: 42 },
    { id: 4, name: 'Михаил Орлов', date: '5 августа', department: 'Отдел продаж', age: 31 },
    { id: 5, name: 'Ольга Никитина', date: '12 августа', department: 'Бухгалтерия', age: 39 }
  ];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cake className="h-5 w-5" />
            Дни рождения сотрудников
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {birthdays.map((birthday) => (
              <Card key={birthday.id} className="p-4">
                <div className="text-center">
                  <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-3">
                    🎂
                  </div>
                  <h3 className="font-semibold">{birthday.name}</h3>
                  <p className="text-sm text-text-secondary">{birthday.department}</p>
                  <p className="text-sm font-medium text-primary">{birthday.date}</p>
                  <p className="text-xs text-text-secondary">Исполняется {birthday.age} лет</p>
                  <Button size="sm" className="mt-3 w-full">
                    <MessageSquare className="h-4 w-4 mr-2" />
                    Поздравить
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Управление словарем
const DictionaryManagement: React.FC = () => {
  const dictionaries = [
    { id: 1, name: 'Должности', count: 12, lastUpdated: '2025-07-20' },
    { id: 2, name: 'Типы выплат', count: 8, lastUpdated: '2025-07-15' },
    { id: 3, name: 'Отделы', count: 6, lastUpdated: '2025-07-10' },
    { id: 4, name: 'Типы имущества', count: 15, lastUpdated: '2025-07-05' }
  ];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BookOpen className="h-5 w-5" />
            Справочники системы
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {dictionaries.map((dict) => (
              <Card key={dict.id} className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold">{dict.name}</h3>
                    <p className="text-sm text-text-secondary">
                      {dict.count} записей • Обновлено {dict.lastUpdated}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="ghost">
                      <Edit className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="ghost">
                      <Eye className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Настройки системы
const SystemSettings: React.FC = () => {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5" />
              Параметры компании
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Название компании</label>
              <Input defaultValue="ООО Розничная торговля" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Рабочие часы</label>
              <Input defaultValue="09:00 - 21:00" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Лимит выплат</label>
              <Input defaultValue="50000" type="number" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MessageSquare className="h-5 w-5" />
              Настройки Telegram бота
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Токен бота</label>
              <Input type="password" placeholder="Введите токен Telegram бота" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Webhook URL</label>
              <Input placeholder="https://your-domain.com/webhook" />
            </div>
            <Button className="w-full">
              <CheckCircle className="h-4 w-4 mr-2" />
              Проверить подключение
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Резервное копирование</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Button variant="secondary" className="flex-1">
                <Download className="h-4 w-4 mr-2" />
                Скачать конфигурацию
              </Button>
              <Button variant="secondary" className="flex-1">
                <Upload className="h-4 w-4 mr-2" />
                Загрузить конфигурацию
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Отчеты</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Button variant="secondary" className="w-full justify-start">
              <FileText className="h-4 w-4 mr-2" />
              PDF отчет по зарплате
            </Button>
            <Button variant="secondary" className="w-full justify-start">
              <FileText className="h-4 w-4 mr-2" />
              Отчет по сотрудникам
            </Button>
            <Button variant="secondary" className="w-full justify-start">
              <FileText className="h-4 w-4 mr-2" />
              Аналитический отчет
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

// Компонент аналитики продаж
const Analytics: React.FC = () => {
  const topSellers = [
    { id: 1, name: 'Алексей Иванов', sales: 456800, change: '+12%', rank: 1 },
    { id: 2, name: 'Мария Петрова', sales: 389200, change: '+8%', rank: 2 },
    { id: 3, name: 'Дмитрий Сидоров', sales: 324500, change: '+15%', rank: 3 },
    { id: 4, name: 'Анна Смирнова', sales: 287300, change: '+3%', rank: 4 },
    { id: 5, name: 'Петр Козлов', sales: 256900, change: '-2%', rank: 5 }
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-6">
            <div className="text-center">
              <TrendingUp className="h-8 w-8 text-success mx-auto mb-2" />
              <h3 className="font-semibold">Общие продажи</h3>
              <p className="text-2xl font-bold text-success">2,456,800 ₽</p>
              <p className="text-sm text-text-secondary">+15% к прошлому месяцу</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="text-center">
              <BarChart3 className="h-8 w-8 text-primary mx-auto mb-2" />
              <h3 className="font-semibold">Средний чек</h3>
              <p className="text-2xl font-bold">2,840 ₽</p>
              <p className="text-sm text-text-secondary">+8% к прошлому месяцу</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="text-center">
              <Users className="h-8 w-8 text-primary mx-auto mb-2" />
              <h3 className="font-semibold">Клиентов обслужено</h3>
              <p className="text-2xl font-bold">1,248</p>
              <p className="text-sm text-text-secondary">+12% к прошлому месяцу</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="text-center">
              <Clock className="h-8 w-8 text-primary mx-auto mb-2" />
              <h3 className="font-semibold">Рабочие часы</h3>
              <p className="text-2xl font-bold">1,894</p>
              <p className="text-sm text-text-secondary">Всего за месяц</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Рейтинг продавцов</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {topSellers.map((seller) => (
                <div key={seller.id} className="flex items-center justify-between p-3 border border-border-light rounded-lg">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center font-semibold text-sm ${
                      seller.rank <= 3 ? 'bg-primary text-primary-foreground' : 'bg-muted text-text-secondary'
                    }`}>
                      {seller.rank}
                    </div>
                    <div>
                      <p className="font-medium">{seller.name}</p>
                      <p className="text-sm text-text-secondary">
                        {seller.sales.toLocaleString()} ₽
                      </p>
                    </div>
                  </div>
                  <div className={`text-sm font-medium ${
                    seller.change.startsWith('+') ? 'text-success' : 'text-danger'
                  }`}>
                    {seller.change}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>График продаж</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64 bg-muted rounded-lg flex items-center justify-center">
              <div className="text-center">
                <BarChart3 className="h-12 w-12 text-text-secondary mx-auto mb-2" />
                <p className="text-text-secondary">График продаж по дням</p>
                <p className="text-sm text-text-secondary">Интеграция с библиотекой диаграмм</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

// Главный компонент Admin Panel
export const AdminPanel: React.FC = () => {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border-light bg-card">
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-semibold">Портал управления персоналом</h1>
            <Badge variant="secondary">HR System</Badge>
          </div>
          
          <div className="flex items-center gap-4">
            <div className="flex-1 max-w-md">
              <Input placeholder="Поиск..." className="w-full" />
            </div>
            <Button variant="ghost" size="sm">
              <Bell className="h-4 w-4" />
              <Badge className="ml-1 text-xs">3</Badge>
            </Button>
            <Button variant="ghost" size="sm">
              <Settings className="h-4 w-4" />
            </Button>
            <div className="w-8 h-8 bg-primary rounded-full flex items-center justify-center">
              <span className="text-xs text-primary-foreground font-medium">АД</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="p-6">
        <Tabs defaultValue="dashboard" className="space-y-6">
          <TabsList className="grid w-full grid-cols-6 lg:grid-cols-12">
            <TabsTrigger value="dashboard" className="col-span-2">Дашборд</TabsTrigger>
            <TabsTrigger value="employees" className="col-span-2">Сотрудники</TabsTrigger>
            <TabsTrigger value="messaging" className="col-span-2">Рассылка</TabsTrigger>
            <TabsTrigger value="bonuses" className="col-span-2">Штрафы/Премии</TabsTrigger>
            <TabsTrigger value="payments" className="col-span-2">Выплаты</TabsTrigger>
            <TabsTrigger value="control" className="col-span-2">Контроль</TabsTrigger>
            <TabsTrigger value="vacations" className="col-span-2">Отпуска</TabsTrigger>
            <TabsTrigger value="property" className="col-span-2">Имущество</TabsTrigger>
            <TabsTrigger value="analytics" className="col-span-2">Аналитика</TabsTrigger>
            <TabsTrigger value="birthdays" className="col-span-2">Дни рождения</TabsTrigger>
            <TabsTrigger value="dictionary" className="col-span-2">Словарь</TabsTrigger>
            <TabsTrigger value="settings" className="col-span-2">Настройки</TabsTrigger>
          </TabsList>
          
          <TabsContent value="dashboard">
            <Dashboard />
          </TabsContent>
          
          <TabsContent value="employees">
            <UsersManagement />
          </TabsContent>
          
          <TabsContent value="messaging">
            <MessagingSystem />
          </TabsContent>
          
          <TabsContent value="bonuses">
            <BonusesAndPenalties />
          </TabsContent>
          
          <TabsContent value="payments">
            <PaymentsManagement />
          </TabsContent>
          
          <TabsContent value="control">
            <PaymentControl />
          </TabsContent>
          
          <TabsContent value="vacations">
            <VacationsManagement />
          </TabsContent>
          
          <TabsContent value="property">
            <PropertyManagement />
          </TabsContent>
          
          <TabsContent value="analytics">
            <Analytics />
          </TabsContent>
          
          <TabsContent value="birthdays">
            <BirthdaysManagement />
          </TabsContent>
          
          <TabsContent value="dictionary">
            <DictionaryManagement />
          </TabsContent>
          
          <TabsContent value="settings">
            <SystemSettings />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};