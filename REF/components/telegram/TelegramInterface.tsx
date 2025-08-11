import React, { useState } from 'react';
import { Card, CardContent, CardHeader } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { StatusBadge } from '../design-system/StatusBadge';
import { ActionCard } from '../design-system/ActionCard';
import { 
  DollarSign, 
  Clock, 
  Users, 
  BarChart3, 
  ArrowLeft,
  Plus,
  CheckCircle,
  AlertCircle
} from 'lucide-react';

interface TelegramScreen {
  id: string;
  title: string;
  component: React.ComponentType<{ onNavigate: (screenId: string) => void }>;
}

// Главное меню Telegram
const MainMenuScreen: React.FC<{ onNavigate: (screenId: string) => void }> = ({ onNavigate }) => {
  const menuItems = [
    {
      title: '💰 Запрос выплаты',
      description: 'Подать заявку на аванс или зарплату',
      onClick: () => onNavigate('payment-request'),
      icon: '💰'
    },
    {
      title: '📊 Мои продажи',
      description: 'Статистика продаж и рейтинг',
      onClick: () => onNavigate('my-sales'),
      icon: '📊'
    },
    {
      title: '🏖️ Отпуск',
      description: 'Подать заявку на отпуск или больничный',
      onClick: () => onNavigate('vacation-request'),
      icon: '🏖️'
    },
    {
      title: '📦 Мое имущество',
      description: 'Выданное оборудование и форма',
      onClick: () => onNavigate('my-property'),
      icon: '📦'
    },
    {
      title: '🎂 Дни рождения',
      description: 'Ближайшие дни рождения коллег',
      onClick: () => onNavigate('birthdays'),
      icon: '🎂'
    },
    {
      title: '💼 Моя информация',
      description: 'Личные данные и контакты',
      onClick: () => onNavigate('profile'),
      icon: '💼'
    }
  ];

  return (
    <div className="space-y-3">
      <div className="bg-primary text-primary-foreground p-4 rounded-lg">
        <h2 className="font-semibold">👋 Привет, Алексей!</h2>
        <p className="text-sm opacity-90 mt-1">
          Продажи сегодня: <strong>24,850 ₽</strong> • Рейтинг: <strong>#3</strong>
        </p>
        <div className="flex gap-4 mt-2 text-xs">
          <span>🏆 Чеков: 18</span>
          <span>💰 Средний чек: 1,380 ₽</span>
        </div>
      </div>

      <div className="space-y-2">
        {menuItems.map((item, index) => (
          <ActionCard
            key={index}
            title={item.title}
            description={item.description}
            variant="compact"
            actions={[
              {
                label: 'Открыть',
                onClick: item.onClick,
                variant: 'default'
              }
            ]}
          />
        ))}
      </div>

      {/* Уведомления и быстрые действия */}
      <div className="space-y-3">
        <div className="bg-warning/10 border border-warning/20 p-3 rounded-lg">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-warning" />
            <span className="text-sm font-medium">Уведомления</span>
          </div>
          <p className="text-sm text-text-secondary mt-1">
            ✅ Заявка на аванс одобрена: 15,000 ₽
          </p>
        </div>
        
        <div className="bg-muted p-4 rounded-lg">
          <h3 className="font-medium mb-3">⚡ Быстрые действия</h3>
          <div className="grid grid-cols-2 gap-2">
            <Button size="sm" variant="secondary">
              📊 Сводка дня
            </Button>
            <Button size="sm" variant="secondary">
              💬 Поддержка
            </Button>
            <Button size="sm" variant="secondary">
              📋 Мой график
            </Button>
            <Button size="sm" variant="secondary">
              🎯 План продаж
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

// Экран запроса выплаты
const PaymentRequestScreen: React.FC<{ onNavigate: (screenId: string) => void }> = ({ onNavigate }) => {
  const [paymentType, setPaymentType] = useState('advance');
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = () => {
    setSubmitted(true);
    setTimeout(() => {
      onNavigate('main');
    }, 2000);
  };

  if (submitted) {
    return (
      <div className="space-y-4">
        <div className="text-center py-8">
          <CheckCircle className="h-16 w-16 text-success mx-auto mb-4" />
          <h2 className="font-semibold text-lg">Заявка отправлена!</h2>
          <p className="text-text-secondary mt-2">
            Заявка на {paymentType === 'advance' ? 'аванс' : 'премию'} {amount} ₽ передана HR
          </p>
          <StatusBadge status="processing" size="lg" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Button 
        variant="ghost" 
        onClick={() => onNavigate('main')}
        className="mb-2"
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Назад
      </Button>

      <Card>
        <CardHeader>
          <h2 className="font-semibold">💰 Запрос выплаты</h2>
          <p className="text-sm text-text-secondary">
            Доступно для аванса: <strong>18,200 ₽</strong>
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">Тип выплаты</label>
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant={paymentType === 'advance' ? 'default' : 'secondary'}
                onClick={() => setPaymentType('advance')}
                className="text-sm"
              >
                💰 Аванс
              </Button>
              <Button
                variant={paymentType === 'bonus' ? 'default' : 'secondary'}
                onClick={() => setPaymentType('bonus')}
                className="text-sm"
              >
                🎁 Премия
              </Button>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">
              Сумма ({paymentType === 'advance' ? 'аванса' : 'премии'}) ₽
            </label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="Введите сумму"
              className="w-full p-3 border border-border-light rounded-lg"
              max={paymentType === 'advance' ? '18200' : '50000'}
            />
          </div>

          {paymentType === 'bonus' && (
            <div>
              <label className="block text-sm font-medium mb-2">Основание для премии</label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Опишите основание для премии..."
                className="w-full h-20 p-3 border border-border-light rounded-lg resize-none"
              />
            </div>
          )}

          <div className="bg-muted p-3 rounded-lg">
            <h4 className="font-medium text-sm mb-2">ℹ️ Условия:</h4>
            <ul className="text-xs text-text-secondary space-y-1">
              {paymentType === 'advance' ? (
                <>
                  <li>• Максимум 50% от заработка</li>
                  <li>• Удержание при следующей зарплате</li>
                  <li>• Рассмотрение до 2 часов</li>
                </>
              ) : (
                <>
                  <li>• Требуется обоснование</li>
                  <li>• Рассмотрение до 24 часов</li>
                  <li>• Зависит от показателей работы</li>
                </>
              )}
            </ul>
          </div>

          <Button 
            onClick={handleSubmit}
            disabled={!amount || (paymentType === 'bonus' && !reason)}
            className="w-full"
          >
            📤 Отправить заявку
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};

// Экран "Мои продажи"
const MySalesScreen: React.FC<{ onNavigate: (screenId: string) => void }> = ({ onNavigate }) => {
  const salesData = [
    {
      date: '25 июля',
      checks: 18,
      amount: 24850,
      avgCheck: 1380,
      rank: 3
    },
    {
      date: '24 июля', 
      checks: 15,
      amount: 19200,
      avgCheck: 1280,
      rank: 5
    },
    {
      date: '23 июля',
      checks: 22,
      amount: 31400,
      avgCheck: 1427,
      rank: 2
    }
  ];

  return (
    <div className="space-y-4">
      <Button 
        variant="ghost" 
        onClick={() => onNavigate('main')}
        className="mb-2"
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Назад
      </Button>

      <div className="bg-primary text-primary-foreground p-4 rounded-lg">
        <h2 className="font-semibold">📊 Мои продажи</h2>
        <p className="text-sm opacity-90 mt-1">
          За неделю: <strong>75,450 ₽</strong> • Рейтинг: <strong>#3 из 89</strong>
        </p>
        <div className="flex gap-4 mt-2 text-xs">
          <span>🏆 Чеков: 55</span>
          <span>📈 Рост: +12%</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Card>
          <CardContent className="p-3 text-center">
            <p className="text-2xl font-bold text-success">24,850 ₽</p>
            <p className="text-xs text-text-secondary">Сегодня</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3 text-center">
            <p className="text-2xl font-bold text-primary">1,380 ₽</p>
            <p className="text-xs text-text-secondary">Средний чек</p>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-3">
        {salesData.map((day, index) => (
          <Card key={index}>
            <CardContent className="p-4">
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="font-medium">{day.date}</h3>
                  <p className="text-sm text-text-secondary">
                    {day.checks} чеков • Средний: {day.avgCheck} ₽
                  </p>
                </div>
                <div className="text-right">
                  <div className="text-lg font-semibold text-success">
                    {day.amount.toLocaleString()} ₽
                  </div>
                  <Badge variant={day.rank <= 3 ? 'default' : 'secondary'}>
                    #{day.rank} место
                  </Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Button variant="secondary" className="text-sm">
          🎯 План месяца
        </Button>
        <Button variant="secondary" className="text-sm">
          📈 Статистика
        </Button>
      </div>
    </div>
  );
};

// Экран запроса отпуска
const VacationRequestScreen: React.FC<{ onNavigate: (screenId: string) => void }> = ({ onNavigate }) => {
  const [vacationType, setVacationType] = useState('vacation');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  return (
    <div className="space-y-4">
      <Button variant="ghost" onClick={() => onNavigate('main')} className="mb-2">
        <ArrowLeft className="h-4 w-4 mr-2" />
        Назад
      </Button>

      <Card>
        <CardHeader>
          <h2 className="font-semibold">🏖️ Заявка на отпуск</h2>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">Тип отсутствия</label>
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant={vacationType === 'vacation' ? 'default' : 'secondary'}
                onClick={() => setVacationType('vacation')}
                className="text-sm"
              >
                🏖️ Отпуск
              </Button>
              <Button
                variant={vacationType === 'sick' ? 'default' : 'secondary'}
                onClick={() => setVacationType('sick')}
                className="text-sm"
              >
                🏥 Больничный
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-2">Дата начала</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full p-2 border border-border-light rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Дата окончания</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full p-2 border border-border-light rounded-lg text-sm"
              />
            </div>
          </div>

          <Button className="w-full">
            📤 Отправить заявку
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};

// Экран моего имущества
const MyPropertyScreen: React.FC<{ onNavigate: (screenId: string) => void }> = ({ onNavigate }) => {
  const propertyItems = [
    { name: 'Рабочая форма', category: 'Одежда', status: 'Выдано', date: '2025-06-01' },
    { name: 'Планшет Samsung', category: 'Техника', status: 'Выдано', date: '2025-06-15' },
    { name: 'Сканер штрих-кодов', category: 'Оборудование', status: 'Возвращено', date: '2025-07-20' }
  ];

  return (
    <div className="space-y-4">
      <Button variant="ghost" onClick={() => onNavigate('main')} className="mb-2">
        <ArrowLeft className="h-4 w-4 mr-2" />
        Назад
      </Button>

      <div className="bg-primary text-primary-foreground p-4 rounded-lg">
        <h2 className="font-semibold">📦 Мое имущество</h2>
        <p className="text-sm opacity-90 mt-1">
          Выдано: <strong>2 предмета</strong> • Возвращено: <strong>1</strong>
        </p>
      </div>

      <div className="space-y-3">
        {propertyItems.map((item, index) => (
          <Card key={index}>
            <CardContent className="p-4">
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="font-medium">{item.name}</h3>
                  <p className="text-sm text-text-secondary">{item.category}</p>
                  <p className="text-xs text-text-secondary">Выдано: {item.date}</p>
                </div>
                <Badge variant={item.status === 'Выдано' ? 'default' : 'secondary'}>
                  {item.status}
                </Badge>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Button className="w-full" variant="secondary">
        📋 Запросить имущество
      </Button>
    </div>
  );
};

// Экран дней рождения
const BirthdaysScreen: React.FC<{ onNavigate: (screenId: string) => void }> = ({ onNavigate }) => {
  const birthdays = [
    { name: 'Анна Смирнова', date: '27 июля', department: 'Отдел продаж' },
    { name: 'Петр Козлов', date: '30 июля', department: 'Склад' },
    { name: 'Елена Васильева', date: '2 августа', department: 'Администрация' }
  ];

  return (
    <div className="space-y-4">
      <Button variant="ghost" onClick={() => onNavigate('main')} className="mb-2">
        <ArrowLeft className="h-4 w-4 mr-2" />
        Назад
      </Button>

      <div className="bg-primary text-primary-foreground p-4 rounded-lg">
        <h2 className="font-semibold">🎂 Дни рождения</h2>
        <p className="text-sm opacity-90 mt-1">
          Ближайшие дни рождения коллег
        </p>
      </div>

      <div className="space-y-3">
        {birthdays.map((birthday, index) => (
          <Card key={index}>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center">
                  🎂
                </div>
                <div className="flex-1">
                  <h3 className="font-medium">{birthday.name}</h3>
                  <p className="text-sm text-text-secondary">{birthday.department}</p>
                </div>
                <div className="text-right">
                  <p className="font-medium text-primary">{birthday.date}</p>
                  <Button size="sm" className="mt-1">
                    🎉 Поздравить
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

// Экран профиля
const ProfileScreen: React.FC<{ onNavigate: (screenId: string) => void }> = ({ onNavigate }) => {
  const profileData = {
    name: 'Алексей Иванов',
    position: 'Продавец-консультант',
    department: 'Отдел косметики',
    phone: '+7 (999) 123-45-67',
    email: 'alexey.ivanov@company.com',
    startDate: '2024-03-15',
    birthDate: '1990-12-08'
  };

  return (
    <div className="space-y-4">
      <Button variant="ghost" onClick={() => onNavigate('main')} className="mb-2">
        <ArrowLeft className="h-4 w-4 mr-2" />
        Назад
      </Button>

      <Card>
        <CardContent className="p-6">
          <div className="text-center mb-6">
            <div className="w-20 h-20 bg-primary rounded-full flex items-center justify-center mx-auto mb-3">
              <span className="text-2xl text-primary-foreground font-semibold">АИ</span>
            </div>
            <h2 className="text-xl font-semibold">{profileData.name}</h2>
            <p className="text-text-secondary">{profileData.position}</p>
          </div>

          <div className="space-y-4">
            <div className="flex justify-between">
              <span className="text-text-secondary">Отдел:</span>
              <span className="font-medium">{profileData.department}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Телефон:</span>
              <span className="font-medium">{profileData.phone}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Email:</span>
              <span className="font-medium text-sm">{profileData.email}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Дата приема:</span>
              <span className="font-medium">{profileData.startDate}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">День рождения:</span>
              <span className="font-medium">{profileData.birthDate}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      <Button className="w-full" variant="secondary">
        ✏️ Редактировать профиль
      </Button>
    </div>
  );
};

// Главный компонент Telegram интерфейса
export const TelegramInterface: React.FC = () => {
  const [currentScreen, setCurrentScreen] = useState('main');

  const screens: Record<string, TelegramScreen> = {
    main: {
      id: 'main',
      title: 'Главное меню',
      component: MainMenuScreen
    },
    'payment-request': {
      id: 'payment-request',
      title: 'Запрос выплаты',
      component: PaymentRequestScreen
    },
    'my-sales': {
      id: 'my-sales',
      title: 'Мои продажи',
      component: MySalesScreen
    },
    'vacation-request': {
      id: 'vacation-request',
      title: 'Заявка на отпуск',
      component: VacationRequestScreen
    },
    'my-property': {
      id: 'my-property',
      title: 'Мое имущество',
      component: MyPropertyScreen
    },
    birthdays: {
      id: 'birthdays',
      title: 'Дни рождения',
      component: BirthdaysScreen
    },
    profile: {
      id: 'profile',
      title: 'Мой профиль',
      component: ProfileScreen
    }
  };

  const CurrentScreenComponent = screens[currentScreen]?.component || MainMenuScreen;

  return (
    <div className="max-w-sm mx-auto bg-background min-h-screen">
      {/* Telegram-style header */}
      <div className="bg-primary text-primary-foreground p-4 sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-primary-foreground/20 rounded-full flex items-center justify-center">
            <Users className="h-4 w-4" />
          </div>
          <div>
            <h1 className="font-semibold">HR Portal Bot</h1>
            <p className="text-xs opacity-75">Система управления персоналом</p>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        <CurrentScreenComponent onNavigate={setCurrentScreen} />
      </div>
    </div>
  );
};