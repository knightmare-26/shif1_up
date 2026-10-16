/** @type {import('tailwindcss').Config} */
// The look: pure black, white type, one red; a DIN-style grotesk (Barlow) set big and tight for
// display, small and tracked-out in uppercase for labels; square corners and thin rules.
const DISPLAY = ['Barlow', 'ui-sans-serif', 'system-ui', 'sans-serif'];

module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'racing-red': '#E42320',
        'carbon-black': '#000000',
        'track-grey': '#F7F7F7',
        // Old accents, folded into the palette: one accent colour (red), the rest white and grey.
        'turbo-teal': '#FFFFFF',
        'pit-stop-yellow': '#808080',
        'pure-white': '#FFFFFF',
        // Surfaces and rules on black.
        'ink': {
          900: '#0B0B0B',
          800: '#131313',
          700: '#1C1C1C',
          600: '#262626',
          500: '#3A3A3A',
        },
        'muted': '#808080',
      },
      fontFamily: {
        sans: DISPLAY,
        display: DISPLAY,
        // Earlier names, kept so older markup picks up the new face.
        'f1': DISPLAY,
        'racing': DISPLAY,
      },
      // Square, like the rest of the look; `rounded-full` (dots, avatars) stays round.
      borderRadius: {
        none: '0',
        sm: '1px',
        DEFAULT: '2px',
        md: '2px',
        lg: '2px',
        xl: '2px',
        '2xl': '3px',
        '3xl': '4px',
      },
      letterSpacing: {
        display: '-0.035em',
        label: '0.12em',
      },
      animation: {
        'race-start': 'raceStart 0.5s ease-out',
        'checkered-flag': 'checkeredFlag 2s linear infinite',
        'pit-stop': 'pitStop 1s ease-in-out',
        'lap-time': 'lapTime 0.3s ease-out',
        'caret': 'caret 1s steps(1) infinite',
      },
      keyframes: {
        raceStart: {
          '0%': { transform: 'scale(0.8)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        checkeredFlag: {
          '0%': { backgroundPosition: '0% 0%' },
          '100%': { backgroundPosition: '100% 100%' },
        },
        pitStop: {
          '0%, 100%': { transform: 'translateX(0)' },
          '50%': { transform: 'translateX(10px)' },
        },
        lapTime: {
          '0%': { transform: 'translateY(-20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        caret: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
      },
      backgroundImage: {
        'checkered-pattern': 'repeating-conic-gradient(#000 0deg 90deg, #fff 90deg 180deg)',
        'race-track': 'linear-gradient(90deg, #2a2a2a 0%, #4a4a4a 50%, #2a2a2a 100%)',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}
