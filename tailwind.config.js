/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'racing-red': '#D62828',
        'carbon-black': '#0A0A0A',
        'track-grey': '#F7F7F7',
        'turbo-teal': '#005F73',
        'pit-stop-yellow': '#FFBA08',
        'pure-white': '#FFFFFF',
      },
      fontFamily: {
        'f1': ['Orbitron', 'monospace'],
        'racing': ['Racing Sans One', 'cursive'],
      },
      animation: {
        'race-start': 'raceStart 0.5s ease-out',
        'checkered-flag': 'checkeredFlag 2s linear infinite',
        'pit-stop': 'pitStop 1s ease-in-out',
        'lap-time': 'lapTime 0.3s ease-out',
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
