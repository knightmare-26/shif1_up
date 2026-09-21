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
}

export const SERVER_WAKING_MESSAGE =
  'Waking up the server — the first visit after a quiet period can take up to a minute.';
const DATABASE_WAKING_MESSAGE =
  'Waking up the database — this can take 1–2 minutes if it was paused.';

const PROBE_TIMEOUT_MS = 10_000;

/** One look at /health. Never throws. */
export async function probeService(): Promise<ServiceStatus> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE_URL}/health`, { signal: controller.signal });
    if (!res.ok) return { state: 'server-waking', message: SERVER_WAKING_MESSAGE };

    const body = await res.json().catch(() => null);
    // `checks.database` only exists when the API runs against Supabase; its
    // `state` is "ready" once connected. An older backend without it is treated as ready.
    const database = body?.checks?.database;
    if (database && database.state !== 'ready') {
      return { state: 'database-waking', message: DATABASE_WAKING_MESSAGE };
    }
    return { state: 'ready', message: '' };
  } catch {
    return { state: 'server-waking', message: SERVER_WAKING_MESSAGE };
  } finally {
    clearTimeout(timer);
  }
}
