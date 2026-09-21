import { API_BASE_URL } from './backendApi';

/**
 * What the visitor should be told about the backend.
 *  - server-waking:   the API host isn't answering yet (a free Render instance boots on the first request)
 *  - database-waking: the API is up but its database is asleep or reconnecting (a paused Supabase project)
 */
export type ServiceState = 'checking' | 'ready' | 'server-waking' | 'database-waking';

export interface ServiceStatus {
  state: ServiceState;
  message: string;
  /** Plain-language result of the last check — shown so a stuck wait can be diagnosed at a glance. */
  detail: string;
  /** True once our own API has answered (as opposed to the host's error page or nothing at all). */
  serverUp: boolean;
}

export const SERVER_WAKING_MESSAGE =
  'Waking up the server — the first visit after a quiet period can take up to a minute.';
export const DATABASE_WAKING_MESSAGE =
  'Waking up the database — it was paused after a period of inactivity, and restoring it takes a few minutes.';
// The server has nothing to wake it with, so waiting won't help until someone resumes it by hand.
export const DATABASE_OFFLINE_MESSAGE =
  "The database is offline, and this server can't restart it on its own. It has to be resumed from the Supabase dashboard.";

// A cold, CPU-throttled free instance can be slow to answer its first request.
const PROBE_TIMEOUT_MS = 20_000;

const serverWaking = (detail: string): ServiceStatus => ({
  state: 'server-waking', message: SERVER_WAKING_MESSAGE, detail, serverUp: false,
});

/** One look at /health. Never throws. */
export async function probeService(): Promise<ServiceStatus> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE_URL}/health`, { signal: controller.signal, cache: 'no-store' });
    const body = await res.json().catch(() => null);

    // Our API answers with { checks: ... } (FastAPI wraps an error response's payload in { detail }).
    const report = body?.checks ? body : body?.detail?.checks ? body.detail : null;
    if (!report) {
      // Something answered, but it isn't our API: the host's own page while the service starts (or is suspended).
      return serverWaking(`The API host answered HTTP ${res.status} instead of the API`);
    }

    // `checks.database` only exists when the API runs against Supabase; its `state`
    // is "ready" once connected. An older backend without it is treated as ready.
    const database = report.checks?.database;
    if (database && database.state !== 'ready') {
      const parts = [`The API is up; its database is ${database.state}`];
      if (database.project_status) parts.push(`Supabase reports the project as ${database.project_status}`);
      const cannotRestore = database.can_restore === false;
      if (cannotRestore) parts.push('no Supabase access token is configured on the server');
      return {
        state: 'database-waking',
        // "unavailable" with nothing able to restore it is not a wake-up in progress.
        message: cannotRestore && database.state === 'unavailable' ? DATABASE_OFFLINE_MESSAGE : DATABASE_WAKING_MESSAGE,
        detail: parts.join(' · '),
        serverUp: true,
      };
    }
    return { state: 'ready', message: '', detail: '', serverUp: true };
  } catch (err) {
    console.warn('[service] health check failed:', err);
    const timedOut = err instanceof DOMException && err.name === 'AbortError';
    return serverWaking(
      timedOut
        ? `No answer within ${PROBE_TIMEOUT_MS / 1000}s`
        : "The browser couldn't reach the API (it may still be starting, blocked by CORS, or down)",
    );
  } finally {
    clearTimeout(timer);
  }
}
