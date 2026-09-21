import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { SERVICE_WAKING_EVENT } from '../services/backendApi';
import { probeService, ServiceStatus, SERVER_WAKING_MESSAGE } from '../services/serviceStatus';

const POLL_MS = 4_000;
// Don't flash a banner for a backend that answers quickly.
const SHOW_AFTER_MS = 1_500;

/**
 * Checks the API once on load — which also wakes a sleeping host — and, while it
 * (or its database) is asleep, keeps checking until it's ready. `epoch` changes
 * when things come back so the app can remount and refetch what failed.
 * A failed API request also re-triggers the check (see SERVICE_WAKING_EVENT).
 */
export function useServiceStatus() {
  const [status, setStatus] = useState<ServiceStatus>({ state: 'checking', message: '' });
  const [slow, setSlow] = useState(false);
  const [epoch, setEpoch] = useState(0);

  const loopId = useRef(0);
  const active = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const wasDown = useRef(false);

  const start = useCallback((force: boolean) => {
    if (active.current && !force) return; // already polling — don't stack loops
    const id = ++loopId.current;           // a newer loop supersedes any older one
    clearTimeout(timer.current);
    active.current = true;

    const tick = async () => {
      const next = await probeService();
      if (id !== loopId.current) return;
      setStatus(next);
      if (next.state === 'ready') {
        active.current = false;
        if (wasDown.current) {
          wasDown.current = false;
          setEpoch((e) => e + 1);
        }
        return;
      }
      wasDown.current = true;
      timer.current = setTimeout(tick, POLL_MS);
    };
    tick();
  }, []);

  const stop = useCallback(() => {
    loopId.current++; // any loop in flight sees a newer id and drops its result
    active.current = false;
    clearTimeout(timer.current);
  }, []);

  useEffect(() => {
    start(true);
    const slowTimer = setTimeout(() => setSlow(true), SHOW_AFTER_MS);
    const onWaking = () => start(false);
    window.addEventListener(SERVICE_WAKING_EVENT, onWaking);
    return () => {
      stop();
      clearTimeout(slowTimer);
      window.removeEventListener(SERVICE_WAKING_EVENT, onWaking);
    };
  }, [start, stop]);

  return { status, slow, epoch };
}

export const ServiceStatusBanner: React.FC<{ status: ServiceStatus; slow: boolean }> = ({ status, slow }) => {
  const waking = status.state === 'server-waking' || status.state === 'database-waking';
  const stillChecking = status.state === 'checking' && slow;
  if (!waking && !stillChecking) return null;

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
