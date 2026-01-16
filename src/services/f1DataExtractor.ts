/**
 * F1 Data Extractor Service
 * Efficiently fetches and organizes F1 data by year to minimize API calls
 */

import { backendApi } from './backendApi';
import { Driver, Team, RaceResult } from '../types/f1';

export interface F1DataByYear {
  [year: number]: {
    drivers: Driver[];
    teams: Team[];
    races: RaceResult[];
    lastUpdated: Date;
  };
}

export interface DataExtractionStats {
  totalYears: number;
  yearsProcessed: number;
  totalDrivers: number;
  totalTeams: number;
  totalRaces: number;
  lastUpdated: Date;
  errors: string[];
}

class F1DataExtractor {
  private dataCache: F1DataByYear = {};
  private extractionInProgress = false;
  private readonly CACHE_KEY = 'f1_data_by_year';
  private readonly CACHE_EXPIRY = 24 * 60 * 60 * 1000; // 24 hours

  constructor() {
    this.loadFromCache();
  }

  /**
   * Extract all F1 data for a range of years
   */
  async extractAllData(startYear: number = 2000, endYear?: number): Promise<DataExtractionStats> {
    if (this.extractionInProgress) {
      throw new Error('Data extraction already in progress');
    }

    this.extractionInProgress = true;
    const stats: DataExtractionStats = {
      totalYears: 0,
      yearsProcessed: 0,
      totalDrivers: 0,
      totalTeams: 0,
      totalRaces: 0,
      lastUpdated: new Date(),
      errors: []
    };

    try {
      const currentYear = endYear || new Date().getFullYear();
      stats.totalYears = currentYear - startYear + 1;

      console.log(`🚀 Starting F1 data extraction for years ${startYear}-${currentYear}...`);

      // Process years in batches to avoid overwhelming the API
      const batchSize = 3;
      const years = Array.from({ length: currentYear - startYear + 1 }, (_, i) => startYear + i);
      
      for (let i = 0; i < years.length; i += batchSize) {
        const batch = years.slice(i, i + batchSize);
        console.log(`📊 Processing batch: ${batch.join(', ')}`);
        
        await Promise.all(batch.map(year => this.extractYearData(year, stats)));
        
        // Small delay between batches to be respectful to the API
        if (i + batchSize < years.length) {
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
      }

      // Save to cache
      this.saveToCache();
      
      console.log(`✅ Data extraction completed! Processed ${stats.yearsProcessed} years`);
      return stats;

    } catch (error) {
      console.error('❌ Data extraction failed:', error);
      throw error;
    } finally {
      this.extractionInProgress = false;
    }
  }

  /**
   * Extract data for a specific year
   */
  private async extractYearData(year: number, stats: DataExtractionStats): Promise<void> {
    try {
      console.log(`📅 Extracting data for ${year}...`);

      // Fetch all data for this year in parallel
      const [driverStandings, constructorStandings, raceSchedule] = await Promise.all([
        backendApi.getDriverStandings(year).catch(err => {
          console.warn(`⚠️ Failed to fetch drivers for ${year}:`, err);
          return [];
        }),
        backendApi.getConstructorStandings(year).catch(err => {
          console.warn(`⚠️ Failed to fetch constructors for ${year}:`, err);
          return [];
        }),
        backendApi.getRaceSchedule(year).catch(err => {
          console.warn(`⚠️ Failed to fetch races for ${year}:`, err);
          return [];
        })
      ]);

      // Convert to frontend types
      const drivers: Driver[] = driverStandings.map(standing => 
        backendApi.convertDriverStandingToDriver(standing)
      );

      const teams: Team[] = constructorStandings.map(standing => 
        backendApi.convertConstructorStandingToTeam(standing)
      );

      const races: RaceResult[] = raceSchedule.map(event => 
        backendApi.convertRaceEventToRaceResult(event)
      );

      // Store in cache
      this.dataCache[year] = {
        drivers,
        teams,
        races,
        lastUpdated: new Date()
      };

      // Update stats
      stats.yearsProcessed++;
      stats.totalDrivers += drivers.length;
      stats.totalTeams += teams.length;
      stats.totalRaces += races.length;

      console.log(`✅ ${year}: ${drivers.length} drivers, ${teams.length} teams, ${races.length} races`);

    } catch (error) {
      const errorMsg = `Failed to extract data for ${year}: ${error}`;
      console.error(`❌ ${errorMsg}`);
      stats.errors.push(errorMsg);
    }
  }

  /**
   * Get data for a specific year
   */
  getYearData(year: number): { drivers: Driver[]; teams: Team[]; races: RaceResult[] } | null {
    const yearData = this.dataCache[year];
    if (!yearData) {
      return null;
    }

    return {
      drivers: yearData.drivers,
      teams: yearData.teams,
      races: yearData.races
    };
  }

  /**
   * Get all available years
   */
  getAvailableYears(): number[] {
    return Object.keys(this.dataCache).map(Number).sort((a, b) => b - a);
  }

  /**
   * Get data extraction status
   */
  getExtractionStatus(): {
    inProgress: boolean;
    yearsExtracted: number;
    totalYears: number;
    lastUpdated: Date | null;
  } {
    const years = this.getAvailableYears();
    const lastYearData = years.length > 0 ? this.dataCache[years[0]] : null;

    return {
      inProgress: this.extractionInProgress,
      yearsExtracted: years.length,
      totalYears: years.length,
      lastUpdated: lastYearData?.lastUpdated || null
    };
  }

  /**
   * Store data for a specific year
   */
  storeYearData(year: number, drivers: Driver[], teams: Team[], races: RaceResult[] = []): void {
    this.dataCache[year] = {
      drivers,
      teams,
      races,
      lastUpdated: new Date()
    };
    this.saveToCache();
  }

  /**
   * Clear all cached data
   */
  clearCache(): void {
    this.dataCache = {};
    localStorage.removeItem(this.CACHE_KEY);
    console.log('🧹 F1 data cache cleared');
  }

  /**
   * Load data from localStorage cache
   */
  private loadFromCache(): void {
    try {
      const cached = localStorage.getItem(this.CACHE_KEY);
      if (cached) {
        const parsed = JSON.parse(cached);
        const cacheTime = parsed.timestamp || 0;
        const now = Date.now();

        // Check if cache is still valid
        if (now - cacheTime < this.CACHE_EXPIRY) {
          this.dataCache = parsed.data || {};
          console.log(`📦 Loaded F1 data cache with ${Object.keys(this.dataCache).length} years`);
        } else {
          console.log('⏰ F1 data cache expired, will fetch fresh data');
        }
      }
    } catch (error) {
      console.warn('⚠️ Failed to load F1 data cache:', error);
    }
  }

  /**
   * Save data to localStorage cache
   */
  private saveToCache(): void {
    try {
      const cacheData = {
        data: this.dataCache,
        timestamp: Date.now()
      };
      localStorage.setItem(this.CACHE_KEY, JSON.stringify(cacheData));
      console.log('💾 F1 data cache saved');
    } catch (error) {
      console.warn('⚠️ Failed to save F1 data cache:', error);
    }
  }

  /**
   * Get comprehensive data summary
   */
  getDataSummary(): {
    totalYears: number;
    years: number[];
    totalDrivers: number;
    totalTeams: number;
    totalRaces: number;
    lastUpdated: Date | null;
  } {
    const years = this.getAvailableYears();
    let totalDrivers = 0;
    let totalTeams = 0;
    let totalRaces = 0;
    let lastUpdated: Date | null = null;

    years.forEach(year => {
      const yearData = this.dataCache[year];
      if (yearData) {
        totalDrivers += yearData.drivers.length;
        totalTeams += yearData.teams.length;
        totalRaces += yearData.races.length;
        
        if (!lastUpdated || yearData.lastUpdated > lastUpdated) {
          lastUpdated = yearData.lastUpdated;
        }
      }
    });

    return {
      totalYears: years.length,
      years,
      totalDrivers,
      totalTeams,
      totalRaces,
      lastUpdated
    };
  }
}

// Export singleton instance
export const f1DataExtractor = new F1DataExtractor();
