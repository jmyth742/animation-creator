/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        pixel: ['"Press Start 2P"', 'monospace'],
        retro: ['"VT323"', 'monospace'],
        mono: ['"VT323"', 'monospace'],
      },
      colors: {
        // Remap zinc to a dark navy/indigo game palette
        zinc: {
          950: '#06060f',
          900: '#0c0c1e',
          800: '#121228',
          700: '#1c1c38',
          600: '#2a2a50',
          500: '#44446a',
          400: '#7070a8',
          300: '#9898c8',
          200: '#c0c0e0',
          100: '#e8e8f8',
        },
        // Accent = vivid purple (primary CTA)
        accent: {
          50:  '#f3e8ff',
          100: '#e9d5ff',
          200: '#d8b4fe',
          300: '#c084fc',
          400: '#a855f7',
          500: '#9333ea',
          600: '#7c3aed',
          700: '#6d28d9',
          800: '#5b21b6',
          900: '#3b0764',
          950: '#1a0333',
        },
        // Pixel-game utility colors
        px: {
          green:  '#4ade80',
          yellow: '#fbbf24',
          red:    '#f87171',
          cyan:   '#22d3ee',
          orange: '#fb923c',
        },
      },
      boxShadow: {
        pixel:        '4px 4px 0 0 #000000',
        'pixel-sm':   '2px 2px 0 0 #000000',
        'pixel-lg':   '6px 6px 0 0 #000000',
        'pixel-accent': '4px 4px 0 0 #6d28d9',
        'pixel-green':  '4px 4px 0 0 #166534',
        'pixel-inset':  'inset -2px -2px 0 0 rgba(0,0,0,0.6), inset 2px 2px 0 0 rgba(255,255,255,0.08)',
      },
      animation: {
        blink: 'blink 1s step-end infinite',
        'pixel-pulse': 'pixelPulse 2s ease-in-out infinite',
        march: 'march 0.6s steps(4) infinite',
      },
      keyframes: {
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0' },
        },
        pixelPulse: {
          '0%, 100%': { boxShadow: '4px 4px 0 0 #6d28d9' },
          '50%':      { boxShadow: '4px 4px 0 0 #a855f7, 0 0 16px rgba(168,85,247,0.4)' },
        },
      },
    },
  },
  plugins: [],
}
