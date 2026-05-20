import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Clock, Users, MapPin, Calendar, RefreshCw, TrendingUp, BarChart3, Trophy } from 'lucide-react';
import { backendApi } from '../services/backendApi';

interface LapDataItem {
  Driver: string;
  LapNumber: string;
  LapTime: number;
  Sector1?: number;
  Sector2?: number;
  Sector3?: number;
  PitIn?: boolean;
  PitOut?: boolean;
}

interface LapDataResponse {
  year: number;
  gp: string;
  session: string;
  driver?: string;
  laps: LapDataItem[];
}

const LapData: React.FC = () => {
  const [lapData, setLapData] = useState<LapDataResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedYear, setSelectedYear] = useState(2024);
  const [selectedGP, setSelectedGP] = useState('Bahrain');
  const [selectedSession, setSelectedSession] = useState('R');
  const [selectedDriver, setSelectedDriver] = useState<string>('');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const availableGPs = [
    'Bahrain', 'Saudi Arabia', 'Australia', 'Japan', 'China', 'Miami', 'Emilia Romagna',
    'Monaco', 'Canada', 'Spain', 'Austria', 'Great Britain', 'Hungary', 'Belgium',
    'Netherlands', 'Italy', 'Azerbaijan', 'Singapore', 'United States', 'Mexico',
    'Brazil', 'Las Vegas', 'Qatar', 'Abu Dhabi'
  ];

  const availableSessions = [
    { value: 'P1', label: 'Practice 1' },
    { value: 'P2', label: 'Practice 2' },
    { value: 'P3', label: 'Practice 3' },
    { value: 'Q', label: 'Qualifying' },
    { value: 'R', label: 'Race' }
  ];

  const availableYears = Array.from({ length: 25 }, (_, i) => 2000 + i);

  useEffect(() => {
    loadLapData();
  }, [selectedYear, selectedGP, selectedSession, selectedDriver]);

  const loadLapData = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const raw = await backendApi.getSessionLaps(
        selectedYear,
        selectedGP,
        selectedSession,
        selectedDriver || undefined
      );

      // Backend returns a flat array from DuckDB with ms times and snake_case keys.
      // Normalise into the shape the component expects.
      const rows: any[] = Array.isArray(raw) ? raw : (raw as any).laps ?? [];
      const msToSec = (ms: any) => (ms != null && !isNaN(Number(ms)) ? Number(ms) / 1000 : 0);

      const laps: LapDataItem[] = rows.map((r: any) => ({
        Driver:    r.driver_name ?? r.Driver ?? r.driver_id ?? '',
        LapNumber: String(r.lap_number ?? r.LapNumber ?? ''),
        LapTime:   msToSec(r.lap_time_ms ?? r.LapTime),
        Sector1:   msToSec(r.sector1_ms  ?? r.Sector1),
        Sector2:   msToSec(r.sector2_ms  ?? r.Sector2),
        Sector3:   msToSec(r.sector3_ms  ?? r.Sector3),
        PitIn:     r.pit ?? r.PitIn  ?? false,
        PitOut:    r.pit ?? r.PitOut ?? false,
      }));

      const normalized: LapDataResponse = {
        year: selectedYear,
        gp: selectedGP,
        session: selectedSession,
        driver: selectedDriver || undefined,
        laps,
      };

      setLapData(normalized);
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Error loading lap data:', err);
      setError(err instanceof Error ? err.message : 'Failed to load lap data');
    } finally {
      setIsLoading(false);
    }
  };

  const refreshData = () => {
    loadLapData();
  };

  const formatLapTime = (time: number): string => {
    if (isNaN(time) || time === 0) return 'Unavailable';
    
    const minutes = Math.floor(time / 60);
    const seconds = (time % 60).toFixed(3);
    return `${minutes}:${seconds.padStart(6, '0')}`;
  };

  const getFastestLap = (): LapDataItem | null => {
    if (!lapData?.laps.length) return null;
    
    const validLaps = lapData.laps.filter(lap => !isNaN(lap.LapTime) && lap.LapTime > 0);
    if (!validLaps.length) return null;
    
    return validLaps.reduce((fastest, current) => 
      current.LapTime < fastest.LapTime ? current : fastest
    );
  };

  const getDriverStats = () => {
    if (!lapData?.laps.length) return null;
    
    const validLaps = lapData.laps.filter(lap => !isNaN(lap.LapTime) && lap.LapTime > 0);
    if (!validLaps.length) return null;
    
    const times = validLaps.map(lap => lap.LapTime);
    const fastest = Math.min(...times);
    const slowest = Math.max(...times);
    const average = times.reduce((sum, time) => sum + time, 0) / times.length;
    
    return { fastest, slowest, average, totalLaps: validLaps.length };
  };

  const stats = getDriverStats();
  const fastestLap = getFastestLap();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-carbon-black text-pure-white p-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <RefreshCw className="w-8 h-8 animate-spin text-racing-red mx-auto mb-4" />
              <p className="text-lg">Loading lap data...</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-carbon-black text-pure-white p-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center py-12">
            <div className="text-racing-red text-6xl mb-4">⚠️</div>
            <h2 className="text-2xl font-bold mb-4">Error Loading Lap Data</h2>
            <p className="text-gray-400 mb-6">{error}</p>
            <button
              onClick={refreshData}
              className="bg-racing-red text-pure-white px-6 py-3 rounded-lg hover:bg-red-700 transition-colors"
            >
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-carbon-black text-pure-white p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-4xl font-racing text-racing-red mb-2">
                Lap Data Analysis
              </h1>
              <p className="text-gray-400">
                Detailed lap times and sector analysis
              </p>
            </div>
            <button
              onClick={refreshData}
              className="bg-racing-red text-pure-white px-4 py-2 rounded-lg hover:bg-red-700 transition-colors flex items-center space-x-2"
            >
              <RefreshCw className="w-4 h-4" />
              <span>Refresh</span>
            </button>
          </div>

          {/* Filters */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <div className="flex items-center space-x-2">
              <Calendar className="w-5 h-5 text-racing-red" />
              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                className="bg-gray-800 text-pure-white px-3 py-2 rounded-lg border border-gray-600 focus:border-racing-red focus:outline-none w-full"
              >
                {availableYears.map(year => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </select>
            </div>
            
            <div className="flex items-center space-x-2">
              <MapPin className="w-5 h-5 text-racing-red" />
              <select
                value={selectedGP}
                onChange={(e) => setSelectedGP(e.target.value)}
                className="bg-gray-800 text-pure-white px-3 py-2 rounded-lg border border-gray-600 focus:border-racing-red focus:outline-none w-full"
              >
                {availableGPs.map(gp => (
                  <option key={gp} value={gp}>{gp}</option>
                ))}
              </select>
            </div>

            <div className="flex items-center space-x-2">
              <Clock className="w-5 h-5 text-racing-red" />
              <select
                value={selectedSession}
                onChange={(e) => setSelectedSession(e.target.value)}
                className="bg-gray-800 text-pure-white px-3 py-2 rounded-lg border border-gray-600 focus:border-racing-red focus:outline-none w-full"
              >
                {availableSessions.map(session => (
                  <option key={session.value} value={session.value}>{session.label}</option>
                ))}
              </select>
            </div>

            <div className="flex items-center space-x-2">
              <Users className="w-5 h-5 text-racing-red" />
              <input
                type="text"
                placeholder="Driver code (e.g., VER)"
                value={selectedDriver}
                onChange={(e) => setSelectedDriver(e.target.value.toUpperCase())}
                className="bg-gray-800 text-pure-white px-3 py-2 rounded-lg border border-gray-600 focus:border-racing-red focus:outline-none w-full"
              />
            </div>
          </div>

          {lastUpdated && (
            <p className="text-sm text-gray-400">
              Last updated: {lastUpdated.toLocaleTimeString()}
            </p>
          )}
        </motion.div>

        {/* Stats Cards */}
        {stats && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8"
          >
            <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
              <div className="flex items-center space-x-3 mb-2">
                <Trophy className="w-6 h-6 text-yellow-500" />
                <h3 className="text-lg font-semibold text-pure-white">Fastest Lap</h3>
              </div>
              <p className="text-2xl font-bold text-yellow-500">
                {formatLapTime(stats.fastest)}
              </p>
              {fastestLap && (
                <p className="text-sm text-gray-400">
                  Lap {fastestLap.LapNumber}
                </p>
              )}
            </div>

            <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
              <div className="flex items-center space-x-3 mb-2">
                <Clock className="w-6 h-6 text-racing-red" />
                <h3 className="text-lg font-semibold text-pure-white">Average Lap</h3>
              </div>
              <p className="text-2xl font-bold text-pure-white">
                {formatLapTime(stats.average)}
              </p>
              <p className="text-sm text-gray-400">
                {stats.totalLaps} laps
              </p>
            </div>

            <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
              <div className="flex items-center space-x-3 mb-2">
                <BarChart3 className="w-6 h-6 text-turbo-teal" />
                <h3 className="text-lg font-semibold text-pure-white">Slowest Lap</h3>
              </div>
              <p className="text-2xl font-bold text-turbo-teal">
                {formatLapTime(stats.slowest)}
              </p>
              <p className="text-sm text-gray-400">
                Total laps: {stats.totalLaps}
              </p>
            </div>

            <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
              <div className="flex items-center space-x-3 mb-2">
                <TrendingUp className="w-6 h-6 text-pit-stop-yellow" />
                <h3 className="text-lg font-semibold text-pure-white">Lap Range</h3>
              </div>
              <p className="text-2xl font-bold text-pit-stop-yellow">
                {formatLapTime(stats.slowest - stats.fastest)}
              </p>
              <p className="text-sm text-gray-400">
                Time difference
              </p>
            </div>
          </motion.div>
        )}

        {/* Empty state */}
        {lapData && lapData.laps.length === 0 && (
          <div className="text-center py-16 text-gray-400">
            <Clock className="w-12 h-12 mx-auto mb-4 opacity-40" />
            <p className="text-lg">No lap data found for this session.</p>
            <p className="text-sm mt-2">Run <code className="bg-gray-800 px-1 rounded">python ingest/simple_ingest.py --laps --years {selectedYear}</code> to ingest lap data.</p>
          </div>
        )}

        {/* Lap Data Table */}
        {lapData && lapData.laps.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="bg-gray-900 rounded-xl p-6 shadow-2xl"
          >
            <div className="mb-6">
              <h2 className="text-2xl font-bold text-racing-red mb-2">
                {selectedYear} {selectedGP} Grand Prix - {availableSessions.find(s => s.value === selectedSession)?.label} Laps
              </h2>
              <div className="flex items-center space-x-6 text-sm text-gray-400">
                <div className="flex items-center space-x-2">
                  <Clock className="w-4 h-4" />
                  <span>{lapData.laps.length} laps</span>
                </div>
                {selectedDriver && (
                  <div className="flex items-center space-x-2">
                    <Users className="w-4 h-4" />
                    <span>Driver: {selectedDriver}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Lap Times Table */}
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Lap</th>
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Driver</th>
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Lap Time</th>
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Sector 1</th>
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Sector 2</th>
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Sector 3</th>
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Pit</th>
                  </tr>
                </thead>
                <tbody>
                  {lapData.laps.slice(0, 50).map((lap, index) => (
                    <motion.tr
                      key={`${lap.Driver}-${lap.LapNumber}`}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.01 }}
                      className={`border-b border-gray-800 hover:bg-gray-800 transition-colors ${
                        fastestLap && lap.LapNumber === fastestLap.LapNumber ? 'bg-yellow-900/20' : ''
                      }`}
                    >
                      <td className="py-3 px-4 text-pure-white font-semibold">
                        {lap.LapNumber}
                      </td>
                      <td className="py-3 px-4 text-pure-white">
                        {lap.Driver}
                      </td>
                      <td className="py-3 px-4">
                        <span className={`font-mono ${
                          fastestLap && lap.LapNumber === fastestLap.LapNumber 
                            ? 'text-yellow-500 font-bold' 
                            : 'text-pure-white'
                        }`}>
                          {formatLapTime(lap.LapTime)}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-gray-400 font-mono">
                        {lap.Sector1 ? formatLapTime(lap.Sector1) : 'N/A'}
                      </td>
                      <td className="py-3 px-4 text-gray-400 font-mono">
                        {lap.Sector2 ? formatLapTime(lap.Sector2) : 'N/A'}
                      </td>
                      <td className="py-3 px-4 text-gray-400 font-mono">
                        {lap.Sector3 ? formatLapTime(lap.Sector3) : 'N/A'}
                      </td>
                      <td className="py-3 px-4">
                        {lap.PitIn || lap.PitOut ? (
                          <span className="px-2 py-1 bg-orange-900 text-orange-300 rounded text-xs">
                            PIT
                          </span>
                        ) : (
                          <span className="text-gray-500">-</span>
                        )}
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>

            {lapData.laps.length > 50 && (
              <div className="mt-4 text-center text-gray-400">
                Showing first 50 laps of {lapData.laps.length} total laps
              </div>
            )}
          </motion.div>
        )}
      </div>
    </div>
  );
};

export default LapData;
