/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'sidebar-mist': '#f9f9f9',
        'pure-white': '#ffffff',
        'graphite-ink': '#0d0d0d',
        'mid-ash': '#5d5d5d',
        'hollow': '#8f8f8f',
        'hairline': 'rgba(0, 0, 0, 0.1)',
        'hover-veil': 'rgba(0, 0, 0, 0.05)',
        'ink-press': '#000000',
        'deep-charcoal': 'rgba(0, 0, 0, 0.5)',
        'edge-gray': '#e6e6e6',

        // Semantic Aliases
        surface: {
          base: '#ffffff',
          sidebar: '#f9f9f9',
          panel: '#ffffff',
          border: 'rgba(0, 0, 0, 0.1)',
        },
        ink: {
          DEFAULT: '#0d0d0d',
          secondary: '#5d5d5d',
          tertiary: '#8f8f8f',
        },
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          'system-ui',
          'sans-serif',
        ],
      },
      fontSize: {
        'caption': ['14px', { lineHeight: '1.43' }],
        'body': ['16px', { lineHeight: '1.5' }],
        'heading': ['24px', { lineHeight: '1.33' }],
      },
      borderRadius: {
        'DEFAULT': '10px',
        'lg': '10px',
        'xl': '10px',
        '2xl': '16px',
        'pill': '9999px',
      },
      boxShadow: {
        'none': 'none',
        'hairline': '0 0 0 1px rgba(0, 0, 0, 0.1)',
      },
    },
  },
  plugins: [],
}
