import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, Calendar, MapPin, Radio, TrendingUp } from 'lucide-react';
import { backendApi, RaceEvent, LiveRaceState, LiveSessionInfo } from '../services/backendApi';
import { daysUntil, describeDaysUntil, formatDate, isPastDate } from '../utils/dates';
import { isRaceRound, LiveSession, LIVE_SESSION_LABELS, liveMonitorPath } from '../utils/races';
import LiveSectionTabs from './LiveSectionTabs';
import LiveComingSoon from './LiveComingSoon';
import { LIVE_TIMING_ENABLED } from '../config/features';
import {
  Card, CardBody, CardHeader, DetailList, EmptyState, FadeIn, LoadingState, PageHeader, PageShell,
  PositionBadge, TabPanel,
} from './ui';

const LIVE_POLL_MS = 15_000;

const LiveOverview: React.FC = () => {
  const year = new Date().getFullYear();
  const [schedule, setSchedule] = useState<RaceEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [liveState, setLiveState] = useState<LiveRaceState | null>(null);
  const [activeSession, setActiveSession] = useState<LiveSessionInfo | null>(null);

  useEffect(() => {
    backendApi.getRaceSchedule(year)
      .then((data) => setSchedule(Array.isArray(data) ? data.filter(isRaceRound) : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [year]);

  const nextRace = schedule.find((r) => !isPastDate(r.date));
  const lastRace = [...schedule].reverse().find((r) => isPastDate(r.date));
  const completed = schedule.filter((r) => isPastDate(r.date)).length;
  const nextIn = nextRace ? daysUntil(nextRace.date) : null;

  // Poll the next weekend for whichever of its sessions the poller is publishing right now
  // (practice, qualifying, sprint, race) and show that session's positions.
  const gpToken = nextRace ? nextRace.race_name.replace(/ /g, '_').replace(/\//g, '-') : '';
  useEffect(() => {
    if (!nextRace) return;
    const raceId = `${year}_${gpToken}`;
    let cancelled = false;
    const fetchState = async () => {
      try {
        const { sessions } = await backendApi.getLiveSessions(raceId);
        const active = sessions.find((s) => s.live) ?? null;
        if (cancelled) return;
        setActiveSession(active);
        setLiveState(active ? await backendApi.getLiveRaceState(active.race_id) : null);
      } catch { /* keep what we have */ }
    };
    fetchState();
    const id = setInterval(fetchState, LIVE_POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [nextRace?.race_name, year]); // eslint-disable-line react-hooks/exhaustive-deps

  const sessionLive = !!activeSession && liveState?.session_status === 'live' && (liveState?.positions?.length ?? 0) > 0;
  const sessionCode = (activeSession?.session ?? 'R') as LiveSession;
  const sessionLabel = LIVE_SESSION_LABELS[sessionCode] ?? activeSession?.session ?? '';
  const isTimed = activeSession?.session_type === 'timed';

  return (
    <PageShell>
      <PageHeader title="Live" subtitle="Real-time Formula 1 data — active during race weekends" />
      <LiveSectionTabs active="overview" />

      <TabPanel id="overview" idPrefix="live" className="space-y-6 pt-6">
        <FadeIn>
          <Card>
            <CardHeader
              title={sessionLive ? `Live — ${sessionLabel}` : 'Live Session Status'}
              icon={<Activity className="h-4 w-4" />}
              action={
                sessionLive ? (
                  <span className="flex items-center gap-2 rounded-full bg-racing-red/15 px-3 py-1 text-xs font-semibold text-racing-red">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-racing-red" aria-hidden="true" />
                    LIVE{!isTimed && liveState?.lap ? ` — Lap ${liveState.lap}${liveState.total_laps ? ` / ${liveState.total_laps}` : ''}` : ''}
                  </span>
                ) : (
                  <span className="rounded-full border border-gray-700 px-3 py-1 text-xs text-gray-400">No session active</span>
                )
              }
            />
            {sessionLive ? (
              <CardBody className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm text-gray-300">
                    <span className="font-semibold text-white">{sessionLabel}</span> · {nextRace?.race_name}
                  </p>
                  <Link
                    to={liveMonitorPath(year, gpToken, sessionCode)}
                    className="inline-flex items-center gap-2 rounded-lg bg-racing-red px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/60"
                  >
                    <Radio className="h-4 w-4" aria-hidden="true" /> Go to {sessionLabel}
                  </Link>
                </div>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                {liveState!.positions!.slice(0, 10).map((p) => (
                  <div key={p.driver_id} className="flex items-center justify-between rounded-lg bg-gray-800/50 px-3 py-2 text-sm">
                    <span className="flex items-center gap-3">
                      <PositionBadge position={p.position} label={`P${p.position}`} />
                      <span className="font-medium text-white">{p.driver_name || p.driver_id}</span>
                    </span>
                    <span className="tabular-nums text-gray-400">{(isTimed ? p.best_lap_time : p.gap) ?? p.last_lap_time ?? '—'}</span>
                  </div>
                ))}
                </div>
              </CardBody>
            ) : (
              <EmptyState
                icon={<Radio className="h-10 w-10" />}
                title="Live timing appears here during race weekends"
                message={nextRace
                  ? `Next up: ${nextRace.race_name} — ${describeDaysUntil(nextIn).toLowerCase()}.`
                  : 'No upcoming sessions on the calendar.'}
                action={
                  <Link
                    to="/live-monitor"
                    className="inline-flex items-center gap-2 rounded-lg bg-racing-red px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/60"
                  >
                    <Radio className="h-4 w-4" aria-hidden="true" /> Open Live Monitor
                  </Link>
                }
              />
            )}
          </Card>
        </FadeIn>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title={`Next Race — ${year}`} icon={<Calendar className="h-4 w-4" />} />
            {loading ? <LoadingState /> : nextRace ? (
              <DetailList rows={[
                ['Race', nextRace.race_name],
                ['Circuit', nextRace.circuit_name],
                ['Country', nextRace.country],
                ['Date', formatDate(nextRace.date)],
                ['Countdown', describeDaysUntil(nextIn)],
              ]} />
            ) : <EmptyState title={`No upcoming races found for ${year}`} />}
          </Card>

          <Card>
            <CardHeader title={`Last Race — ${year}`} icon={<MapPin className="h-4 w-4" />} />
            {loading ? <LoadingState /> : lastRace ? (
              <DetailList rows={[
                ['Race', lastRace.race_name],
                ['Circuit', lastRace.circuit_name],
                ['Country', lastRace.country],
                ['Date', formatDate(lastRace.date)],
              ]} />
            ) : <EmptyState title="No completed races yet this season" />}
          </Card>
        </div>

        <Card>
          <CardHeader title={`${year} Season Progress`} icon={<TrendingUp className="h-4 w-4" />} />
          {loading ? <LoadingState className="py-8" /> : (
            <CardBody className="flex items-center gap-4">
              <div
                className="h-2 flex-1 overflow-hidden rounded-full bg-gray-800"
                role="progressbar" aria-valuemin={0} aria-valuemax={schedule.length} aria-valuenow={completed}
                aria-label="Races completed"
              >
                <div
                  className="h-full rounded-full bg-racing-red transition-[width] duration-700"
                  style={{ width: schedule.length ? `${(completed / schedule.length) * 100}%` : '0%' }}
                />
              </div>
              <span className="whitespace-nowrap text-sm font-bold tabular-nums text-white">
                {completed} / {schedule.length} races
              </span>
            </CardBody>
          )}
        </Card>
      </TabPanel>
    </PageShell>
  );
};

const LiveAnalytics: React.FC = () => (LIVE_TIMING_ENABLED ? <LiveOverview /> : <LiveComingSoon />);

export default LiveAnalytics;
