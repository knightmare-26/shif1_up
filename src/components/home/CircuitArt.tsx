import React, { useId } from 'react';
import { useReducedMotion } from 'framer-motion';

// A made-up circuit: long straights, a hairpin, a fast sweep and a chicane.
const TRACK =
  'M 90 300 C 90 248 124 226 172 226 L 300 226 C 344 226 356 194 334 162 L 304 116 C 288 90 304 62 336 62 ' +
  'L 476 62 C 526 62 546 94 534 134 L 518 190 C 508 230 532 250 562 260 C 594 272 592 334 552 342 ' +
  'L 146 354 C 108 356 90 330 90 300 Z';

/** Line drawing of a circuit, with a red car lapping it (still with reduced motion). Decorative. */
export const CircuitArt: React.FC<{ className?: string; lapSeconds?: number }> = ({ className = '', lapSeconds = 11 }) => {
  const reduce = useReducedMotion();
  const id = `track-${useId().replace(/[^\w-]/g, '')}`;     // each drawing's own path to lap
  return (
    <svg viewBox="40 30 600 360" className={className} fill="none" aria-hidden="true">
      <path d={TRACK} stroke="currentColor" strokeWidth="14" strokeLinejoin="round" opacity="0.12" />
      <path id={id} d={TRACK} stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" opacity="0.55" />
      {/* start / finish line */}
      <path d="M 236 214 L 236 238" stroke="#E42320" strokeWidth="3" />
      {!reduce && (
        <circle r="5.5" fill="#E42320">
          <animateMotion dur={`${lapSeconds}s`} repeatCount="indefinite" rotate="auto">
            <mpath href={`#${id}`} />
          </animateMotion>
        </circle>
      )}
    </svg>
  );
};
