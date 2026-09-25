import React from 'react';

// The icon's red italic "1". Same shape as public/favicon.svg — both come from
// scripts/make_icons.py; change them together.
export const LOGO_ONE_POINTS = '39.04,13 49.04,13 40.96,51 30.96,51 36.49,25 28.03,29.5 29.73,21.5';
const RED = '#D62828';

/** The square icon: the red "1" and two speed streaks on carbon black (the browser-tab icon). */
export const LogoMark: React.FC<{ className?: string }> = ({ className = 'h-9 w-9' }) => (
  <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
    <rect width="64" height="64" rx="14" fill="#0A0A0A" />
    <rect x="5" y="27" width="20" height="4.5" rx="2.25" fill={RED} />
    <rect x="2" y="35.5" width="23" height="4.5" rx="2.25" fill={RED} opacity="0.6" />
    <polygon points={LOGO_ONE_POINTS} fill={RED} />
  </svg>
);

/** The wordmark: speed streaks, SHIF with a red 1, and a small UP. Sized by font-size (pass a
 *  text-* class); read out as "Shif1 UP". */
export const Wordmark: React.FC<{ className?: string }> = ({ className = 'text-2xl' }) => (
  <span className={`inline-flex items-center font-racing leading-none ${className}`}>
    <span className="sr-only">Shif1 UP</span>
    <span aria-hidden="true" className="inline-flex items-baseline">
      <span className="mr-[0.18em] flex flex-col items-end gap-[0.1em] self-center">
        <span className="block h-[0.09em] w-[0.55em] rounded-full bg-racing-red" />
        <span className="block h-[0.09em] w-[0.7em] rounded-full bg-racing-red opacity-60" />
      </span>
      <span className="text-white">SHIF</span>
      <span className="text-racing-red">1</span>
      <span className="ml-[0.3em] text-[0.45em] tracking-[0.3em] text-gray-400">UP</span>
    </span>
  </span>
);
