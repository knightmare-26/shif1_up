/**
 * Backend API Service - Handles communication with FastAPI backend
 */

import { Driver, Team, RaceResult } from '../types/f1';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

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
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
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

    this.cache.set(cacheKey, {
      data,
      timestamp: Date.now(),
      ttl: ttl
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
  async getRaceResults(year: number, gp: string): Promise<any> {
    // Try static files first — filenames: {year}_{round:02d}_{gp}.json
    // We don't know the round here, so glob via schedule
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

    const raceId = `${year}_${gp.replace(/ /g, '_')}`;
    return this.getCachedOrFetch(`/race/${raceId}/results`, {}, 1800); // 30 minutes cache
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

  async getPredictionStatus(): Promise<any> {
    return this.getCachedOrFetch('/predict/status', {}, 10);
  }

  async getPredictionCircuits(): Promise<string[]> {
    return this.getCachedOrFetch('/predict/circuits', {}, 300);
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

  async triggerModelTraining(): Promise<{ message: string }> {
    const response = await fetch(`${this.baseUrl}/predict/train`, { method: 'POST' });
    return response.json();
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
