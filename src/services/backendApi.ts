/**
 * Backend API Service - Handles communication with FastAPI backend
 */

import { Driver, Team, RaceResult } from '../types/f1';

export const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

/** Fired when the API says it (or its database) is waking up, so the app can show a banner and re-check. */
export const SERVICE_WAKING_EVENT = 'shif1:service-waking';
const announceWaking = () => window.dispatchEvent(new Event(SERVICE_WAKING_EVENT));

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  message?: string;
  timestamp: string;
  cache_hit?: boolean;
}

export interface DriverStanding {
  position: number;
  driver_id: string;
  driver_name: string;
  constructor: string;
  points: number;
  wins: number;
  podiums?: number;
  nationality: string;
  number?: number;
  /** Three-letter code (VER). Only in live API responses; the committed snapshots don't have it. */
  code?: string | null;
}

/** Race and sprint wins/podiums per driver, counted from the stored results. */
export interface DriverResultStats {
  code: string;
  driver_name: string | null;
  race_wins: number;
  race_podiums: number;
  sprint_wins: number;
  sprint_podiums: number;
}

export interface DriverStatsResponse {
  year: number;
  races_counted: number;
  sprints_counted: number;
  drivers: DriverResultStats[];
}

/** One driver's or team's row in the championship outlook (GET /api/predictions/championship). */
export interface ChampionshipRow {
  id: string;
  code: string | null;
  name: string;
  team: string | null;
  position: number;
  points: number;
  wins: number;
  /** Can still mathematically win the title. */
  alive: boolean;
  projected_points: number;
  points_p10: number;
  points_p90: number;
  projected_position: number;
  title_probability: number;
  /** Chance of each final position (index 0 = champion); null once the season is decided. */
  position_probabilities: number[] | null;
}

export interface ChampionshipOutlook {
  year: number;
  status: 'pre_season' | 'in_progress' | 'finished';
  rounds_completed: number;
  rounds_total: number;
  remaining: { round: number; name: string; sprint: boolean }[];
  sprint_calendar_known: boolean;
  clinched: boolean;
  champion: string | null;
  max_points_remaining: number;
  next_race_clinch: { round: number; race_name: string; rival: string; rival_name: string; margin_needed: number } | null;
  standings: ChampionshipRow[];
  method: { simulations: number; beta: number; calibration_races: number; model_trained_at: string | null };
  computed_at: string;
}

export interface ChampionshipBacktestSummary {
  checkpoints: number;
  champion_accuracy: number;
  leader_accuracy: number;
  mean_p_actual_champion: number;
  brier: number;
  log_score: number;
  final_order_mae: number;
}

export interface ChampionshipBacktest {
  seasons: { year: number; champion: string; constructors_champion: string; rounds: number }[];
  drivers: ChampionshipBacktestSummary | Record<string, never>;
  constructors: ChampionshipBacktestSummary | Record<string, never>;
  computed_at: string | null;
}

export interface ConstructorStanding {
  position: number;
  constructor_id: string;
  constructor_name: string;
  points: number;
  wins: number;
  nationality: string;
}

export interface RaceEvent {
  round: number;
  race_name: string;
  circuit_name: string;
  country: string;
  location: string;
  date: string;
  time: string;
  url?: string;
  is_sprint?: boolean;
}

export interface PredictableRace {
  round: number;
  race_name: string;
  circuit_name: string;
  date: string;
  is_sprint: boolean;
}

export interface BacktestDriverRow {
  driver_id: string;
  driver_name: string;
  predicted_grid?: number | null;
  actual_grid?: number | null;
  predicted_position?: number | null;
  actual_position?: number | null;
}

export interface BacktestRace {
  year: number;
  round: number;
  race_id: string;
  race_name: string;
  circuit_name: string;
  quali_mae: number | null;
  race_mae: number | null;
  drivers: BacktestDriverRow[];
}

export interface BacktestResult {
  races: BacktestRace[];
}

export interface SessionData {
  year: number;
  round: number;
  session_type: string;
  session_name: string;
  date: string;
  time: string;
  status: string;
  results?: any[];
}

export interface LivePosition {
  driver_id: string;
  driver_name?: string;
  position: number;
  gap?: string;
  interval?: string;
  last_lap_time?: string;
  best_lap_time?: string;
  sector?: number;
  status?: string;
  tyre?: string;
}

export interface LiveSession {
  session_id: string;
  session_name: string;
  status: string;
  elapsed_time?: string;
  remaining_time?: string;
  track_status: string;
  positions: LivePosition[];
}

export interface LiveRaceState {
  race_id: string;
  session_status: string;
  track_status?: string;
  lap?: number;
  total_laps?: number;
  leader?: string;
  positions?: LivePosition[];
  timestamp?: string;
  message?: string;
}

export interface LiveSessionInfo {
  session: string;        // FP1 FP2 FP3 SQ S Q R
  race_id: string;        // the id to fetch state / open a WebSocket with
  session_type?: 'timed' | 'classified';
  session_status?: string;
  timestamp: string;
  live: boolean;          // the poller has refreshed it in the last couple of minutes
}

class BackendApiService {
  private baseUrl: string;
  private cache: Map<string, { data: any; timestamp: number; ttl: number }> = new Map();

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async makeRequest<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    try {
      const url = `${this.baseUrl}${endpoint}`;
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
        ...options,
      });

      if (!response.ok) {
        // While the database is asleep the API answers 503 "database_waking".
        // Say so plainly instead of surfacing "HTTP error! status: 503".
        if (response.status === 503) {
          const body = await response.json().catch(() => null);
          if (body?.detail === 'database_waking') {
            announceWaking();
            throw new Error(body.message || 'The database is waking up. This page will refresh when it is ready.');
          }
          // A data source the API depends on (e.g. the standings feed) is failing — say so, don't retry blindly.
          if (body?.detail === 'source_unavailable') {
            throw new Error(body.message || "A data source isn't responding right now. Try again in a moment.");
          }
        }
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      // fetch() rejects with a TypeError when the server can't be reached at all
      // (e.g. a sleeping host that is still booting).
      if (error instanceof TypeError) announceWaking();
      console.error(`API request failed for ${endpoint}:`, error);
      throw error;
    }
  }

  private getCacheKey(endpoint: string, params: Record<string, any> = {}): string {
    const paramString = new URLSearchParams(params).toString();
    return `${endpoint}${paramString ? `?${paramString}` : ''}`;
  }

  private isCacheValid(timestamp: number, ttl: number): boolean {
    return Date.now() - timestamp < ttl * 1000;
  }

  private async getCachedOrFetch<T>(
    endpoint: string,
    params: Record<string, any> = {},
    ttl: number = 300 // 5 minutes default
  ): Promise<T> {
    const cacheKey = this.getCacheKey(endpoint, params);
    const cached = this.cache.get(cacheKey);

    if (cached && this.isCacheValid(cached.timestamp, cached.ttl)) {
      console.log(`📦 Cache hit for ${cacheKey}`);
      return cached.data;
    }

    const paramString = new URLSearchParams(params).toString();
    const fullEndpoint = `${endpoint}${paramString ? `?${paramString}` : ''}`;
    
    const response = await this.makeRequest<T>(fullEndpoint);

    // Backend may return data directly (array/object) or wrapped in { success, data }
    const isWrapped = response && typeof response === 'object' &&
      'success' in (response as any) && 'data' in (response as any);
    const data: T = isWrapped ? (response as any).data : response as unknown as T;

    // An empty list is far more likely to be a hiccup than the truth (e.g. a rate-limited
    // upstream), so don't let it stick for the full TTL and keep a page empty until reload.
    const effectiveTtl = Array.isArray(data) && data.length === 0 ? Math.min(ttl, 15) : ttl;
    this.cache.set(cacheKey, {
      data,
      timestamp: Date.now(),
      ttl: effectiveTtl
    });
    console.log(`💾 Cached data for ${cacheKey}`);
    return data;
  }

  // Health check
  async healthCheck(): Promise<{ status: string; timestamp: string; service: string }> {
    try {
      const response = await this.makeRequest('/health');
      if (response.data && typeof response.data === 'object' && 'status' in response.data) {
        return response.data as { status: string; timestamp: string; service: string };
      }
    } catch (error) {
      console.warn('Health check failed, returning default status');
    }
    return { status: 'healthy', timestamp: new Date().toISOString(), service: 'Shif1 UP API' };
  }

  // ---------------------------------------------------------------------------
  // Static JSON helpers — served from public/data/ via CDN, no backend needed
  // ---------------------------------------------------------------------------

  private async fetchStatic<T>(url: string): Promise<T | null> {
    // Snapshots are only trustworthy for finished seasons. The current season
    // changes every race weekend (and its calendar can change mid-year), so a
    // committed snapshot would silently override fresher data from the API.
    const season = /\/data\/(?:standings|schedule|results)\/(\d{4})/.exec(url);
    if (season && Number(season[1]) >= new Date().getFullYear()) return null;

    try {
      const r = await fetch(url);
      if (!r.ok) return null;
      return (await r.json()) as T;
    } catch {
      return null;
    }
  }

  // Driver endpoints
  async getDriverStandings(
    year?: number,
    round?: number,
    useCache: boolean = true
  ): Promise<DriverStanding[]> {
    // Try static file first (CDN — fast, no backend required)
    if (year && !round) {
      const staticData = await this.fetchStatic<DriverStanding[]>(
        `/data/standings/${year}_drivers.json`
      );
      if (staticData && staticData.length > 0) {
        console.log(`📄 Static standings for ${year}`);
        return staticData;
      }
    }

    const params: Record<string, any> = {};
    if (year) params.year = year;
    if (round) params.round = round;
    if (!useCache) params.use_cache = false;

    return this.getCachedOrFetch('/api/drivers', params, 3600); // 1 hour cache
  }

  async getDriverStats(year: number): Promise<DriverStatsResponse> {
    return this.getCachedOrFetch('/api/driver-stats', { year }, 600);
  }

  async getChampionshipOutlook(kind: 'drivers' | 'constructors', year: number): Promise<ChampionshipOutlook> {
    const endpoint = kind === 'drivers' ? '/api/predictions/championship' : '/api/predictions/constructors-championship';
    return this.getCachedOrFetch(endpoint, { year }, 600);
  }

  async getChampionshipBacktest(): Promise<ChampionshipBacktest> {
    return this.getCachedOrFetch('/predict/championship/backtest', {}, 3600);
  }

  async getDriverDetails(driverId: string, year?: number): Promise<any> {
    const params: Record<string, any> = {};
    if (year) params.year = year;

    return this.getCachedOrFetch(`/drivers/${driverId}`, params, 1800); // 30 minutes cache
  }

  // Constructor endpoints
  async getConstructorStandings(
    year?: number,
    round?: number,
    useCache: boolean = true
  ): Promise<ConstructorStanding[]> {
    // Try static file first
    if (year && !round) {
      const staticData = await this.fetchStatic<ConstructorStanding[]>(
        `/data/standings/${year}_constructors.json`
      );
      if (staticData && staticData.length > 0) {
        console.log(`📄 Static constructor standings for ${year}`);
        return staticData;
      }
    }

    const params: Record<string, any> = {};
    if (year) params.year = year;
    if (round) params.round = round;
    if (!useCache) params.use_cache = false;

    return this.getCachedOrFetch('/api/constructors', params, 3600); // 1 hour cache
  }

  // Race endpoints
  async getRaceSchedule(year?: number, useCache: boolean = true): Promise<RaceEvent[]> {
    // Try static file first
    if (year) {
      const staticData = await this.fetchStatic<RaceEvent[]>(
        `/data/schedule/${year}.json`
      );
      if (staticData && staticData.length > 0) {
        console.log(`📄 Static schedule for ${year}`);
        return staticData;
      }
    }

    const params: Record<string, any> = {};
    if (year) params.year = year;
    if (!useCache) params.use_cache = false;

    return this.getCachedOrFetch('/api/races', params, 7200); // 2 hours cache
  }

  async getRaceDetails(raceId: string, year?: number): Promise<any> {
    const params: Record<string, any> = {};
    if (year) params.year = year;

    return this.getCachedOrFetch(`/api/races/${raceId}`, params, 1800); // 30 minutes cache
  }

  // Session endpoints
  async getSessionData(
    sessionId: string,
    year?: number,
    includeTelemetry: boolean = false
  ): Promise<SessionData> {
    const params: Record<string, any> = {};
    if (year) params.year = year;
    if (includeTelemetry) params.include_telemetry = true;

    return this.getCachedOrFetch(`/api/sessions/${sessionId}`, params, 1800); // 30 minutes cache
  }

  // Live data endpoints
  async getLiveSessionData(): Promise<LiveSession> {
    return this.getCachedOrFetch('/api/live/session', {}, 30); // 30 seconds cache for live data
  }

  async getLivePositions(): Promise<LivePosition[]> {
    return this.getCachedOrFetch('/api/live/positions', {}, 30); // 30 seconds cache for live data
  }

  async getLiveSessions(raceId: string): Promise<{ race_id: string; sessions: LiveSessionInfo[] }> {
    return this.getCachedOrFetch(`/live/${raceId}/sessions`, {}, 10);
  }

  async getLiveRaceState(raceId: string): Promise<LiveRaceState> {
    return this.getCachedOrFetch(`/live/${raceId}/state`, {}, 15);
  }

  // Telemetry endpoints
  async getDriverTelemetry(
    sessionId: string,
    driverId: string,
    year?: number,
    lap?: number
  ): Promise<any> {
    const params: Record<string, any> = {};
    if (year) params.year = year;
    if (lap) params.lap = lap;

    return this.getCachedOrFetch(`/api/telemetry/${sessionId}/${driverId}`, params, 1800); // 30 minutes cache
  }

  // Weather endpoints
  async getSessionWeather(sessionId: string, year?: number): Promise<any> {
    const params: Record<string, any> = {};
    if (year) params.year = year;

    return this.getCachedOrFetch(`/api/weather/${sessionId}`, params, 1800); // 30 minutes cache
  }

  // Cache management
  async clearCache(): Promise<{ message: string }> {
    try {
      const response = await this.makeRequest('/api/cache/clear', { method: 'POST' });
      this.cache.clear(); // Clear local cache too
      if (response.data && typeof response.data === 'object' && 'message' in response.data) {
        return response.data as { message: string };
      }
    } catch (error) {
      console.warn('Cache clear request failed, clearing local cache only');
      this.cache.clear();
    }
    return { message: 'Cache cleared successfully' };
  }

  async getCacheStats(): Promise<any> {
    return this.makeRequest('/api/cache/stats');
  }

  // Background refresh
  async refreshData(dataType: string): Promise<{ message: string }> {
    try {
      const response = await this.makeRequest(`/api/refresh/${dataType}`, { method: 'POST' });
      if (response.data && typeof response.data === 'object' && 'message' in response.data) {
        return response.data as { message: string };
      }
    } catch (error) {
      console.warn(`Background refresh request failed for ${dataType}`);
    }
    return { message: `Background refresh started for ${dataType}` };
  }

  // Race detail endpoints — backend race_id format: "{year}_{gp}" e.g. "2024_Bahrain"
  async getRaceResults(year: number, gp: string, session: string = 'R'): Promise<any> {
    // Try static files first (main race only) — filenames: {year}_{round:02d}_{gp}.json
    // We don't know the round here, so glob via schedule
    if (session === 'R') {
      const scheduleStatic = await this.fetchStatic<RaceEvent[]>(`/data/schedule/${year}.json`);
      if (scheduleStatic) {
        const gpSlug = gp.replace(/ /g, '_').replace(/\//g, '-');
        const race = scheduleStatic.find(r =>
          r.race_name.replace(/ /g, '_').replace(/\//g, '-') === gpSlug
        );
        if (race) {
          const round = String(race.round).padStart(2, '0');
          const staticData = await this.fetchStatic<any>(
            `/data/results/${year}_${round}_${gpSlug}.json`
          );
          if (staticData) {
            console.log(`📄 Static results for ${year} R${round} ${gp}`);
            return staticData;
          }
        }
      }
    }

    const raceId = `${year}_${gp.replace(/ /g, '_')}`;
    return this.getCachedOrFetch(`/race/${raceId}/results`, { session }, 1800); // 30 minutes cache
  }

  async getSessionLaps(year: number, gp: string, _session: string, driver?: string): Promise<any> {
    const raceId = `${year}_${gp.replace(/ /g, '_')}`;
    const params: any = {};
    if (driver) params.driver = driver;
    return this.getCachedOrFetch(`/race/${raceId}/laps`, params, 1800); // 30 minutes cache
  }

  // ---------------------------------------------------------------------------
  // Prediction endpoints
  // ---------------------------------------------------------------------------

  /** `force` skips the short cache — needed right after a prediction, which is what trains a cold instance's models. */
  async getPredictionStatus(force = false): Promise<any> {
    if (force) this.cache.delete(this.getCacheKey('/predict/status', {}));
    return this.getCachedOrFetch('/predict/status', {}, 10);
  }

  async getPredictionCircuits(): Promise<PredictableRace[]> {
    return this.getCachedOrFetch('/predict/circuits', {}, 300);
  }

  async getPredictionBacktest(): Promise<BacktestResult> {
    return this.getCachedOrFetch('/predict/backtest', {}, 300);
  }

  async predictQualifying(circuit: string): Promise<any> {
    const key = `/predict/qualifying?circuit=${encodeURIComponent(circuit)}`;
    const cached = this.cache.get(key);
    if (cached && this.isCacheValid(cached.timestamp, 300)) return cached.data;
    const response = await fetch(`${this.baseUrl}/predict/qualifying?circuit=${encodeURIComponent(circuit)}`);
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }
    const data = await response.json();
    this.cache.set(key, { data, timestamp: Date.now(), ttl: 300 });
    return data;
  }

  async predictRace(circuit: string): Promise<any> {
    const key = `/predict/race?circuit=${encodeURIComponent(circuit)}`;
    const cached = this.cache.get(key);
    if (cached && this.isCacheValid(cached.timestamp, 300)) return cached.data;
    const response = await fetch(`${this.baseUrl}/predict/race?circuit=${encodeURIComponent(circuit)}`);
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }
    const data = await response.json();
    this.cache.set(key, { data, timestamp: Date.now(), ttl: 300 });
    return data;
  }

  async predictSprint(circuit: string): Promise<any> {
    const key = `/predict/sprint?circuit=${encodeURIComponent(circuit)}`;
    const cached = this.cache.get(key);
    if (cached && this.isCacheValid(cached.timestamp, 300)) return cached.data;
    const response = await fetch(`${this.baseUrl}/predict/sprint?circuit=${encodeURIComponent(circuit)}`);
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }
    const data = await response.json();
    this.cache.set(key, { data, timestamp: Date.now(), ttl: 300 });
    return data;
  }

  // Utility methods
  clearLocalCache(): void {
    this.cache.clear();
    console.log('🧹 Local cache cleared');
  }

  getLocalCacheStats(): { size: number; keys: string[] } {
    return {
      size: this.cache.size,
      keys: Array.from(this.cache.keys())
    };
  }

  // Convert backend data to frontend types
  convertDriverStandingToDriver(standing: DriverStanding): Driver {
    return {
      id: standing.driver_id,
      name: standing.driver_name,
      team: standing.constructor,
      number: standing.number || 0,
      nationality: standing.nationality,
      points: standing.points,
      position: standing.position,
      wins: standing.wins,
      podiums: standing.podiums || 0
    };
  }

  convertConstructorStandingToTeam(standing: ConstructorStanding): Team {
    return {
      id: standing.constructor_id,
      name: standing.constructor_name,
      nationality: standing.nationality,
      points: standing.points,
      position: standing.position,
      wins: standing.wins
    };
  }

  convertRaceEventToRaceResult(event: RaceEvent): RaceResult {
    return {
      id: `race_${event.round}`,
      raceName: event.race_name,
      circuitName: event.circuit_name,
      country: event.country,
      locality: event.location,
      date: event.date,
      season: new Date(event.date).getFullYear(),
      round: event.round,
      results: [] // Would be populated separately
    };
  }
}

// Create singleton instance
export const backendApi = new BackendApiService();

// Export the class for testing
export { BackendApiService };
