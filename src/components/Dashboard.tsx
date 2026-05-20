import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import { backendApi, DriverStanding, RaceEvent } from '../services/backendApi';
import { BarChart3, TrendingUp, Calendar, Users, MapPin, Flag, RefreshCw } from 'lucide-react';

const Dashboard: React.FC = () => {
  const { user } = useAuth();
  const year = new Date().getFullYear();

  const [drivers, setDrivers]       = useState<DriverStanding[]>([]);
  const [races, setRaces]           = useState<RaceEvent[]>([]);
  const [loading, setLoading]       = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [d, r] = await Promise.all([
          backendApi.getDriverStandings(year),
          backendApi.getRaceSchedule(year),
        ]);
        setDrivers(Array.isArray(d) ? d : []);
        setRaces(Array.isArray(r) ? r : []);
      } catch (e) {
        console.error('Dashboard load error', e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [year]);

  if (!user) {
    return (
      <div className="min-h-screen bg-carbon-black flex items-center justify-center">
        <div className="text-pure-white">Loading...</div>
      </div>
    );
  }

  // Derived stats
  const leader      = drivers[0];
  const nextRace    = races.find(r => new Date(r.date) >= new Date());
  const favName     = user.preferences.favoriteDriver?.toLowerCase() ?? '';
  const favDriver   = drivers.find(d =>
    d.driver_name.toLowerCase().includes(favName) ||
    d.driver_id.toLowerCase().includes(favName)
  );
  const recentRaces = [...races]
    .filter(r => new Date(r.date) < new Date())
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
    .slice(0, 3);

  return (
    <div className="min-h-screen bg-carbon-black p-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="mb-8"
      >
        <h1 className="text-4xl font-racing text-racing-red mb-2">F1 Dashboard</h1>
        <p className="text-pure-white text-lg">
          Your personalized Formula 1 analytics overview
        </p>
      </motion.div>

      {/* Stats Grid */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8"
      >
        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Next Race</p>
              {loading ? (
                <RefreshCw className="w-5 h-5 animate-spin text-gray-400 mt-1" />
              ) : (
                <p className="text-2xl font-bold text-carbon-black">
                  {nextRace ? `${nextRace.race_name.replace(' Grand Prix', '')} GP` : '—'}
                </p>
              )}
              {nextRace && (
                <p className="text-xs text-gray-500 mt-1">{nextRace.date}</p>
              )}
            </div>
            <Calendar className="w-8 h-8 text-racing-red" />
          </div>
        </div>

        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Championship Leader</p>
              {loading ? (
                <RefreshCw className="w-5 h-5 animate-spin text-gray-400 mt-1" />
              ) : (
                <>
                  <p className="text-lg font-bold text-carbon-black leading-tight">
                    {leader?.driver_name ?? '—'}
                  </p>
                  <p className="text-sm text-gray-500">{leader?.points ?? 0} pts</p>
                </>
              )}
            </div>
            <Users className="w-8 h-8 text-turbo-teal" />
          </div>
        </div>

        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Constructors Leader</p>
              {loading ? (
                <RefreshCw className="w-5 h-5 animate-spin text-gray-400 mt-1" />
              ) : (
                <>
                  <p className="text-lg font-bold text-carbon-black leading-tight">
                    {leader?.constructor ?? '—'}
                  </p>
                </>
              )}
            </div>
            <Flag className="w-8 h-8 text-pit-stop-yellow" />
          </div>
        </div>

        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Season Wins (Leader)</p>
              {loading ? (
                <RefreshCw className="w-5 h-5 animate-spin text-gray-400 mt-1" />
              ) : (
                <p className="text-2xl font-bold text-carbon-black">{leader?.wins ?? '—'}</p>
              )}
            </div>
            <TrendingUp className="w-8 h-8 text-racing-red" />
          </div>
        </div>
      </motion.div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Favorite Driver */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="bg-track-grey rounded-xl p-6 shadow-lg"
        >
          <h3 className="text-xl font-bold text-carbon-black mb-4 flex items-center">
            <Users className="w-5 h-5 text-racing-red mr-2" />
            {user.preferences.favoriteDriver || 'Your Driver'} — {year} Season
          </h3>
          {loading ? (
            <div className="flex items-center justify-center h-24">
              <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : favDriver ? (
            <div className="space-y-4">
              {[
                ['Championship Position', `P${favDriver.position}`],
                ['Points', String(favDriver.points)],
                ['Wins', String(favDriver.wins)],
                ['Team', favDriver.constructor],
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between items-center p-3 bg-pure-white rounded-lg">
                  <span className="text-carbon-black">{label}</span>
                  <span className="font-bold text-racing-red">{value}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">
              {favName
                ? `No standings data found for "${user.preferences.favoriteDriver}".`
                : 'Set a favourite driver in your profile to see their stats here.'}
            </p>
          )}
        </motion.div>

        {/* Next Race */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, delay: 0.6 }}
          className="bg-track-grey rounded-xl p-6 shadow-lg"
        >
          <h3 className="text-xl font-bold text-carbon-black mb-4 flex items-center">
            <MapPin className="w-5 h-5 text-turbo-teal mr-2" />
            Next Race
          </h3>
          {loading ? (
            <div className="flex items-center justify-center h-24">
              <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : nextRace ? (
            <div className="space-y-4">
              {[
                ['Race', nextRace.race_name],
                ['Circuit', nextRace.circuit_name],
                ['Country', nextRace.country],
                ['Date', nextRace.date],
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between items-center p-3 bg-pure-white rounded-lg">
                  <span className="text-carbon-black">{label}</span>
                  <span className="font-bold text-turbo-teal">{value}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">No upcoming races found.</p>
          )}
        </motion.div>
      </div>

      {/* Recent Results */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.8 }}
        className="mt-8 bg-track-grey rounded-xl p-6 shadow-lg"
      >
        <h3 className="text-xl font-bold text-carbon-black mb-4 flex items-center">
          <BarChart3 className="w-5 h-5 text-racing-red mr-2" />
          Recent Races — {year}
        </h3>
        {loading ? (
          <div className="flex items-center justify-center h-16">
            <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
          </div>
        ) : recentRaces.length > 0 ? (
          <div className="space-y-3">
            {recentRaces.map(race => (
              <div key={race.round} className="flex items-center justify-between p-4 bg-pure-white rounded-lg">
                <div className="flex items-center space-x-4">
                  <span className="text-2xl font-bold text-racing-red">R{race.round}</span>
                  <div>
                    <p className="font-medium text-carbon-black">{race.race_name}</p>
                    <p className="text-sm text-gray-600">{race.location}, {race.country}</p>
                  </div>
                </div>
                <span className="text-sm text-gray-500">{race.date}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-gray-500 text-sm">No completed races yet this season.</p>
        )}
      </motion.div>
    </div>
  );
};

export default Dashboard;
