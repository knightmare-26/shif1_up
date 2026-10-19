import React from 'react';
import { motion, useReducedMotion } from 'framer-motion';

/** Same max width as the navbar so page content lines up with it. */
export const PageShell: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => (
  <div className={`mx-auto w-full max-w-[1600px] px-4 py-8 sm:px-6 lg:px-10 lg:py-12 ${className}`}>{children}</div>
);

/** One short fade for a whole section — no per-row staggering, honours reduced-motion. */
export const FadeIn: React.FC<{ children: React.ReactNode; className?: string; delay?: number }> = ({
  children,
  className,
  delay = 0,
}) => {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay }}
    >
      {children}
    </motion.div>
  );
};

export const PageHeader: React.FC<{
  title: string;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
}> = ({ title, subtitle, actions }) => (
  <header className="mb-8 flex flex-wrap items-end justify-between gap-6">
    <div className="min-w-0">
      {/* The section in white after a short red bar (the logo is in the bar above, so no brand here). */}
      <h1 className="display text-4xl uppercase text-white sm:text-5xl lg:text-6xl">
        <span aria-hidden="true" className="mr-[0.3em] inline-block h-[0.72em] w-[0.11em] bg-racing-red" />
        {title}
      </h1>
      {subtitle && <p className="mt-3 max-w-3xl text-base italic text-muted sm:text-lg">{subtitle}</p>}
    </div>
    {actions && <div className="flex flex-wrap items-end gap-3">{actions}</div>}
  </header>
);
