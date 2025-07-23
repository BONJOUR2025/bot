import colors from 'tailwindcss/colors';
import { fontFamily } from 'tailwindcss/defaultTheme';

export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#FF6600',
        secondary: '#666666',
      },
      fontFamily: {
        sans: ['Roboto', ...fontFamily.sans],
      },
    },
  },
  plugins: [],
};
