import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './card';
import { Button } from './button';
import { cn } from './utils';

export function ActionCard({
  title,
  description,
  icon,
  actions = [],
  variant = 'default',
  children,
  className,
}) {
  const variantClasses = {
    default: 'border border-border-light',
    compact: 'border border-border-light p-4',
    highlighted: 'border-2 border-primary bg-primary/5',
  };

  return (
    <Card className={cn(variantClasses[variant], className)}>
      <CardHeader className={variant === 'compact' ? 'p-0 pb-3' : undefined}>
        <CardTitle className="flex items-center gap-3">
          {icon && <div className="text-primary">{icon}</div>}
          <div>
            <div>{title}</div>
            {description && <div className="text-sm text-text-secondary font-normal mt-1">{description}</div>}
          </div>
        </CardTitle>
      </CardHeader>
      {children && <CardContent className={variant === 'compact' ? 'p-0 py-3' : undefined}>{children}</CardContent>}
      {actions.length > 0 && (
        <CardContent className={cn('flex gap-2 pt-0', variant === 'compact' ? 'p-0 pt-3' : undefined)}>
          {actions.map((action, index) => (
            <Button
              key={index}
              variant={action.variant || 'default'}
              size="sm"
              onClick={action.onClick}
              disabled={action.disabled}
            >
              {action.label}
            </Button>
          ))}
        </CardContent>
      )}
    </Card>
  );
}
