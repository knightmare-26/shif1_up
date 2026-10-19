import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { Menu, X } from 'lucide-react';
import { Wordmark } from './ui';
import { NAV_LOGO_ID } from './home/DockingLogo';
import { useLiveTiming } from '../config/features';

type NavItem = { path: string; label: string };

const NAV_ITEMS: NavItem[] = [
  { path: '/',             label: 'Home' },
  { path: '/dashboard',    label: 'Dashboard' },
  { path: '/predictions',  label: 'Predictions' },
  { path: '/live',         label: 'Live' },
  { path: '/data-manager', label: 'Data Manager' },
];

// Nested routes (e.g. /live-monitor under Live) keep their section highlighted.
const isActive = (path: string, pathname: string) => (path === '/' ? pathname === '/' : pathname.startsWith(path));

// A computer: the menu rolls out inside the bar instead of opening the side panel.
const DESKTOP = '(min-width: 1024px)';
const ROLLED_OUT_KEY = 'shif1:menu-rolled-out';

function useDesktop(): boolean {
  const [desktop, setDesktop] = useState(() => !!window.matchMedia?.(DESKTOP).matches);
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const query = window.matchMedia(DESKTOP);
    const onChange = () => setDesktop(query.matches);
    onChange();
    query.addEventListener?.('change', onChange);
    return () => query.removeEventListener?.('change', onChange);
  }, []);
  return desktop;
}

// The rolled-out menu stays out until the button is pressed again, across pages and reloads
// (kept in this browser only; it's a convenience, so storage failing just means it starts closed).
function readRolledOut(): boolean {
  try { return window.localStorage.getItem(ROLLED_OUT_KEY) === '1'; } catch { return false; }
}
function saveRolledOut(value: boolean) {
  try { window.localStorage.setItem(ROLLED_OUT_KEY, value ? '1' : '0'); } catch { /* not kept */ }
}

const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * A slim bar — the Shif1 UP logo on the left (on the home page it's hidden: the hero's logo docks
 * into its place as the page scrolls, see DockingLogo), the menu button on the right.
 * On a computer the button rolls the sections out to its left, inside the bar, and they stay out —
 * across pages — until it's pressed again. On a phone or tablet it opens a full-height panel that
 * slides in from the right with the sections in big type (the current one in red); that closes on
 * Escape, a click outside, or moving to another page, and focus goes into it and back to the button.
 */
const Navigation: React.FC = () => {
  const { pathname, search } = useLocation();
  const [open, setOpen] = useState(false);
  const desktop = useDesktop();
  const [rolledOut, setRolledOut] = useState(readRolledOut);
  const reduce = useReducedMotion();
  const panel = useRef<HTMLElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  // Live timing is on hold unless the API has a feed (or a replay) running: say so in the menu.
  const { enabled: liveOn, loading: liveLoading } = useLiveTiming();
  const current = NAV_ITEMS.find((item) => item.path !== '/' && isActive(item.path, pathname));
  const docking = pathname === '/' && !reduce;

  useEffect(() => { setOpen(false); }, [pathname, search]);
  useEffect(() => { if (desktop) setOpen(false); }, [desktop]);   // widened past the panel's sizes
  const showLinks = desktop && rolledOut;
  const onMenuButton = () => {
    if (!desktop) { setOpen(true); return; }
    setRolledOut((v) => { saveRolledOut(!v); return !v; });
  };

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        toggle.current?.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';                 // the page doesn't scroll under the menu
    panel.current?.querySelector<HTMLElement>('a')?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
    };
  }, [open]);

  return (
    <>
      <header className="fixed inset-x-0 top-0 z-50 h-16 border-b border-white/5 bg-black/75 backdrop-blur-md">
        <div className="mx-auto flex h-full max-w-[1600px] items-center justify-between px-4 sm:px-6 lg:px-10">
          <Link to="/" aria-label="Shif1 UP home"
            className="focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/70">
            <span id={NAV_LOGO_ID} className={`inline-flex ${docking ? 'invisible' : ''}`}>
              <Wordmark className="text-[1.65rem] sm:text-[2rem]" />
            </span>
          </Link>

          <div className="flex items-center gap-5">
            <AnimatePresence initial={false}>
              {showLinks && (
                <motion.nav
                  key="links"
                  id="site-links"
                  aria-label="Site"
                  className="overflow-hidden"
                  // Rolls out leftwards from the button: revealed right to left, and back in on close.
                  initial={reduce ? { opacity: 0 } : { clipPath: 'inset(0 0 0 100%)' }}
                  animate={reduce ? { opacity: 1 } : { clipPath: 'inset(0 0 0 0%)' }}
                  exit={reduce ? { opacity: 0 } : { clipPath: 'inset(0 0 0 100%)' }}
                  transition={{ duration: reduce ? 0 : 0.5, ease: EASE }}
                >
                  <ul className="flex items-center gap-8 pr-2">
                    {NAV_ITEMS.map((item, i) => {
                      const active = isActive(item.path, pathname);
                      return (
                        <motion.li
                          key={item.path}
                          initial={reduce ? false : { opacity: 0, x: 18 }}
                          animate={{ opacity: 1, x: 0 }}
                          // The one nearest the button first, so it reads as unrolling to the left.
                          transition={{ duration: 0.35, ease: EASE, delay: reduce ? 0 : 0.05 + (NAV_ITEMS.length - 1 - i) * 0.05 }}
                        >
                          <NavLink
                            to={item.path}
                            aria-current={active ? 'page' : undefined}
                            className={`group relative inline-flex items-baseline gap-1.5 py-1 text-[13px] font-medium uppercase tracking-label transition-colors focus:outline-none focus-visible:text-racing-red ${
                              active ? 'text-racing-red' : 'text-white hover:text-racing-red'}`}
                          >
                            {item.label}
                            {item.path === '/live' && !liveOn && !liveLoading && (
                              <span className="text-[10px] text-muted group-hover:text-white">Soon</span>
                            )}
                            <span aria-hidden="true"
                              className={`absolute inset-x-0 -bottom-0.5 h-px origin-left bg-racing-red transition-transform duration-300 ${
                                active ? 'scale-x-100' : 'scale-x-0 group-hover:scale-x-100'}`} />
                          </NavLink>
                        </motion.li>
                      );
                    })}
                  </ul>
                </motion.nav>
              )}
            </AnimatePresence>
            {current && !showLinks && <span className="label hidden text-muted sm:inline">{current.label}</span>}
            <button
              ref={toggle}
              type="button"
              onClick={onMenuButton}
              aria-label={showLinks ? 'Close menu' : 'Open menu'}
              aria-expanded={desktop ? rolledOut : open}
              aria-controls={desktop ? 'site-links' : 'site-menu'}
              className="p-1.5 text-white transition-colors hover:text-racing-red focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/70"
            >
              <AnimatePresence mode="wait" initial={false}>
                <motion.span
                  key={showLinks ? 'close' : 'open'}
                  className="block"
                  initial={reduce ? false : { rotate: -90, opacity: 0 }}
                  animate={{ rotate: 0, opacity: 1 }}
                  exit={reduce ? { opacity: 0 } : { rotate: 90, opacity: 0 }}
                  transition={{ duration: reduce ? 0 : 0.18 }}
                >
                  {showLinks ? <X className="h-7 w-7" strokeWidth={2.5} /> : <Menu className="h-7 w-7" strokeWidth={2.5} />}
                </motion.span>
              </AnimatePresence>
            </button>
          </div>
        </div>
      </header>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              key="backdrop"
              className="fixed inset-0 z-[60] bg-black/60"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ duration: reduce ? 0 : 0.25 }}
              onClick={() => setOpen(false)}
              aria-hidden="true"
            />
            <motion.nav
              key="panel"
              ref={panel}
              id="site-menu"
              aria-label="Site"
              className="fixed inset-y-0 right-0 z-[61] flex w-full max-w-md flex-col bg-[#141414] px-10 pb-10 pt-6 sm:px-14"
              initial={reduce ? { opacity: 0 } : { x: '100%' }}
              animate={reduce ? { opacity: 1 } : { x: 0 }}
              exit={reduce ? { opacity: 0 } : { x: '100%' }}
              transition={{ duration: reduce ? 0 : 0.35, ease: [0.22, 1, 0.36, 1] }}
            >
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => { setOpen(false); toggle.current?.focus(); }}
                  aria-label="Close menu"
                  className="p-1.5 text-white transition-colors hover:text-racing-red focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/70"
                >
                  <X className="h-7 w-7" strokeWidth={2.5} />
                </button>
              </div>

              <ul className="mt-12 space-y-6">
                {NAV_ITEMS.map((item, i) => {
                  const active = isActive(item.path, pathname);
                  return (
                    <motion.li
                      key={item.path}
                      initial={reduce ? false : { opacity: 0, x: 24 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.3, delay: reduce ? 0 : 0.08 + i * 0.04 }}
                    >
                      <NavLink
                        to={item.path}
                        aria-current={active ? 'page' : undefined}
                        className={`group inline-flex items-baseline gap-3 font-display text-3xl font-medium uppercase tracking-tight transition-colors focus:outline-none focus-visible:text-racing-red sm:text-4xl ${
                          active ? 'text-racing-red' : 'text-white hover:text-racing-red'}`}
                      >
                        {item.label}
                        {item.path === '/live' && !liveOn && !liveLoading && (
                          <span className="label text-muted group-hover:text-white">Soon</span>
                        )}
                      </NavLink>
                    </motion.li>
                  );
                })}
              </ul>

              <div className="mt-auto border-t border-white/10 pt-6">
                <p className="label text-muted">Standings · Results · Predictions</p>
                <p className="mt-2 text-sm italic text-muted">Data: FastF1, Jolpica and OpenF1.</p>
              </div>
            </motion.nav>
          </>
        )}
      </AnimatePresence>
    </>
  );
};

export default Navigation;
