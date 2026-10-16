import React, { useRef } from 'react';
import { motion, MotionValue, useReducedMotion, useScroll, useTransform } from 'framer-motion';

const Word: React.FC<{ progress: MotionValue<number>; range: [number, number]; red: boolean; still: boolean; children: string }> = ({
  progress, range, red, still, children,
}) => {
  const opacity = useTransform(progress, range, [0.12, 1]);
  return (
    <motion.span style={{ opacity: still ? 1 : opacity }}
      className={`mr-[0.2em] inline-block ${red ? 'text-racing-red' : 'text-white'}`}>
      {children}
    </motion.span>
  );
};

/**
 * A statement in giant type whose words light up one after another as it scrolls through the
 * window. Screen readers get the sentence once; with reduced motion every word is lit.
 */
export const ScrollStatement: React.FC<{ text: string; highlight?: string[] }> = ({ text, highlight = [] }) => {
  const ref = useRef<HTMLElement>(null);
  const still = !!useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start 0.8', 'end 0.45'] });
  const words = text.split(' ');

  return (
    <section ref={ref} className="mx-auto max-w-[1600px] px-4 py-28 sm:px-6 lg:px-10 lg:py-40">
      <h2 className="sr-only">{text}</h2>
      <p aria-hidden="true" className="display text-[clamp(2.6rem,8vw,8.5rem)] uppercase">
        {words.map((word, i) => (
          <Word key={`${word}-${i}`} progress={scrollYProgress} range={[i / words.length, (i + 1) / words.length]}
            red={highlight.includes(word.replace(/[^\w]/g, ''))} still={still}>
            {word}
          </Word>
        ))}
      </p>
    </section>
  );
};
