import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { MapPin, Calendar, Clock, Flag, RefreshCw, TrendingUp } from 'lucide-react';
import { backendApi, RaceEvent } from '../services/backendApi';

const TrackAnalytics: React.FC = () => {
  const [raceSchedule, setRaceSchedule] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
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
      const raceEvents = await backendApi.getRaceSchedule(selectedYear);

      const schedule = raceEvents.map(event => ({
        round: event.round,
        raceName: event.race_name,
        circuitName: event.circuit_name,
        country: event.country,
        location: event.location,
        date: event.date,
        time: event.time,
        url: event.url
      }));
      
      setRaceSchedule(schedule);
    } catch (err) {
      setRaceSchedule(getFallbackRaceSchedule(selectedYear));
    } finally {
      setIsLoading(false);
    }
  };

  // Fallback data for when API fails
  const getFallbackRaceSchedule = (year: number): any[] => {
    const currentSchedule = [
      { round: 1, raceName: 'Bahrain Grand Prix', circuitName: 'Bahrain International Circuit', country: 'Bahrain', location: 'Sakhir', date: '2024-03-02', time: '15:00:00Z' },
      { round: 2, raceName: 'Saudi Arabian Grand Prix', circuitName: 'Jeddah Corniche Circuit', country: 'Saudi Arabia', location: 'Jeddah', date: '2024-03-09', time: '20:00:00Z' },
      { round: 3, raceName: 'Australian Grand Prix', circuitName: 'Albert Park Circuit', country: 'Australia', location: 'Melbourne', date: '2024-03-24', time: '05:00:00Z' },
      { round: 4, raceName: 'Japanese Grand Prix', circuitName: 'Suzuka International Racing Course', country: 'Japan', location: 'Suzuka', date: '2024-04-07', time: '06:00:00Z' },
      { round: 5, raceName: 'Chinese Grand Prix', circuitName: 'Shanghai International Circuit', country: 'China', location: 'Shanghai', date: '2024-04-21', time: '08:00:00Z' },
      { round: 6, raceName: 'Miami Grand Prix', circuitName: 'Miami International Autodrome', country: 'USA', location: 'Miami', date: '2024-05-05', time: '21:00:00Z' },
      { round: 7, raceName: 'Emilia Romagna Grand Prix', circuitName: 'Autodromo Enzo e Dino Ferrari', country: 'Italy', location: 'Imola', date: '2024-05-19', time: '15:00:00Z' },
      { round: 8, raceName: 'Monaco Grand Prix', circuitName: 'Circuit de Monaco', country: 'Monaco', location: 'Monte Carlo', date: '2024-05-26', time: '15:00:00Z' },
      { round: 9, raceName: 'Canadian Grand Prix', circuitName: 'Circuit Gilles Villeneuve', country: 'Canada', location: 'Montreal', date: '2024-06-09', time: '20:00:00Z' },
      { round: 10, raceName: 'Spanish Grand Prix', circuitName: 'Circuit de Barcelona-Catalunya', country: 'Spain', location: 'Montmeló', date: '2024-06-23', time: '15:00:00Z' },
      { round: 11, raceName: 'Austrian Grand Prix', circuitName: 'Red Bull Ring', country: 'Austria', location: 'Spielberg', date: '2024-06-30', time: '15:00:00Z' },
      { round: 12, raceName: 'British Grand Prix', circuitName: 'Silverstone Circuit', country: 'UK', location: 'Silverstone', date: '2024-07-07', time: '15:00:00Z' },
      { round: 13, raceName: 'Hungarian Grand Prix', circuitName: 'Hungaroring', country: 'Hungary', location: 'Mogyoród', date: '2024-07-21', time: '15:00:00Z' },
      { round: 14, raceName: 'Belgian Grand Prix', circuitName: 'Circuit de Spa-Francorchamps', country: 'Belgium', location: 'Stavelot', date: '2024-07-28', time: '15:00:00Z' },
      { round: 15, raceName: 'Dutch Grand Prix', circuitName: 'Circuit Zandvoort', country: 'Netherlands', location: 'Zandvoort', date: '2024-08-25', time: '15:00:00Z' },
      { round: 16, raceName: 'Italian Grand Prix', circuitName: 'Autodromo Nazionale Monza', country: 'Italy', location: 'Monza', date: '2024-09-01', time: '15:00:00Z' },
      { round: 17, raceName: 'Azerbaijan Grand Prix', circuitName: 'Baku City Circuit', country: 'Azerbaijan', location: 'Baku', date: '2024-09-15', time: '13:00:00Z' },
      { round: 18, raceName: 'Singapore Grand Prix', circuitName: 'Marina Bay Street Circuit', country: 'Singapore', location: 'Marina Bay', date: '2024-09-22', time: '14:00:00Z' },
      { round: 19, raceName: 'United States Grand Prix', circuitName: 'Circuit of the Americas', country: 'USA', location: 'Austin', date: '2024-10-20', time: '21:00:00Z' },
      { round: 20, raceName: 'Mexican Grand Prix', circuitName: 'Autódromo Hermanos Rodríguez', country: 'Mexico', location: 'Mexico City', date: '2024-10-27', time: '21:00:00Z' },
      { round: 21, raceName: 'Brazilian Grand Prix', circuitName: 'Autódromo José Carlos Pace', country: 'Brazil', location: 'São Paulo', date: '2024-11-03', time: '18:00:00Z' },
      { round: 22, raceName: 'Las Vegas Grand Prix', circuitName: 'Las Vegas Strip Circuit', country: 'USA', location: 'Las Vegas', date: '2024-11-23', time: '06:00:00Z' },
      { round: 23, raceName: 'Qatar Grand Prix', circuitName: 'Lusail International Circuit', country: 'Qatar', location: 'Lusail', date: '2024-12-01', time: '17:00:00Z' },
      { round: 24, raceName: 'Abu Dhabi Grand Prix', circuitName: 'Yas Marina Circuit', country: 'UAE', location: 'Abu Dhabi', date: '2024-12-08', time: '17:00:00Z' }
    ];

    // Adjust data based on year (simplified - just change the year in dates)
    return currentSchedule.map(race => ({
      ...race,
      date: race.date.replace('2024', year.toString())
    }));
  };

  const refreshData = () => {
    loadData();
  };

  // Helper functions for track information
  const getTrackLength = (trackName: string): string => {
    if (!trackName || trackName === 'Unavailable') {
      return 'Track Length Unavailable';
    }
    
    const trackLengths: { [key: string]: string } = {
      'Bahrain International Circuit': '5.412 km',
      'Jeddah Corniche Circuit': '6.174 km',
      'Albert Park Grand Prix Circuit': '5.278 km',
      'Circuit de Monaco': '3.337 km',
      'Circuit de Barcelona-Catalunya': '4.675 km',
      'Circuit Gilles Villeneuve': '4.361 km',
      'Red Bull Ring': '4.318 km',
      'Silverstone Circuit': '5.891 km',
      'Hungaroring': '4.381 km',
      'Circuit de Spa-Francorchamps': '7.004 km',
      'Circuit Zandvoort': '4.259 km',
      'Monza': '5.793 km',
      'Marina Bay Street Circuit': '5.063 km',
      'Suzuka Circuit': '5.807 km',
      'Circuit of the Americas': '5.513 km',
      'Autódromo Hermanos Rodríguez': '4.304 km',
      'Autódromo José Carlos Pace': '4.309 km',
      'Yas Marina Circuit': '5.281 km',
      'Miami International Autodrome': '5.412 km',
      'Autodromo Enzo e Dino Ferrari': '4.909 km',
      'Losail International Circuit': '5.380 km',
      'Las Vegas Strip Circuit': '6.201 km',
    };
    return trackLengths[trackName] || 'Track Length Unavailable';
  };

  const getTrackCorners = (trackName: string): number => {
    if (!trackName || trackName === 'Unavailable') {
      return 0;
    }
    
    const trackCorners: { [key: string]: number } = {
      'Bahrain International Circuit': 15,
      'Jeddah Corniche Circuit': 27,
      'Albert Park Grand Prix Circuit': 16,
      'Circuit de Monaco': 19,
      'Circuit de Barcelona-Catalunya': 16,
      'Circuit Gilles Villeneuve': 14,
      'Red Bull Ring': 10,
      'Silverstone Circuit': 18,
      'Hungaroring': 14,
      'Circuit de Spa-Francorchamps': 20,
      'Circuit Zandvoort': 14,
      'Monza': 11,
      'Marina Bay Street Circuit': 23,
      'Suzuka Circuit': 18,
      'Circuit of the Americas': 20,
      'Autódromo Hermanos Rodríguez': 17,
      'Autódromo José Carlos Pace': 15,
      'Yas Marina Circuit': 16,
      'Miami International Autodrome': 19,
      'Autodromo Enzo e Dino Ferrari': 19,
      'Losail International Circuit': 16,
      'Las Vegas Strip Circuit': 17,
    };
    return trackCorners[trackName] || 0;
  };

  const getTrackRecord = (trackName: string): { time: string; holder: string; year: number } => {
    if (!trackName || trackName === 'Unavailable') {
      return { time: 'Track Record Unavailable', holder: 'N/A', year: 0 };
    }
    
    const trackRecords: { [key: string]: { time: string; holder: string; year: number } } = {
      'Bahrain International Circuit': { time: '1:31.447', holder: 'Max Verstappen', year: 2024 },
      'Jeddah Corniche Circuit': { time: '1:27.791', holder: 'Lewis Hamilton', year: 2021 },
      'Albert Park Grand Prix Circuit': { time: '1:17.706', holder: 'Charles Leclerc', year: 2022 },
      'Circuit de Monaco': { time: '1:12.909', holder: 'Lewis Hamilton', year: 2019 },
      'Circuit de Barcelona-Catalunya': { time: '1:16.330', holder: 'Max Verstappen', year: 2023 },
      'Circuit Gilles Villeneuve': { time: '1:13.078', holder: 'Valtteri Bottas', year: 2019 },
      'Red Bull Ring': { time: '1:05.619', holder: 'Carlos Sainz', year: 2020 },
      'Silverstone Circuit': { time: '1:26.720', holder: 'Max Verstappen', year: 2023 },
      'Hungaroring': { time: '1:16.627', holder: 'Lewis Hamilton', year: 2020 },
      'Circuit de Spa-Francorchamps': { time: '1:41.252', holder: 'Valtteri Bottas', year: 2018 },
      'Circuit Zandvoort': { time: '1:10.567', holder: 'Max Verstappen', year: 2021 },
      'Monza': { time: '1:18.887', holder: 'Carlos Sainz', year: 2023 },
      'Marina Bay Street Circuit': { time: '1:35.867', holder: 'Lewis Hamilton', year: 2018 },
      'Suzuka Circuit': { time: '1:30.983', holder: 'Max Verstappen', year: 2019 },
      'Circuit of the Americas': { time: '1:34.356', holder: 'Charles Leclerc', year: 2019 },
      'Autódromo Hermanos Rodríguez': { time: '1:14.759', holder: 'Valtteri Bottas', year: 2021 },
      'Autódromo José Carlos Pace': { time: '1:10.540', holder: 'Valtteri Bottas', year: 2018 },
      'Yas Marina Circuit': { time: '1:26.103', holder: 'Max Verstappen', year: 2021 },
      'Miami International Autodrome': { time: '1:29.708', holder: 'Max Verstappen', year: 2023 },
      'Autodromo Enzo e Dino Ferrari': { time: '1:15.484', holder: 'Lewis Hamilton', year: 2020 },
      'Losail International Circuit': { time: '1:24.319', holder: 'Max Verstappen', year: 2021 },
      'Las Vegas Strip Circuit': { time: '1:35.776', holder: 'Oscar Piastri', year: 2023 },
    };
    return trackRecords[trackName] || { time: 'Track Record Unavailable', holder: 'N/A', year: 0 };
  };

  const getNextRace = (): any | null => {
    const now = new Date();
    const upcomingRaces = raceSchedule.filter(race => {
      const raceDate = new Date(race.date);
      return raceDate > now;
    });
    
    if (upcomingRaces.length > 0) {
      return upcomingRaces[0];
    }
    return null;
  };

  const formatRaceName = (name: string): string => {
    return name === 'Unavailable' ? 'Race Name Unavailable' : name;
  };

  const formatCircuitName = (name: string): string => {
    return name === 'Unavailable' ? 'Circuit Name Unavailable' : name;
  };

  const formatCountry = (country: string): string => {
    return country === 'Unavailable' ? 'Country Unavailable' : country;
  };

  const formatDate = (dateString: string): string => {
    if (!dateString || dateString === 'Unavailable') {
      return 'Date Unavailable';
    }
    
    try {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) {
        return 'Invalid Date';
      }
      
      return date.toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      });
    } catch (error) {
      return 'Date Unavailable';
    }
  };

  const formatRound = (round: string | number): string => {
    if (round === 'Unavailable' || round === 0) {
      return 'Round Unavailable';
    }
    return round.toString();
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-carbon-black flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-racing-red mx-auto mb-4"></div>
          <p className="text-pure-white text-lg">Loading race schedule...</p>
        </div>
      </div>
    );
  }

  const nextRace = getNextRace();

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
              Track Analytics
            </h1>
            <p className="text-pure-white text-lg">
              Formula 1 circuit information and race schedule
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


      {nextRace && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="bg-gradient-to-r from-turbo-teal to-blue-600 rounded-xl p-6 mb-8 text-pure-white shadow-lg"
        >
          <h2 className="text-2xl font-bold mb-4 flex items-center">
            <Clock className="w-6 h-6 mr-3" />
            Next Race Information
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <h3 className="text-lg font-semibold mb-2">{nextRace.raceName}</h3>
              <p className="text-sm opacity-90">{nextRace.circuitName}</p>
              <p className="text-sm opacity-90">{nextRace.country}</p>
            </div>
            <div>
              <p className="text-sm opacity-90">Date</p>
              <p className="text-lg font-semibold">{formatDate(nextRace.date)}</p>
              <p className="text-sm opacity-90">Round {nextRace.round}</p>
            </div>
            <div>
              <p className="text-sm opacity-90">Track Details</p>
              <p className="text-lg font-semibold">{getTrackLength(nextRace.circuitName)}</p>
              <p className="text-sm opacity-90">{getTrackCorners(nextRace.circuitName)} corners</p>
            </div>
          </div>
        </motion.div>
      )}

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.6 }}
        className="bg-track-grey rounded-xl p-6 shadow-lg mb-8"
      >
        <h2 className="text-2xl font-bold text-carbon-black mb-6 flex items-center">
          <MapPin className="w-6 h-6 text-racing-red mr-3" />
          {selectedYear} Season Race Schedule
        </h2>
        <div className="space-y-4">
          {raceSchedule.map((race, index) => {
            const trackRecord = getTrackRecord(race.circuitName);
            const isUpcoming = new Date(race.date) > new Date();
            
            return (
              <motion.div
                key={race.round}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.4, delay: 0.1 * index }}
                className={`p-4 rounded-lg transition-all ${
                  isUpcoming 
                    ? 'bg-gradient-to-r from-turbo-teal to-blue-600 text-pure-white' 
                    : 'bg-pure-white hover:shadow-md'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-4">
                    <div className={`w-12 h-12 rounded-full flex items-center justify-center text-lg font-bold ${
                      isUpcoming ? 'bg-pure-white text-turbo-teal' : 'bg-racing-red text-pure-white'
                    }`}>
                      {race.round}
                    </div>
                    <div>
                      <h3 className={`font-bold text-lg ${
                        isUpcoming ? 'text-pure-white' : 'text-carbon-black'
                      }`}>
                        {race.raceName}
                      </h3>
                      <p className={`text-sm ${
                        isUpcoming ? 'text-blue-100' : 'text-gray-600'
                      }`}>
                        {race.circuitName} • {race.country}
                      </p>
                      <p className={`text-sm ${
                        isUpcoming ? 'text-blue-100' : 'text-gray-600'
                      }`}>
                        {formatDate(race.date)}
                      </p>
                    </div>
                  </div>
                  <div className={`text-right ${
                    isUpcoming ? 'text-pure-white' : 'text-carbon-black'
                  }`}>
                    <div className="text-sm opacity-80">Track Record</div>
                    <div className="font-semibold">{trackRecord.time}</div>
                    <div className="text-xs opacity-70">{trackRecord.holder} ({trackRecord.year})</div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.8 }}
        className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8"
      >
        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center mb-4">
            <TrendingUp className="w-8 h-8 text-racing-red mr-3" />
            <h3 className="text-xl font-bold text-carbon-black">Total Races</h3>
          </div>
          <p className="text-3xl font-racing text-racing-red mb-2">
            {raceSchedule.length}
          </p>
          <p className="text-sm text-gray-600">
            {selectedYear} Formula 1 World Championship
          </p>
        </div>

        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center mb-4">
            <MapPin className="w-8 h-8 text-turbo-teal mr-3" />
            <h3 className="text-xl font-bold text-carbon-black">Countries</h3>
          </div>
          <p className="text-3xl font-racing text-turbo-teal mb-2">
            {new Set(raceSchedule.map(race => race.country)).size}
          </p>
          <p className="text-sm text-gray-600">
            Unique host nations this season
          </p>
        </div>

        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center mb-4">
            <Flag className="w-8 h-8 text-pit-stop-yellow mr-3" />
            <h3 className="text-xl font-bold text-carbon-black">Upcoming</h3>
          </div>
          <p className="text-3xl font-racing text-pit-stop-yellow mb-2">
            {raceSchedule.filter(race => new Date(race.date) > new Date()).length}
          </p>
          <p className="text-sm text-gray-600">
            Races remaining this season
          </p>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 1.0 }}
        className="bg-gradient-to-r from-racing-red to-red-700 rounded-xl p-8 text-center text-pure-white shadow-lg"
      >
        <h3 className="text-2xl font-bold mb-4">Advanced Track Analysis Coming Soon</h3>
        <p className="text-lg opacity-90 mb-6">
          Real-time weather data, tire strategies, and AI-powered track performance predictions
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div>
            <p className="font-bold">Weather Integration</p>
            <p className="opacity-80">Real-time weather conditions and forecasts</p>
          </div>
          <div>
            <p className="font-bold">Tire Analysis</p>
            <p className="opacity-80">Optimal tire strategies and wear patterns</p>
          </div>
          <div>
            <p className="font-bold">Performance Metrics</p>
            <p className="opacity-80">Corner speeds, braking points, and sector analysis</p>
          </div>
        </div>
      </motion.div>
    </div>
  );
};

export default TrackAnalytics;
