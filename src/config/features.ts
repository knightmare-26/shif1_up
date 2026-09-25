import { useEffect, useState } from 'react';
import { backendApi, LiveFeedStatus } from '../services/backendApi';

/**
 * Whether the Live pages have anything to show, asked of the API (GET /live/status): live data
 * needs the OpenF1 feed to be connected (credentials on the server), and otherwise an admin can
 * run a replay of a finished session. With neither, /live and /live-monitor show a "coming soon"
 * notice. Being a runtime check, connecting the feed turns the pages on without a new build.
 */
export function useLiveTiming(): { enabled: boolean; loading: boolean; status: LiveFeedStatus | null } {
  const [status, setStatus] = useState<LiveFeedStatus | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    backendApi.getLiveStatus()
      .then((s) => { if (!cancelled) setStatus(s); })
      .catch(() => { /* treated as off */ })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);
  return { enabled: !!status?.enabled, loading, status };
}
