import React, { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

const GAP = 8;

/**
 * A small dark tooltip for extra detail on a badge or a number: on hover, on keyboard focus, and on
 * tap (touch screens have no hover). It's drawn over the page (a portal), so a scrolling table never
 * clips it, and kept inside the window: above the trigger, or below when there's no room. Closes on
 * Escape, a tap elsewhere, or scrolling.
 */
export const Tooltip: React.FC<{ content: React.ReactNode; children: React.ReactNode; label?: string }> = ({
  content, children, label,
}) => {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const tip = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!open || !trigger.current || !tip.current) return;
    const r = trigger.current.getBoundingClientRect();
    const t = tip.current.getBoundingClientRect();
    const left = Math.max(GAP, Math.min(r.left + r.width / 2 - t.width / 2, window.innerWidth - t.width - GAP));
    const above = r.top - t.height - GAP >= GAP;
    setPos({ left, top: above ? r.top - t.height - GAP : r.bottom + GAP });
  }, [open, content]);

  useEffect(() => {
    if (!open) return undefined;
    const close = () => setOpen(false);
    const onPointer = (e: PointerEvent) => {
      if (!trigger.current?.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    window.addEventListener('scroll', close, true);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('scroll', close, true);
    };
  }, [open]);

  useEffect(() => { if (!open) setPos(null); }, [open]);

  return (
    <>
      <button
        ref={trigger}
        type="button"
        aria-label={label}
        aria-describedby={open ? id : undefined}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen(true)}
        className="inline-flex cursor-help rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/60"
      >
        {children}
      </button>
      {open && createPortal(
        <div
          ref={tip}
          id={id}
          role="tooltip"
          style={{ position: 'fixed', left: pos?.left ?? -9999, top: pos?.top ?? -9999 }}
          className="pointer-events-none z-[70] w-max max-w-[min(20rem,calc(100vw-1rem))] rounded-lg border border-gray-700 bg-gray-950/95 px-3 py-2 text-left text-xs leading-relaxed text-gray-200 shadow-2xl backdrop-blur"
        >
          {content}
        </div>,
        document.body,
      )}
    </>
  );
};
