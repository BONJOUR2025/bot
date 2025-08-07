import React from 'react';

// Design System Tokens - основные константы дизайн-системы
export const designTokens = {
  // Typography Scale
  typography: {
    h1: { size: '32px', weight: 700, lineHeight: 1.2 },
    h2: { size: '24px', weight: 600, lineHeight: 1.3 },
    h3: { size: '20px', weight: 600, lineHeight: 1.4 },
    body: { size: '16px', weight: 400, lineHeight: 1.5 },
    caption: { size: '12px', weight: 500, lineHeight: 1.4 },
    small: { size: '14px', weight: 400, lineHeight: 1.4 },
  },

  // Color Palette
  colors: {
    primary: '#3B82F6',
    success: '#10B981',
    danger: '#EF4444',
    warning: '#F59E0B',
    
    // Backgrounds
    backgroundLight: '#F9FAFB',
    backgroundDefault: '#FFFFFF',
    
    // Text
    textPrimary: '#111827',
    textSecondary: '#6B7280',
    textMuted: '#9CA3AF',
    
    // Borders
    borderLight: '#E5E7EB',
    borderMedium: '#D1D5DB',
    borderDark: '#9CA3AF',
  },

  // Spacing (8pt grid)
  spacing: {
    xs: '4px',
    sm: '8px',
    md: '16px',
    lg: '24px',
    xl: '32px',
    xxl: '48px',
  },

  // Border Radius
  radius: {
    sm: '4px',
    md: '8px',
    lg: '12px',
    xl: '16px',
  },

  // Shadows
  shadows: {
    sm: '0 1px 2px 0 rgb(0 0 0 / 0.05)',
    md: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
    lg: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
  },

  // Breakpoints
  breakpoints: {
    mobile: '375px',
    tablet: '768px',
    desktop: '1440px',
  },
};

// Component для демонстрации токенов
export const DesignTokensDemo: React.FC = () => {
  return (
    <div className="p-6 space-y-8">
      <div>
        <h2 className="mb-4">Typography Scale</h2>
        <div className="space-y-2">
          <div style={designTokens.typography.h1}>H1 Heading - 32px Bold</div>
          <div style={designTokens.typography.h2}>H2 Heading - 24px Semibold</div>
          <div style={designTokens.typography.h3}>H3 Heading - 20px Semibold</div>
          <div style={designTokens.typography.body}>Body Text - 16px Regular</div>
          <div style={designTokens.typography.caption}>Caption - 12px Medium</div>
        </div>
      </div>

      <div>
        <h2 className="mb-4">Color Palette</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Object.entries(designTokens.colors).map(([name, color]) => (
            <div key={name} className="flex flex-col items-center">
              <div 
                className="w-16 h-16 rounded-lg shadow-md"
                style={{ backgroundColor: color }}
              />
              <span className="text-sm mt-2">{name}</span>
              <span className="text-xs text-muted-foreground">{color}</span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="mb-4">Spacing Scale (8pt grid)</h2>
        <div className="space-y-2">
          {Object.entries(designTokens.spacing).map(([name, size]) => (
            <div key={name} className="flex items-center gap-4">
              <div className="w-16 text-sm">{name}</div>
              <div 
                className="bg-primary h-4 rounded"
                style={{ width: size }}
              />
              <span className="text-sm text-muted-foreground">{size}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};