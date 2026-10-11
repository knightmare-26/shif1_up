import { useEffect, useRef, useState } from 'react';
import { backendApi } from '../services/backendApi';

/**
 * A counter that goes up whenever the server's data moved while the page was open, so a page can
 * fetch again by itself instead of waiting for a reload.
 *
 * The server retrains whenever new results land (a session stored by data upkeep — often right
 * after a sleeping server wakes — or a correction from the results refresh), and /predict/status
 * says when (`trained_at`). One check is shared by every component that asks: once a minute while
 * the page is visible, and straight away when it's shown again. A change forgets the tab's cached
 * answers, so the refetch is fresh.
 */
export const DATA_CHECK_MS = 60_000;

let version = 0;
let lastTrainedAt: string | null | undefined;          // undefined: not asked yet
const listeners = new Set<(v: number) => void>();
let timer: ReturnType<typeof setInterval> | null = null;

/** `first`: what the page loaded with — taken even in a background tab, or a change made before
 * it's first looked at would become the starting point and never be shown. */
async function check(first = false): Promise<void> {
  if (!first && document.visibilityState === 'hidden') return;
  try {
    const status = await backendApi.getPredictionStatus(true);
    const trainedAt: string | null = status?.trained_at ?? null;
    // Untrained -> trained counts too: a minute's check can miss a short-lived value in between.
    if (lastTrainedAt !== undefined && trainedAt && trainedAt !== lastTrainedAt) {
      backendApi.forgetCachedData();
      version += 1;
      listeners.forEach((listener) => listener(version));
    }
    lastTrainedAt = trainedAt ?? lastTrainedAt ?? null;
  } catch {
    // The server waking up: the next check will tell.
  }
}

const onShown = () => { if (document.visibilityState === 'visible') check(); };

function subscribe(listener: (v: number) => void): () => void {
  listeners.add(listener);
  if (listeners.size === 1) {
    check(true);
    timer = setInterval(() => check(), DATA_CHECK_MS);
    document.addEventListener('visibilitychange', onShown);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      if (timer) clearInterval(timer);
      timer = null;
      document.removeEventListener('visibilitychange', onShown);
    }
  };
}

export function useDataVersion(): number {
  const [current, setCurrent] = useState(version);
  useEffect(() => subscribe(setCurrent), []);
  return current;
}

/** Runs `refresh` when the data moved — not on mount, where the page does its first load itself. */
export function useOnDataChange(refresh: () => void): void {
  const dataVersion = useDataVersion();
  const seen = useRef(dataVersion);
  const latest = useRef(refresh);
  latest.current = refresh;
  useEffect(() => {
    if (seen.current === dataVersion) return;
    seen.current = dataVersion;
    latest.current();
  }, [dataVersion]);
}

/** For tests: start from scratch. */
export function resetDataVersionForTests(): void {
  version = 0;
  lastTrainedAt = undefined;
  listeners.clear();
  if (timer) clearInterval(timer);
  timer = null;
}
