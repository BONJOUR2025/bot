import colors from 'tailwindcss/colors';
import { fontFamily } from 'tailwindcss/defaultTheme';

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#FF6600',
        secondary: '#666666',
        brand: {
          DEFAULT: '#FF6600',
          light: '#FFD6B3',
          dark: '#CC5200',
        },
        surface: '#F9F9FB',
        accent: '#3B82F6',
      },
      fontFamily: {
        sans: ['Roboto', ...fontFamily.sans],
      },
    },
  },
  plugins: [],
};
