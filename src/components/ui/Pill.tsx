import React from 'react';

const TONES = {
  good: 'bg-green-500/15 text-green-400',
  warn: 'bg-yellow-500/15 text-yellow-400',
  bad: 'bg-red-500/15 text-red-400',
  neutral: 'bg-gray-800 text-gray-400',
};

/** Small status label (model readiness, counts, ...). Colour is never the only signal — keep the text meaningful. */
export const Pill: React.FC<{ tone?: keyof typeof TONES; children: React.ReactNode }> = ({
  tone = 'neutral',
  children,
}) => <span className={`rounded px-2 py-1 text-xs ${TONES[tone]}`}>{children}</span>;
