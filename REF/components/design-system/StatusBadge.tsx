import React from 'react';
import { Badge } from '../ui/badge';
import { cn } from '../ui/utils';

export interface StatusBadgeProps {
  status:
    | 'approved'
    | 'rejected'
    | 'waiting'
    | 'active'
    | 'inactive'
    | 'processing'
    | 'paid';
  size?: 'sm' | 'md' | 'lg';
  variant?: 'default' | 'outline';
}

const statusConfig = {
  approved: {
    label: 'Одобрено',
    className: 'bg-success text-success-foreground border-success',
    emoji: '✅'
  },
  rejected: {
    label: 'Отклонено',
    className: 'bg-danger text-danger-foreground border-danger',
    emoji: '❌'
  },
  waiting: {
    label: 'Ожидание',
    className: 'bg-warning text-warning-foreground border-warning',
    emoji: '⏳'
  },
  active: {
    label: 'Активен',
    className: 'bg-success text-success-foreground border-success',
    emoji: '🟢'
  },
  inactive: {
    label: 'Неактивен',
    className: 'bg-muted text-muted-foreground border-muted',
    emoji: '⚫'
  },
  processing: {
    label: 'Обработка',
    className: 'bg-primary text-primary-foreground border-primary',
    emoji: '🔄'
  },
  paid: {
    label: 'Выплачено',
    className: 'bg-primary text-primary-foreground border-primary',
    emoji: '📤'
  },
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ 
  status, 
  size = 'md',
  variant = 'default'
}) => {
  const config = statusConfig[status];
  
  const sizeClasses = {
    sm: 'text-xs px-2 py-1',
    md: 'text-sm px-3 py-1.5',
    lg: 'text-base px-4 py-2'
  };

  return (
    <Badge 
      variant={variant}
      className={cn(
        sizeClasses[size],
        variant === 'default' && config.className,
        variant === 'outline' && 'border-2',
        'inline-flex items-center gap-1 font-medium'
      )}
    >
      <span>{config.emoji}</span>
      {config.label}
    </Badge>
  );
};