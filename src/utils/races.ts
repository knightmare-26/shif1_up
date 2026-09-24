import type { RaceEvent } from '../services/backendApi';

/** Results are keyed by the GP name without " Grand Prix" ("Dutch", "Mexico City"). */
export const gpToken = (raceName: string): string => raceName.replace(' Grand Prix', '').trim();

/** Schedules list pre-season testing as round 0 — it isn't a race weekend. */
export const isRaceRound = (r: RaceEvent): boolean => r.round > 0;

/** Sessions the live monitor can follow — the codes match the poller's --session flag. */
export type LiveSession = 'FP1' | 'FP2' | 'FP3' | 'SQ' | 'S' | 'Q' | 'R';

export const LIVE_SESSION_LABELS: Record<LiveSession, string> = {
  FP1: 'Practice 1', FP2: 'Practice 2', FP3: 'Practice 3',
  SQ: 'Sprint Qualifying', S: 'Sprint', Q: 'Qualifying', R: 'Race',
};

/** In running order. A sprint weekend has one practice session, then sprint qualifying and the sprint. */
export const sessionsForWeekend = (isSprint: boolean): LiveSession[] =>
  isSprint ? ['FP1', 'SQ', 'S', 'Q', 'R'] : ['FP1', 'FP2', 'FP3', 'Q', 'R'];

/**
 * Where a qualifying position ends up: Q3 is the top 10, and the rest are knocked out six at a time
 * (P17-22 in Q1, P11-16 in Q2 on a 22-car grid; five each on 20 cars). Sprint qualifying uses the same
 * shape. Returns null for sessions with no knockouts or a grid too small to split.
 */
export type QualifyingZone = 'Q3' | 'Q2' | 'Q1';

export const qualifyingZone = (position: number, fieldSize: number): QualifyingZone | null => {
  if (fieldSize < 12) return null;
  const knockedOutPerRound = Math.floor((fieldSize - 10) / 2);
  if (position <= 10) return 'Q3';
  return position <= 10 + knockedOutPerRound ? 'Q2' : 'Q1';
};

/** The poller's id for a session: the race keeps the bare `{year}_{gp}`, others get a `_{code}` suffix. */
export const liveRaceId = (year: number, gp: string, session: LiveSession): string =>
  session === 'R' ? `${year}_${gp}` : `${year}_${gp}_${session}`;

/** Deep link into the Live Monitor for one session; the page starts monitoring it straight away. */
export const liveMonitorPath = (year: number, gp: string, session: LiveSession): string =>
  `/live-monitor?year=${year}&gp=${encodeURIComponent(gp)}&session=${session}`;
