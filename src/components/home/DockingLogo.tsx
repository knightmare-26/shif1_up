import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, useMotionValue, useMotionValueEvent, useReducedMotion, useScroll } from 'framer-motion';
import { Wordmark } from '../ui';

/** The navigation bar's logo; the home page measures it to know where to dock. */
export const NAV_LOGO_ID = 'nav-logo';

interface Geometry { top: number; left: number; width: number; navTop: number; navLeft: number; navWidth: number }

/**
 * The home page's logo: big above the hero's headline, and as the page scrolls it rides up with
 * the hero, shrinking and sliding over until it docks in the navigation bar's corner (whose own
 * logo stays hidden on the home page); scrolling back brings it down again. It's drawn once, fixed
 * over the page (in a portal, so no transformed ancestor can move it), over a hidden copy that
 * holds its place in the hero. With reduced motion it's just a logo in the hero and the bar keeps
 * its own.
 */
export const DockingLogo: React.FC<{ className: string }> = ({ className }) => {
  const reduce = useReducedMotion();
  const slot = useRef<HTMLSpanElement>(null);
  const geometry = useRef<Geometry | null>(null);
  const [ready, setReady] = useState(false);
  const { scrollY } = useScroll();
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const scale = useMotionValue(1);

  const place = useCallback((scroll: number) => {
    const g = geometry.current;
    if (!g) return;
    // Up with the page until level with the bar's logo, then it stays there; it shrinks and slides
    // over on the way, arriving exactly as it gets there.
    const travel = Math.max(g.top - g.navTop, 1);
    const p = Math.min(Math.max(scroll / travel, 0), 1);
    x.set(g.left + (g.navLeft - g.left) * p);
    y.set(Math.max(g.top - scroll, g.navTop));
    scale.set(1 + (g.navWidth / g.width - 1) * p);
  }, [x, y, scale]);

  const measure = useCallback(() => {
    const hero = slot.current?.getBoundingClientRect();
    const nav = document.getElementById(NAV_LOGO_ID)?.getBoundingClientRect();
    if (!hero || !nav || !hero.width || !nav.width) return;
    geometry.current = {
      top: hero.top + window.scrollY, left: hero.left, width: hero.width,
      navTop: nav.top, navLeft: nav.left, navWidth: nav.width,
    };
    place(window.scrollY);
    setReady(true);
  }, [place]);

  useLayoutEffect(() => { if (!reduce) measure(); }, [reduce, measure]);
  useEffect(() => {
    if (reduce) return undefined;
    // Sizes change with the window and once the logo's font has loaded.
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    observer?.observe(document.body);
    window.addEventListener('resize', measure);
    document.fonts?.ready.then(measure).catch(() => undefined);
    return () => { observer?.disconnect(); window.removeEventListener('resize', measure); };
  }, [reduce, measure]);
  useMotionValueEvent(scrollY, 'change', place);

  if (reduce) return <Wordmark className={className} />;
  return (
    <>
      <span ref={slot} className="invisible inline-flex"><Wordmark className={className} /></span>
      {createPortal(
        <motion.div aria-hidden="true" className="pointer-events-none fixed left-0 top-0 z-[55]"
          style={{ x, y, scale, transformOrigin: '0 0', opacity: ready ? 1 : 0 }}>
          <Wordmark className={className} />
        </motion.div>,
        document.body,
      )}
    </>
  );
};
