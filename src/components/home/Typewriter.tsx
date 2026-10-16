import React, { useEffect, useState } from 'react';
import { useReducedMotion } from 'framer-motion';

/**
 * Types each phrase, holds it, deletes it and moves on, with a blinking caret. Decorative: the
 * caller gives the heading its accessible text. With reduced motion it shows the first phrase.
 */
export const Typewriter: React.FC<{ phrases: string[]; className?: string }> = ({ phrases, className = '' }) => {
  const reduce = useReducedMotion();
  const [index, setIndex] = useState(0);
  const [shown, setShown] = useState(0);
  const [deleting, setDeleting] = useState(false);
  const phrase = phrases[index % phrases.length] ?? '';

  useEffect(() => {
    if (reduce) return undefined;
    let delay = deleting ? 35 : 70;
    let next = () => setShown((n) => n + (deleting ? -1 : 1));
    if (!deleting && shown >= phrase.length) {
      delay = 2200;                                      // hold the whole phrase
      next = () => setDeleting(true);
    } else if (deleting && shown <= 0) {
      delay = 350;
      next = () => { setDeleting(false); setIndex((i) => i + 1); };
    }
    const timer = setTimeout(next, delay);
    return () => clearTimeout(timer);
  }, [shown, deleting, phrase, reduce]);

  return (
    <span aria-hidden="true" className={className}>
      {reduce ? phrases[0] : phrase.slice(0, shown)}
      <span className="ml-[0.08em] inline-block h-[0.82em] w-[0.05em] translate-y-[0.06em] bg-white/80 motion-safe:animate-caret" />
    </span>
  );
};
