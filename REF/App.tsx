import React, { useState } from 'react';
import { Button } from './components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from './components/ui/card';
import { Badge } from './components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { TelegramInterface } from './components/telegram/TelegramInterface';
import { AdminPanel } from './components/admin/AdminPanel';
import { DesignTokensDemo } from './components/design-system/DesignTokens';
import { StatusBadge } from './components/design-system/StatusBadge';
import { ActionCard } from './components/design-system/ActionCard';
import { 
  Smartphone, 
  Monitor, 
  Palette, 
  Users, 
  BarChart3, 
  Settings,
  Layers,
  Code,
  Zap,
  DollarSign,
  Calendar as CalendarIcon,
  Package,
  MessageSquare,
  FileText
} from 'lucide-react';

type ViewMode = 'overview' | 'telegram' | 'admin' | 'tokens';

export default function App() {
  const [viewMode, setViewMode] = useState<ViewMode>('overview');

  // Обзорная страница с описанием системы
  const OverviewPage = () => (
    <div className="min-h-screen bg-background">
      {/* Hero Section */}
      <div className="bg-primary text-primary-foreground py-16">
        <div className="max-w-6xl mx-auto px-6 text-center">
          <h1 className="text-4xl font-bold mb-4">
            Портал управления персоналом
          </h1>
          <p className="text-xl opacity-90 mb-8">
            Полнофункциональная система HR с Telegram-ботом и веб-интерфейсом
          </p>
          <div className="flex justify-center gap-4">
            <Button 
              onClick={() => setViewMode('telegram')}
              variant="secondary"
              size="lg"
            >
              <Smartphone className="h-5 w-5 mr-2" />
              Telegram Bot
            </Button>
            <Button 
              onClick={() => setViewMode('admin')}
              variant="secondary"
              size="lg"
            >
              <Monitor className="h-5 w-5 mr-2" />
              HR Portal
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-16">
        {/* Основные модули */}
        <div className="mb-16">
          <h2 className="text-3xl font-bold text-center mb-12">
            Основные модули системы
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            <ActionCard
              title="👥 Управление сотрудниками"
              description="Ведение кадровых данных, фильтры, экспорт в PDF"
              icon={<Users className="h-6 w-6" />}
              variant="highlighted"
            />
            <ActionCard
              title="💰 Система выплат"
              description="Заявки на аванс, премии, контроль лимитов"
              icon={<DollarSign className="h-6 w-6" />}
              variant="highlighted"
            />
            <ActionCard
              title="📊 Аналитика продаж"
              description="Статистика, рейтинги, отчетность по продажам"
              icon={<BarChart3 className="h-6 w-6" />}
              variant="highlighted"
            />
            <ActionCard
              title="🏖️ Отпуска и больничные"
              description="Календарь отпусков, заявки, статистика"
              icon={<CalendarIcon className="h-6 w-6" />}
              variant="highlighted"
            />
            <ActionCard
              title="📦 Учет имущества"
              description="Выдача оборудования, формы, контроль возврата"
              icon={<Package className="h-6 w-6" />}
              variant="highlighted"
            />
            <ActionCard
              title="📧 Система рассылок"
              description="Уведомления через Telegram, шаблоны сообщений"
              icon={<MessageSquare className="h-6 w-6" />}
              variant="highlighted"
            />
          </div>
        </div>

        {/* Компоненты системы */}
        <div className="mb-16">
          <h2 className="text-3xl font-bold text-center mb-12">
            Компоненты системы
          </h2>
          
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Статус-бейджи */}
            <Card>
              <CardHeader>
                <CardTitle>Status Badges</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge status="approved" />
                    <StatusBadge status="rejected" />
                    <StatusBadge status="waiting" />
                    <StatusBadge status="processing" />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge status="active" size="sm" />
                    <StatusBadge status="inactive" size="sm" />
                    <StatusBadge status="approved" size="lg" />
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Action Cards */}
            <Card>
              <CardHeader>
                <CardTitle>Action Cards</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <ActionCard
                    title="Быстрое действие"
                    description="Описание действия"
                    variant="compact"
                    icon={<Users className="h-5 w-5" />}
                    actions={[
                      { label: 'Выполнить', onClick: () => {} }
                    ]}
                  />
                  <ActionCard
                    title="Важное действие"
                    variant="highlighted"
                    actions={[
                      { label: 'Принять', onClick: () => {}, variant: 'default' },
                      { label: 'Отклонить', onClick: () => {}, variant: 'destructive' }
                    ]}
                  />
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Сценарии использования */}
        <div className="mb-16">
          <h2 className="text-3xl font-bold text-center mb-12">
            Сценарии использования
          </h2>
          
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5" />
                  Кадровое администрирование
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  <li>• HR-специалист ведет список сотрудников</li>
                  <li>• Обновление личных данных и должностей</li>
                  <li>• Управление отпусками и больничными</li>
                  <li>• Учет выданного имущества</li>
                  <li>• Экспорт отчетов в PDF</li>
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <DollarSign className="h-5 w-5" />
                  Финансы и выплаты
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  <li>• Бухгалтер просматривает заявки на выплаты</li>
                  <li>• Утверждение авансов и премий</li>
                  <li>• Контроль лимитов и подозрительной активности</li>
                  <li>• Анализ превышений и длительных ожиданий</li>
                  <li>• Автоматические предупреждения</li>
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <MessageSquare className="h-5 w-5" />
                  Коммуникации
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  <li>• Администратор рассылает сообщения через Telegram</li>
                  <li>• Использование готовых шаблонов</li>
                  <li>• Выборочная отправка по отделам</li>
                  <li>• Уведомления о зарплате и сменах</li>
                  <li>• Поздравления с днем рождения</li>
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5" />
                  Аналитика и отчетность
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  <li>• Руководитель анализирует продажи</li>
                  <li>• Рейтинг сотрудников по выручке</li>
                  <li>• Статистика по чекам и среднему чеку</li>
                  <li>• Отчеты по зарплате и состоянию базы</li>
                  <li>• Настройка параметров через интерфейс</li>
                </ul>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Демо интерфейсов */}
        <div className="mb-16">
          <h2 className="text-3xl font-bold text-center mb-12">
            Демонстрация интерфейсов
          </h2>
          
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Telegram Demo */}
            <Card className="overflow-hidden">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Smartphone className="h-5 w-5" />
                  Telegram Bot для сотрудников
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="aspect-[9/16] bg-muted rounded-lg overflow-hidden">
                  <div className="scale-75 origin-top-left">
                    <div className="w-[375px] h-[667px] bg-background border border-border-light rounded-lg overflow-hidden">
                      <TelegramInterface />
                    </div>
                  </div>
                </div>
                <div className="mt-4 text-center">
                  <Button 
                    onClick={() => setViewMode('telegram')}
                    variant="secondary"
                  >
                    Открыть полную версию
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Admin Panel Demo */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Monitor className="h-5 w-5" />
                  HR Portal для администраторов
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="aspect-video bg-muted rounded-lg overflow-hidden">
                  <div className="scale-50 origin-top-left">
                    <div className="w-[1200px] h-[800px] bg-background border border-border-light rounded-lg overflow-hidden">
                      <AdminPanel />
                    </div>
                  </div>
                </div>
                <div className="mt-4 text-center">
                  <Button 
                    onClick={() => setViewMode('admin')}
                    variant="secondary"
                  >
                    Открыть полную версию
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Технические возможности */}
        <div className="text-center">
          <h2 className="text-3xl font-bold mb-8">
            Технические возможности
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <Card>
              <CardContent className="p-6 text-center">
                <Code className="h-12 w-12 text-primary mx-auto mb-4" />
                <h3 className="font-semibold mb-2">FastAPI + React</h3>
                <p className="text-sm text-text-secondary">
                  Backend API с современным фронтендом
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardContent className="p-6 text-center">
                <MessageSquare className="h-12 w-12 text-primary mx-auto mb-4" />
                <h3 className="font-semibold mb-2">Telegram Bot API</h3>
                <p className="text-sm text-text-secondary">
                  Интеграция с Telegram для сотрудников
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardContent className="p-6 text-center">
                <FileText className="h-12 w-12 text-primary mx-auto mb-4" />
                <h3 className="font-semibold mb-2">PDF Отчеты</h3>
                <p className="text-sm text-text-secondary">
                  Экспорт данных в PDF формат
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardContent className="p-6 text-center">
                <Settings className="h-12 w-12 text-primary mx-auto mb-4" />
                <h3 className="font-semibold mb-2">Конфигурация</h3>
                <p className="text-sm text-text-secondary">
                  Настройка через веб-интерфейс
                </p>
              </CardContent>
            </Card>
          </div>
          
          <div className="mt-12 space-y-4">
            <div className="flex justify-center gap-4">
              <Button 
                onClick={() => setViewMode('tokens')}
                variant="outline"
                size="lg"
              >
                <Palette className="h-5 w-5 mr-2" />
                Design Tokens
              </Button>
              <Button 
                onClick={() => setViewMode('admin')}
                variant="default"
                size="lg"
              >
                <Monitor className="h-5 w-5 mr-2" />
                Попробовать систему
              </Button>
            </div>
            
            <p className="text-sm text-text-secondary max-w-2xl mx-auto">
              Полнофункциональный портал управления персоналом объединяет кадровое администрирование, 
              учет выплат и имущества, аналитику продаж и системные настройки в едином интерфейсе.
            </p>
          </div>
        </div>
      </div>
    </div>
  );

  // Навигация
  const Navigation = () => (
    <div className="fixed top-4 left-4 z-50">
      <div className="flex gap-2">
        <Button
          variant={viewMode === 'overview' ? 'default' : 'secondary'}
          size="sm"
          onClick={() => setViewMode('overview')}
        >
          Обзор
        </Button>
        <Button
          variant={viewMode === 'telegram' ? 'default' : 'secondary'}
          size="sm"
          onClick={() => setViewMode('telegram')}
        >
          <Smartphone className="h-4 w-4 mr-1" />
          Telegram
        </Button>
        <Button
          variant={viewMode === 'admin' ? 'default' : 'secondary'}
          size="sm"
          onClick={() => setViewMode('admin')}
        >
          <Monitor className="h-4 w-4 mr-1" />
          Admin
        </Button>
        <Button
          variant={viewMode === 'tokens' ? 'default' : 'secondary'}
          size="sm"
          onClick={() => setViewMode('tokens')}
        >
          <Palette className="h-4 w-4 mr-1" />
          Tokens
        </Button>
      </div>
    </div>
  );

  return (
    <div className="relative">
      {viewMode !== 'overview' && <Navigation />}
      
      {viewMode === 'overview' && <OverviewPage />}
      
      {viewMode === 'telegram' && (
        <div className="min-h-screen flex items-center justify-center bg-muted p-4">
          <TelegramInterface />
        </div>
      )}
      
      {viewMode === 'admin' && <AdminPanel />}
      
      {viewMode === 'tokens' && (
        <div className="min-h-screen bg-background p-8">
          <div className="max-w-4xl mx-auto">
            <div className="mb-8">
              <h1 className="text-3xl font-bold mb-4">Design System Tokens</h1>
              <p className="text-text-secondary">
                Основные токены дизайн-системы для унифицированного UI
              </p>
            </div>
            <DesignTokensDemo />
          </div>
        </div>
      )}
    </div>
  );
}