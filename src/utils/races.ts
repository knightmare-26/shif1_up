import type { RaceEvent } from '../services/backendApi';

/** Results are keyed by the GP name without " Grand Prix" ("Dutch", "Mexico City"). */
export const gpToken = (raceName: string): string => raceName.replace(' Grand Prix', '').trim();

/** Schedules list pre-season testing as round 0 — it isn't a race weekend. */
export const isRaceRound = (r: RaceEvent): boolean => r.round > 0;
