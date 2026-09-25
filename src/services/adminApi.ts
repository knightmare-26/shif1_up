/**
 * Admin API — calls the backend's admin-guarded endpoints. Requires an
 * admin JWT (Authorization: Bearer <token>), same pattern as authApi.ts.
 */

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export interface IngestStatus {
  running: boolean;
  message: string;
  races_done: number;
  races_total: number;
  error: string | null;
}

export interface DbStats {
  drivers: number;
  constructors: number;
  races: number;
  race_results: number;
  laps: number;
  years: number[];
}

async function authedFetch(path: string, token: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      Authorization: `Bearer ${token}`,
      ...init.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed (${res.status})`);
  }
  return res;
}

export async function triggerIngest(
  token: string,
  years: number[],
  laps: boolean = false
): Promise<{ message: string }> {
  const res = await authedFetch('/admin/ingest', token, {
    method: 'POST',
    body: JSON.stringify({ years, laps }),
  });
  return res.json();
}

export async function getIngestStatus(token: string): Promise<IngestStatus> {
  const res = await authedFetch('/admin/ingest/status', token);
  return res.json();
}

export async function getDbStats(token: string): Promise<DbStats> {
  const res = await authedFetch('/admin/db/stats', token);
  return res.json();
}

export async function clearServerCache(token: string): Promise<{ message: string }> {
  const res = await authedFetch('/api/cache/clear', token, { method: 'POST' });
  return res.json();
}

export async function triggerModelTraining(token: string): Promise<{ message: string }> {
  const res = await authedFetch('/predict/train', token, { method: 'POST' });
  return res.json();
}

export interface LiveRelay {
  race_id: string;
  year: number;
  gp: string;
  session: string;
  replay: boolean;
  replay_speed: number | null;
  status: string;
  detail: string | null;
  clock: string | null;
  started_at: string;
}

/** Follow a session on OpenF1. With replaySpeed, replay a finished one that many times faster. */
export async function startLiveRelay(
  token: string, year: number, gp: string, session: string, replaySpeed: number | null,
): Promise<LiveRelay> {
  const res = await authedFetch('/admin/live/relay', token, {
    method: 'POST',
    body: JSON.stringify({ year, gp, session, replay_speed: replaySpeed }),
  });
  return res.json();
}

export async function listLiveRelays(token: string): Promise<LiveRelay[]> {
  const res = await authedFetch('/admin/live/relays', token);
  return res.json();
}

export async function stopLiveRelay(token: string, raceId: string): Promise<void> {
  await authedFetch(`/admin/live/relay/${encodeURIComponent(raceId)}`, token, { method: 'DELETE' });
}
