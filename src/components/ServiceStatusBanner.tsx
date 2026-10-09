import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { SERVICE_WAKING_EVENT } from '../services/backendApi';
import { probeService, ServiceStatus, SERVER_WAKING_MESSAGE } from '../services/serviceStatus';

const POLL_MS = 4_000;
// An awake server answers well within this (the whole check, database included, is ~1s), so a
// visit inside Render's 15-minute window loads directly; a sleeping one takes ~30-60s to boot.
export const GATE_AFTER_MS = 3_000;
// Only when the visitor chose to open the site anyway: a banner says it's still waking.
const BANNER_AFTER_MS = 8_000;

/**
 * Checks the API on load — which also wakes a sleeping host — and keeps checking
 * while it (or its database) is down.
 *
 *  - The pages mount straight away. An awake server answers within GATE_AFTER_MS and nothing
 *    else is shown.
 *  - `gated` puts the wake-up screen over them while the server is asleep (no answer, or the
 *    host's own page, after GATE_AFTER_MS) or just booting (opening its database connection),
 *    and at once while the **database** is down (a paused Supabase project being restored). It
 *    lifts by itself when everything is ready, or when the visitor chooses to continue anyway
 *    (then a slim banner, `slow`, says it's still waking).
 *  - A failed API request re-triggers the check (SERVICE_WAKING_EVENT) — a server that fell
 *    asleep while the tab sat idle gets the same screen; `epoch` changes when things come back
 *    after a failure so the routes remount and refetch.
 */
export function useServiceStatus() {
  const [status, setStatus] = useState<ServiceStatus>({ state: 'checking', message: '', detail: '', serverUp: false });
  const [slow, setSlow] = useState(false);
  const [graceOver, setGraceOver] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [since, setSince] = useState(() => Date.now());

  const loopId = useRef(0);
  const active = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const slowTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const graceTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const needsRemount = useRef(false);   // something failed while it was down: refetch on recovery

  const start = useCallback((force: boolean) => {
    if (active.current && !force) return; // already polling — don't stack loops
    const id = ++loopId.current;           // a newer loop supersedes any older one
    clearTimeout(timer.current);
    if (!active.current) {
      // A new outage (or the first check): the screen waits GATE_AFTER_MS for an answer — and
      // "ready" from the last check no longer holds while this one is out.
      setStatus({ state: 'checking', message: '', detail: '', serverUp: false });
      setSince(Date.now());
      setGraceOver(false);
      clearTimeout(graceTimer.current);
      graceTimer.current = setTimeout(() => setGraceOver(true), GATE_AFTER_MS);
      clearTimeout(slowTimer.current);
      slowTimer.current = setTimeout(() => setSlow(true), BANNER_AFTER_MS);
    }
    active.current = true;

    const tick = async () => {
      const next = await probeService();
      if (id !== loopId.current) return;
      setStatus(next);
      if (next.state === 'ready') {
        active.current = false;
        clearTimeout(slowTimer.current);
        clearTimeout(graceTimer.current);
        setSlow(false);
        setGraceOver(false);
        setDismissed(false);   // a later outage gets the screen again
        if (needsRemount.current) {
          needsRemount.current = false;
          setEpoch((e) => e + 1);
        }
        return;
      }
      needsRemount.current = true;   // the pages under the screen may have failed meanwhile
      timer.current = setTimeout(tick, POLL_MS);
    };
    tick();
  }, []);

  const stop = useCallback(() => {
    loopId.current++; // any loop in flight sees a newer id and drops its result
    active.current = false;
    clearTimeout(timer.current);
    clearTimeout(slowTimer.current);
    clearTimeout(graceTimer.current);
  }, []);

  useEffect(() => {
    start(true);
    const onWaking = () => {
      needsRemount.current = true;
      start(false);
    };
    window.addEventListener(SERVICE_WAKING_EVENT, onWaking);
    return () => {
      stop();
      window.removeEventListener(SERVICE_WAKING_EVENT, onWaking);
    };
  }, [start, stop]);

  // The database being down is a definite answer: at once. A server that hasn't answered (or
  // whose host is still showing its own page) only after the grace period.
  const waking = status.state === 'database-waking'
    || ((status.state === 'server-waking' || status.state === 'checking') && graceOver);
  const gated = waking && !dismissed;

  // Seconds since the wait began (the grace period included).
  useEffect(() => {
    if (!gated) return;
    setElapsed(Math.floor((Date.now() - since) / 1000));
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - since) / 1000)), 1000);
    return () => clearInterval(id);
  }, [gated, since]);

  const retry = useCallback(() => start(true), [start]);
  const dismiss = useCallback(() => setDismissed(true), []);

  return { status, slow, epoch, gated, elapsed, retry, dismiss };
}

/** Slim, non-blocking notice once the visitor chose to open the site anyway: the server is still starting,
 *  or the database is down. */
export const ServiceStatusBanner: React.FC<{ status: ServiceStatus; slow: boolean }> = ({ status, slow }) => {
  // The database being down always shows (the visitor chose to continue past the wait screen);
  // a server that's still starting only once it's taking a while.
  const databaseDown = status.state === 'database-waking';
  if (status.state === 'ready' || (!databaseDown && !slow)) return null;
  const waking = databaseDown || status.state === 'server-waking';

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-3 border-b border-yellow-500/30 bg-yellow-500/10 px-4 py-2.5 text-center text-sm text-yellow-200"
    >
      <RefreshCw className="h-4 w-4 flex-shrink-0 animate-spin" aria-hidden="true" />
      <span>
        {waking ? status.message : SERVER_WAKING_MESSAGE}{' '}
        <span className="text-yellow-200/70">This page refreshes by itself when it's ready.</span>
      </span>
    </div>
  );
};
