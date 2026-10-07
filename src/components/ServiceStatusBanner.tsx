import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { SERVICE_WAKING_EVENT } from '../services/backendApi';
import { probeService, ServiceStatus, SERVER_WAKING_MESSAGE } from '../services/serviceStatus';

const POLL_MS = 4_000;
// A cold start that's over within this shows nothing at all — the pages just load.
const BANNER_AFTER_MS = 8_000;

/**
 * Checks the API on load — which also wakes a sleeping host — and keeps checking
 * while it (or its database) is down.
 *
 *  - The pages render straight away: a sleeping host holds their requests while it boots,
 *    so a cold start only means a slower first load, and after a few seconds a slim
 *    banner (`slow`) says why.
 *  - `gated` is true only while the **database** is down (a paused Supabase project being
 *    restored): the app shows a wait screen instead of pages that would only fail, until
 *    it's back or the visitor chooses to continue anyway.
 *  - A failed API request re-triggers the check (SERVICE_WAKING_EVENT); `epoch` changes
 *    when things come back after a failure so the routes remount and refetch.
 */
export function useServiceStatus() {
  const [status, setStatus] = useState<ServiceStatus>({ state: 'checking', message: '', detail: '', serverUp: false });
  const [slow, setSlow] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  const loopId = useRef(0);
  const active = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const slowTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const needsRemount = useRef(false);   // something failed while it was down: refetch on recovery

  const start = useCallback((force: boolean) => {
    if (active.current && !force) return; // already polling — don't stack loops
    const id = ++loopId.current;           // a newer loop supersedes any older one
    clearTimeout(timer.current);
    if (!active.current) {
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
        setSlow(false);
        setDismissed(false);   // a later database outage gets the wait screen again
        if (needsRemount.current) {
          needsRemount.current = false;
          setEpoch((e) => e + 1);
        }
        return;
      }
      if (next.state === 'database-waking') needsRemount.current = true;
      timer.current = setTimeout(tick, POLL_MS);
    };
    tick();
  }, []);

  const stop = useCallback(() => {
    loopId.current++; // any loop in flight sees a newer id and drops its result
    active.current = false;
    clearTimeout(timer.current);
    clearTimeout(slowTimer.current);
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

  const gated = status.state === 'database-waking' && !dismissed;

  // Seconds spent on the wait screen.
  useEffect(() => {
    if (!gated) return;
    const t0 = Date.now();
    setElapsed(0);
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(id);
  }, [gated]);

  const retry = useCallback(() => start(true), [start]);
  const dismiss = useCallback(() => setDismissed(true), []);

  return { status, slow, epoch, gated, elapsed, retry, dismiss };
}

/** Slim, non-blocking notice: the server is still starting, or the database is down and the visitor continued anyway. */
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
