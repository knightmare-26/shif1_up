import React from 'react';
import { motion, useReducedMotion } from 'framer-motion';

/** Same max width as the navbar so page content lines up with it. */
export const PageShell: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => (
  <div className={`mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8 ${className}`}>{children}</div>
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
  <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
    <div className="min-w-0">
      <h1 className="font-racing text-3xl leading-tight text-racing-red">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-gray-400">{subtitle}</p>}
    </div>
    {actions && <div className="flex flex-wrap items-end gap-3">{actions}</div>}
  </header>
);
