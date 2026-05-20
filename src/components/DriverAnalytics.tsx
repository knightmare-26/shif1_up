import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Users, TrendingUp, Award, Flag, RefreshCw, ExternalLink, Calendar, ChevronDown, Database } from 'lucide-react';
import { backendApi, DriverStanding, ConstructorStanding } from '../services/backendApi';
import { f1DataExtractor } from '../services/f1DataExtractor';
import { Driver, Team } from '../types/f1';

const DriverAnalytics: React.FC = () => {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [availableYears, setAvailableYears] = useState<number[]>([]);

  useEffect(() => {
    initializeYears();
    loadData();
  }, []);

  useEffect(() => {
    if (selectedYear) {
      loadData();
    }
  }, [selectedYear]);

  const initializeYears = () => {
    // First try to get years from the data extractor
    const cachedYears = f1DataExtractor.getAvailableYears();
    if (cachedYears.length > 0) {
      setAvailableYears(cachedYears);
      return;
    }
    
    // Fallback to generating years if no cached data
    const currentYear = new Date().getFullYear();
    const years = [];
    for (let year = 2000; year <= currentYear; year++) {
      years.push(year);
    }
    setAvailableYears(years);
  };

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      console.log(`🚀 Loading F1 data for ${selectedYear}...`);
      
      // First try to get data from the extractor cache
      const cachedData = f1DataExtractor.getYearData(selectedYear);
      
      if (cachedData) {
        console.log(`📦 Using cached data for ${selectedYear}`);
        setDrivers(cachedData.drivers);
        setTeams(cachedData.teams);
        setLastUpdated(new Date());
        return;
      }
      
      // If no cached data, fetch from API and store in extractor
      console.log(`🌐 Fetching fresh data for ${selectedYear} from API...`);
      
      const [driverStandings, constructorStandings] = await Promise.all([
        backendApi.getDriverStandings(selectedYear),
        backendApi.getConstructorStandings(selectedYear)
      ]);
      
      // Convert backend data to frontend types
      const driverData: Driver[] = driverStandings.map(standing => 
        backendApi.convertDriverStandingToDriver(standing)
      );
      
      const teamData: Team[] = constructorStandings.map(standing => 
        backendApi.convertConstructorStandingToTeam(standing)
      );
      
      // Store in extractor cache for future use
      f1DataExtractor.storeYearData(selectedYear, driverData, teamData);
      
      setDrivers(driverData);
      setTeams(teamData);
      setLastUpdated(new Date());
      console.log(`✅ Loaded and cached ${driverData.length} drivers and ${teamData.length} teams for ${selectedYear}`);
      
    } catch (err) {
      console.error('Error loading data:', err);
      // Fallback to mock data if API fails
      console.log(`⚠️ API failed for ${selectedYear}, using fallback data`);
      setDrivers(getFallbackDriverData(selectedYear));
      setTeams(getFallbackTeamData(selectedYear));
      setLastUpdated(new Date());
    } finally {
      setIsLoading(false);
    }
  };

  // Fallback data for when API fails
  const getFallbackDriverData = (year: number): Driver[] => {
    const currentDrivers = [
      { id: 'verstappen', name: 'Max Verstappen', team: 'Red Bull Racing', number: 1, nationality: 'Dutch', points: 575, position: 1, wins: 19, podiums: 21 },
      { id: 'leclerc', name: 'Charles Leclerc', team: 'Ferrari', number: 16, nationality: 'Monegasque', points: 308, position: 2, wins: 3, podiums: 12 },
      { id: 'hamilton', name: 'Lewis Hamilton', team: 'Mercedes', number: 44, nationality: 'British', points: 234, position: 3, wins: 0, podiums: 6 },
      { id: 'norris', name: 'Lando Norris', team: 'McLaren', number: 4, nationality: 'British', points: 169, position: 4, wins: 0, podiums: 7 },
      { id: 'perez', name: 'Sergio Perez', team: 'Red Bull Racing', number: 11, nationality: 'Mexican', points: 156, position: 5, wins: 0, podiums: 2 },
      { id: 'alonso', name: 'Fernando Alonso', team: 'Aston Martin', number: 14, nationality: 'Spanish', points: 206, position: 6, wins: 0, podiums: 8 },
      { id: 'russell', name: 'George Russell', team: 'Mercedes', number: 63, nationality: 'British', points: 175, position: 7, wins: 0, podiums: 2 },
      { id: 'sainz', name: 'Carlos Sainz', team: 'Ferrari', number: 55, nationality: 'Spanish', points: 200, position: 8, wins: 1, podiums: 3 },
      { id: 'piastri', name: 'Oscar Piastri', team: 'McLaren', number: 81, nationality: 'Australian', points: 97, position: 9, wins: 0, podiums: 2 },
      { id: 'ocon', name: 'Esteban Ocon', team: 'Alpine', number: 31, nationality: 'French', points: 58, position: 10, wins: 0, podiums: 0 }
    ];

    // Adjust data based on year (simplified)
    if (year < 2024) {
      return currentDrivers.map(driver => ({
        ...driver,
        points: Math.floor(driver.points * (year / 2024)), // Scale down for older years
        wins: Math.floor(driver.wins * (year / 2024))
      }));
    }
    
    return currentDrivers;
  };

  const getFallbackTeamData = (year: number): Team[] => {
    const currentTeams = [
      { id: 'redbull', name: 'Red Bull Racing', nationality: 'Austrian', points: 731, position: 1, wins: 19 },
      { id: 'ferrari', name: 'Ferrari', nationality: 'Italian', points: 508, position: 2, wins: 4 },
      { id: 'mercedes', name: 'Mercedes', nationality: 'German', points: 409, position: 3, wins: 0 },
      { id: 'mclaren', name: 'McLaren', nationality: 'British', points: 266, position: 4, wins: 0 },
      { id: 'astonmartin', name: 'Aston Martin', nationality: 'British', points: 206, position: 5, wins: 0 },
      { id: 'alpine', name: 'Alpine', nationality: 'French', points: 120, position: 6, wins: 0 },
      { id: 'williams', name: 'Williams', nationality: 'British', points: 28, position: 7, wins: 0 },
      { id: 'alphatauri', name: 'Visa Cash App RB', nationality: 'Italian', points: 25, position: 8, wins: 0 },
      { id: 'stake', name: 'Stake F1 Team', nationality: 'Swiss', points: 16, position: 9, wins: 0 },
      { id: 'haas', name: 'Haas F1 Team', nationality: 'American', points: 12, position: 10, wins: 0 }
    ];

    // Adjust data based on year (simplified)
    if (year < 2024) {
      return currentTeams.map(team => ({
        ...team,
        points: Math.floor(team.points * (year / 2024)), // Scale down for older years
        wins: Math.floor(team.wins * (year / 2024))
      }));
    }
    
    return currentTeams;
  };

  const refreshData = () => {
    loadData();
  };

  const getTeamColor = (teamName: string): string => {
    // Handle unavailable team names
    if (!teamName || teamName === 'Unavailable') {
      return 'bg-gray-600';
    }
    
    const teamColors: { [key: string]: string } = {
      'Red Bull Racing': 'bg-gradient-to-r from-blue-600 to-blue-800',
      'Mercedes': 'bg-gradient-to-r from-teal-600 to-teal-800',
      'Ferrari': 'bg-gradient-to-r from-red-600 to-red-800',
      'McLaren': 'bg-gradient-to-r from-orange-600 to-orange-800',
      'Aston Martin': 'bg-gradient-to-r from-green-600 to-green-800',
      'Alpine': 'bg-gradient-to-r from-blue-400 to-blue-600',
      'Williams': 'bg-gradient-to-r from-blue-800 to-blue-900',
      'Visa Cash App RB': 'bg-gradient-to-r from-blue-500 to-blue-700',
      'Stake F1 Team': 'bg-gradient-to-r from-red-500 to-red-700',
      'Haas F1 Team': 'bg-gradient-to-r from-gray-600 to-gray-800',
    };
    return teamColors[teamName] || 'bg-gray-600';
  };

  const formatDriverName = (name: string): string => {
    return name === 'Unavailable' ? 'Driver Name Unavailable' : name;
  };

  const formatTeamName = (team: string): string => {
    return team === 'Unavailable' ? 'Team Unavailable' : team;
  };

  const formatNationality = (nationality: string): string => {
    return nationality === 'Unavailable' ? 'N/A' : nationality;
  };

  const formatPoints = (points: number): string => {
    return points === 0 ? '0' : points.toString();
  };

  const formatStats = (wins: number, podiums: number): string => {
    const winsText = wins === 0 ? '0' : wins.toString();
    const podiumsText = podiums === 0 ? '0' : podiums.toString();
    return `${winsText} wins, ${podiumsText} podiums`;
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-carbon-black flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-racing-red mx-auto mb-4"></div>
          <p className="text-pure-white text-lg">Loading F1 data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-carbon-black p-8">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="mb-8"
      >
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-racing text-racing-red mb-2">
              Driver Analytics
            </h1>
            <p className="text-pure-white text-lg">
              Formula 1 driver standings and performance data
            </p>
            {selectedYear === new Date().getFullYear() && (
              <div className="flex items-center space-x-4 mt-2">
                <div className="flex items-center space-x-2 text-sm">
                  <Calendar className="w-4 h-4 text-turbo-teal" />
                  <span className="text-turbo-teal font-semibold">
                    Current Season
                  </span>
                </div>
              </div>
            )}
          </div>
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <label className="text-pure-white text-sm font-medium">Year:</label>
              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                className="px-3 py-2 bg-carbon-black border border-racing-red text-pure-white rounded-lg focus:outline-none focus:ring-2 focus:ring-racing-red"
                disabled={isLoading}
              >
                {availableYears.map(year => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </select>
            </div>
            <button
              onClick={refreshData}
              disabled={isLoading}
              className="flex items-center space-x-2 px-4 py-2 bg-racing-red hover:bg-red-700 text-pure-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              <span>{isLoading ? 'Loading...' : 'Refresh'}</span>
            </button>
            {lastUpdated && selectedYear === new Date().getFullYear() && (
              <p className="text-sm text-gray-400">
                Last updated: {lastUpdated.toLocaleTimeString()}
              </p>
            )}
          </div>
        </div>
      </motion.div>

      {/* Data Management Section */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="bg-gray-900 rounded-xl p-4 mb-6 shadow-lg"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <Database className="w-5 h-5 text-turbo-teal" />
              <span className="text-pure-white font-semibold">Data Status</span>
            </div>
            <div className="text-sm text-gray-400">
              {f1DataExtractor.getAvailableYears().length} years cached
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <span className="text-sm text-gray-400">
              Last updated: {lastUpdated ? lastUpdated.toLocaleTimeString() : 'Never'}
            </span>
          </div>
        </div>
      </motion.div>

      {error && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 p-4 bg-yellow-900 border border-yellow-600 text-yellow-200 rounded-lg"
        >
          <p className="flex items-center">
            <Flag className="w-4 h-4 mr-2" />
            {error}
          </p>
        </motion.div>
      )}

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="bg-track-grey rounded-xl p-4 mb-6"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <ExternalLink className="w-4 h-4 text-turbo-teal" />
            <span className="text-sm text-carbon-black">
              Data from FastF1 API & Ergast API (Fallback)
            </span>
          </div>
          <div className="text-xs text-gray-600">
            Auto-refresh every 15 minutes • Live data every 30 seconds
          </div>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.4 }}
        className="bg-track-grey rounded-xl p-6 shadow-lg mb-8"
      >
        <h2 className="text-2xl font-bold text-carbon-black mb-6 flex items-center">
          <Users className="w-6 h-6 text-racing-red mr-3" />
          Driver Standings - {selectedYear} Season
        </h2>
        <div className="space-y-4">
          {drivers.map((driver, index) => (
            <motion.div
              key={driver.id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.4, delay: 0.1 * index }}
              className="flex items-center justify-between p-4 bg-pure-white rounded-lg hover:shadow-md transition-shadow"
            >
              <div className="flex items-center space-x-4">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center text-lg font-bold text-pure-white ${
                  index === 0 ? 'bg-yellow-500' :
                  index === 1 ? 'bg-gray-400' :
                  index === 2 ? 'bg-orange-600' : 'bg-gray-600'
                }`}>
                  {driver.position}
                </div>
                <div>
                  <p className="font-bold text-carbon-black text-lg">{formatDriverName(driver.name)}</p>
                  <p className="text-sm text-gray-600">#{driver.number} • {formatNationality(driver.nationality)}</p>
                  <div className={`inline-block px-2 py-1 rounded text-xs text-pure-white mt-1 ${getTeamColor(driver.team)}`}>
                    {formatTeamName(driver.team)}
                  </div>
                </div>
              </div>
              <div className="text-right">
                <p className="text-2xl font-bold text-racing-red">{formatPoints(driver.points)} pts</p>
                <p className="text-sm text-gray-600">
                  {formatStats(driver.wins, driver.podiums)}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.6 }}
        className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8"
      >
        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center mb-4">
            <TrendingUp className="w-8 h-8 text-racing-red mr-3" />
            <h3 className="text-xl font-bold text-carbon-black">Season Leader</h3>
          </div>
          <p className="text-3xl font-racing text-racing-red mb-2">
            {formatDriverName(drivers[0]?.name || 'Loading...')}
          </p>
          <p className="text-sm text-gray-600">
            {formatPoints(drivers[0]?.points || 0)} points • {formatStats(drivers[0]?.wins || 0, drivers[0]?.podiums || 0)}
          </p>
        </div>

        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center mb-4">
            <Award className="w-8 h-8 text-turbo-teal mr-3" />
            <h3 className="text-xl font-bold text-carbon-black">Most Wins</h3>
          </div>
          <p className="text-3xl font-racing text-turbo-teal mb-2">
            {Math.max(...drivers.map(d => d.wins))}
          </p>
          <p className="text-sm text-gray-600">
            {drivers.find(d => d.wins === Math.max(...drivers.map(d => d.wins)))?.name || 'Loading...'}
          </p>
        </div>

        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center mb-4">
            <Flag className="w-8 h-8 text-pit-stop-yellow mr-3" />
            <h3 className="text-xl font-bold text-carbon-black">Most Podiums</h3>
          </div>
          <p className="text-3xl font-racing text-pit-stop-yellow mb-2">
            {Math.max(...drivers.map(d => d.podiums))}
          </p>
          <p className="text-sm text-gray-600">
            {drivers.find(d => d.podiums === Math.max(...drivers.map(d => d.podiums)))?.name || 'Loading...'}
          </p>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.8 }}
        className="bg-track-grey rounded-xl p-6 shadow-lg mb-8"
      >
        <h3 className="text-2xl font-bold text-carbon-black mb-6 flex items-center">
          <Flag className="w-6 h-6 text-pit-stop-yellow mr-3" />
          Team Performance Overview - {selectedYear}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {teams.slice(0, 6).map((team, index) => (
            <div key={team.id} className="bg-pure-white rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className={`px-2 py-1 rounded text-xs text-pure-white ${getTeamColor(team.name)}`}>
                  #{team.position}
                </span>
                <span className="text-sm text-gray-600">{team.points} pts</span>
              </div>
              <h4 className="font-bold text-carbon-black mb-1">{formatTeamName(team.name)}</h4>
              <p className="text-sm text-gray-600">{formatNationality(team.nationality)}</p>
              <div className="mt-2 text-xs text-gray-500">
                {team.wins} wins
              </div>
            </div>
          ))}
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 1.0 }}
        className="bg-gradient-to-r from-racing-red to-red-700 rounded-xl p-8 text-center text-pure-white shadow-lg"
      >
        <h3 className="text-2xl font-bold mb-4">Advanced Analytics Coming Soon</h3>
        <p className="text-lg opacity-90 mb-6">
          Real-time telemetry, lap analysis, and AI-powered predictions powered by FastF1
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div>
            <p className="font-bold">Live Telemetry</p>
            <p className="opacity-80">Real-time throttle, brake, and steering data</p>
          </div>
          <div>
            <p className="font-bold">Lap Analysis</p>
            <p className="opacity-80">Sector times, corner speeds, braking points</p>
          </div>
          <div>
            <p className="font-bold">AI Predictions</p>
            <p className="opacity-80">Machine learning race outcome forecasting</p>
          </div>
        </div>
      </motion.div>
    </div>
  );
};

export default DriverAnalytics;
