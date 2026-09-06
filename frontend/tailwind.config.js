/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        terracotta: {
          DEFAULT: '#E05D38',
          hover: '#C84B27',
          light: '#FBE9E4',
          dark: '#A33719',
        },
        amber: {
          DEFAULT: '#F59E0B',
          light: '#FEF3C7',
          hover: '#D97706',
          dark: '#B45309',
        },
        teal: {
          DEFAULT: '#0D9488',
          light: '#CCFBF1',
          hover: '#0F766E',
          dark: '#115E59',
        },
        surface: {
          base: '#FDFBF7',
          card: '#FFFFFF',
          muted: '#F8F6F0',
          border: '#EADBCC',
        },
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
