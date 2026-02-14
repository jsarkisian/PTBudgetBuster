/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        dark: {
          50: '#f0f0f0',
          100: '#d4d4d4',
          200: '#a3a3a3',
          300: '#737373',
          400: '#525252',
          500: '#404040',
          600: '#2d2d2d',
          700: '#1e1e1e',
          800: '#171717',
          900: '#0f0f0f',
          950: '#0a0a0a',
        },
        accent: {
          red: '#ef4444',
          orange: '#f97316',
          yellow: '#eab308',
          green: '#22c55e',
          blue: '#3b82f6',
          purple: '#a855f7',
          cyan: '#06b6d4',
        },
      },
    },
  },
  plugins: [],
}
