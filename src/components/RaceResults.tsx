import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Flag, Clock, Trophy, Users, MapPin, RefreshCw, ExternalLink, ChevronDown } from 'lucide-react';
import { backendApi, RaceEvent } from '../services/backendApi';

const SESSIONS: { id: string; label: string }[] = [
  { id: 'R',   label: 'Race' },
  { id: 'Q',   label: 'Qualifying' },
  { id: 'S',   label: 'Sprint' },
  { id: 'SQ',  label: 'Sprint Qualifying' },
  { id: 'FP1', label: 'Practice 1' },
  { id: 'FP2', label: 'Practice 2' },
  { id: 'FP3', label: 'Practice 3' },
];

interface RaceResult {
  DriverNumber: string;
  BroadcastName: string;
  Abbreviation: string;
  DriverId: string;
  TeamName: string;
  TeamColor: string;
  TeamId: string;
  FirstName: string;
  LastName: string;
  FullName: string;
  HeadshotUrl: string;
  CountryCode: string;
  Position: string;
  ClassifiedPosition: string;
  GridPosition: string;
  Time: number;
  Status: string;
  Points: string;
  Laps: string;
}

interface RaceResultsData {
  year: number;
  gp: string;
  session: string;
  results: RaceResult[];
}

const RaceResults: React.FC<{ year: number }> = ({ year: selectedYear }) => {
  const [raceData, setRaceData] = useState<RaceResultsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [schedule, setSchedule] = useState<RaceEvent[]>([]);
  const [selectedGP, setSelectedGP] = useState('');
  const [selectedSession, setSelectedSession] = useState('R');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // The schedule's race_name (e.g. "Dutch Grand Prix") isn't what results
  // are keyed by — ingestion strips " Grand Prix" (e.g. "Dutch"), so that's
  // the token that has to be sent to the backend.
  const gpToken = (raceName: string) => raceName.replace(' Grand Prix', '').trim();

  useEffect(() => {
    backendApi.getRaceSchedule(selectedYear)
      .then((events) => {
        const list = Array.isArray(events) ? events : [];
        setSchedule(list);
        if (list.length) setSelectedGP(gpToken(list[0].race_name));
      })
      .catch(() => setSchedule([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedYear]);

  useEffect(() => {
    if (selectedGP) loadRaceResults();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedYear, selectedGP, selectedSession]);

  const loadRaceResults = async () => {
    setIsLoading(true);
    setError(null);
    setNotFound(false);

    try {
      const results = await backendApi.getRaceResults(selectedYear, selectedGP, selectedSession);

      // Backend returns a flat array; normalise into the expected shape
      const normalized: RaceResultsData = Array.isArray(results)
        ? { year: selectedYear, gp: selectedGP, session: selectedSession, results }
        : results;

      if ((normalized as any).error) {
        throw new Error((normalized as any).error);
      }

      setRaceData(normalized);
      setLastUpdated(new Date());
    } catch (err: any) {
      if (String(err?.message || '').includes('404')) {
        setNotFound(true);
        setRaceData(null);
      } else {
        console.error('Error loading race results:', err);
        setError(err instanceof Error ? err.message : 'Failed to load race results');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const refreshData = () => {
    loadRaceResults();
  };

  const getTeamColor = (teamColor: string): string => {
    return `#${teamColor}`;
  };

  const formatTime = (time: number): string => {
    if (isNaN(time) || time === 0) return 'Unavailable';
    
    const minutes = Math.floor(time / 60);
    const seconds = (time % 60).toFixed(3);
    return `${minutes}:${seconds.padStart(6, '0')}`;
  };

  const getPositionColor = (position: string): string => {
    const pos = parseInt(position);
    if (pos === 1) return 'text-yellow-500';
    if (pos === 2) return 'text-gray-400';
    if (pos === 3) return 'text-amber-600';
    if (pos <= 10) return 'text-green-500';
    return 'text-gray-500';
  };

  const getPointsColor = (points: string): string => {
    const pts = parseFloat(points);
    if (pts > 0) return 'text-green-500';
    return 'text-gray-500';
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-carbon-black text-pure-white p-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <RefreshCw className="w-8 h-8 animate-spin text-racing-red mx-auto mb-4" />
              <p className="text-lg">Loading race results...</p>
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
            <h2 className="text-2xl font-bold mb-4">Error Loading Race Results</h2>
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
          <div className="mb-6">
            <h1 className="text-4xl font-racing text-racing-red mb-2">
              Race Results
            </h1>
            <p className="text-gray-400">
              Detailed race classification and lap data
            </p>
          </div>

          {/* Filters */}
          <div className="flex flex-wrap gap-4 mb-6">
            <div className="flex items-center space-x-2">
              <MapPin className="w-5 h-5 text-racing-red" />
              <select
                value={selectedGP}
                onChange={(e) => setSelectedGP(e.target.value)}
                className="bg-gray-800 text-pure-white px-3 py-2 rounded-lg border border-gray-600 focus:border-racing-red focus:outline-none"
              >
                {schedule.length === 0 && <option value="">No schedule for {selectedYear}</option>}
                {schedule.map(r => (
                  <option key={r.round} value={gpToken(r.race_name)}>
                    Round {r.round} — {r.race_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center space-x-2 relative">
              <Clock className="w-5 h-5 text-racing-red" />
              <div className="relative">
                <select
                  value={selectedSession}
                  onChange={(e) => setSelectedSession(e.target.value)}
                  className="appearance-none bg-gray-800 text-pure-white pl-3 pr-9 py-2 rounded-lg border border-gray-600 focus:border-racing-red focus:outline-none"
                >
                  {SESSIONS.map(s => (
                    <option key={s.id} value={s.id}>{s.label}</option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>
            </div>
          </div>

          {lastUpdated && (
            <p className="text-sm text-gray-400">
              Last updated: {lastUpdated.toLocaleTimeString()}
            </p>
          )}
        </motion.div>

        {/* No data for this session (e.g. Sprint filter on a non-sprint weekend) */}
        {notFound && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center py-16">
            <p className="text-gray-500">
              No {SESSIONS.find(s => s.id === selectedSession)?.label.toLowerCase()} results for this race.
            </p>
          </motion.div>
        )}

        {/* Race Results */}
        {raceData && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="bg-gray-900 rounded-xl p-6 shadow-2xl"
          >
            <div className="mb-6">
              <h2 className="text-2xl font-bold text-racing-red mb-2">
                {selectedYear} {selectedGP} Grand Prix — {SESSIONS.find(s => s.id === raceData.session)?.label ?? raceData.session}
              </h2>
              <div className="flex items-center space-x-6 text-sm text-gray-400">
                <div className="flex items-center space-x-2">
                  <Flag className="w-4 h-4" />
                  <span>{raceData.results.length} drivers</span>
                </div>
              </div>
            </div>

            {/* Results Table */}
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Pos</th>
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Driver</th>
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Team</th>
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Grid</th>
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Time</th>
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Laps</th>
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Points</th>
                    <th className="text-left py-3 px-4 font-semibold text-racing-red">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {raceData.results.map((result, index) => (
                    <motion.tr
                      key={result.DriverId}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.05 }}
                      className="border-b border-gray-800 hover:bg-gray-800 transition-colors"
                    >
                      <td className="py-4 px-4">
                        <span className={`text-2xl font-bold ${getPositionColor(result.Position)}`}>
                          {result.ClassifiedPosition}
                        </span>
                      </td>
                      <td className="py-4 px-4">
                        <div className="flex items-center space-x-3">
                          <div className="w-10 h-10 rounded-full overflow-hidden">
                            <img
                              src={result.HeadshotUrl}
                              alt={result.FullName}
                              className="w-full h-full object-cover"
                              onError={(e) => {
                                const target = e.target as HTMLImageElement;
                                target.style.display = 'none';
                              }}
                            />
                          </div>
                          <div>
                            <div className="font-semibold text-pure-white">
                              {result.FullName}
                            </div>
                            <div className="text-sm text-gray-400">
                              #{result.DriverNumber} • {result.CountryCode}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="py-4 px-4">
                        <div className="flex items-center space-x-2">
                          <div
                            className="w-4 h-4 rounded"
                            style={{ backgroundColor: getTeamColor(result.TeamColor) }}
                          />
                          <span className="text-pure-white">{result.TeamName}</span>
                        </div>
                      </td>
                      <td className="py-4 px-4 text-pure-white">
                        {result.GridPosition}
                      </td>
                      <td className="py-4 px-4 text-pure-white">
                        {formatTime(result.Time)}
                      </td>
                      <td className="py-4 px-4 text-pure-white">
                        {result.Laps}
                      </td>
                      <td className="py-4 px-4">
                        <span className={`font-bold ${getPointsColor(result.Points)}`}>
                          {result.Points}
                        </span>
                      </td>
                      <td className="py-4 px-4">
                        <span className={`px-2 py-1 rounded text-xs ${
                          result.Status === 'Finished' 
                            ? 'bg-green-900 text-green-300' 
                            : 'bg-gray-700 text-gray-300'
                        }`}>
                          {result.Status}
                        </span>
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
};

export default RaceResults;
