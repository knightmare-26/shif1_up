import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { backendApi, DriverStanding, ConstructorStanding, RaceEvent } from '../services/backendApi';
import { BarChart3, TrendingUp, Calendar, Users, MapPin, Flag, RefreshCw } from 'lucide-react';
import DriverAnalytics from './DriverAnalytics';
import TrackAnalytics from './TrackAnalytics';

type Tab = 'overview' | 'drivers' | 'teams' | 'tracks';

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'overview', label: 'Overview',  icon: <BarChart3 className="w-4 h-4" /> },
  { id: 'drivers',  label: 'Drivers',   icon: <Users className="w-4 h-4" /> },
  { id: 'teams',    label: 'Teams',     icon: <Flag className="w-4 h-4" /> },
  { id: 'tracks',   label: 'Tracks',    icon: <MapPin className="w-4 h-4" /> },
];

const Dashboard: React.FC = () => {
  const [tab, setTab]           = useState<Tab>('overview');
  const year                    = new Date().getFullYear();
  const [drivers, setDrivers]   = useState<DriverStanding[]>([]);
  const [teams, setTeams]       = useState<ConstructorStanding[]>([]);
  const [races, setRaces]       = useState<RaceEvent[]>([]);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [d, c, r] = await Promise.all([
          backendApi.getDriverStandings(year),
          backendApi.getConstructorStandings(year),
          backendApi.getRaceSchedule(year),
        ]);
        setDrivers(Array.isArray(d) ? d : []);
        setTeams(Array.isArray(c) ? c : []);
        setRaces(Array.isArray(r) ? r : []);
      } catch (e) {
        console.error('Dashboard load error', e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [year]);

  const leader      = drivers[0];
  const teamLeader  = teams[0];
  const nextRace    = races.find(r => new Date(r.date) >= new Date());
  const recentRaces = [...races]
    .filter(r => new Date(r.date) < new Date())
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
    .slice(0, 3);

  return (
    <div className="min-h-screen bg-carbon-black text-white">
      {/* Header */}
      <div className="px-4 sm:px-6 lg:px-8 pt-8 pb-0">
        <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
          <h1 className="text-3xl font-racing text-racing-red mb-1">F1 Dashboard</h1>
          <p className="text-gray-400 text-sm">Formula 1 analytics — {year} season</p>
        </motion.div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-gray-800">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors ${
                tab === t.id
                  ? 'bg-gray-900 text-white border border-b-gray-900 border-gray-800 -mb-px'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {t.icon}{t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      {tab === 'overview' && (
        <div className="px-4 sm:px-6 lg:px-8 py-6">
          {/* Stats Grid */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Next Race</p>
                  {loading ? <RefreshCw className="w-4 h-4 animate-spin text-gray-500 mt-1" /> : (
                    <>
                      <p className="text-lg font-bold text-white mt-1">
                        {nextRace ? `${nextRace.race_name.replace(' Grand Prix', '')} GP` : '—'}
                      </p>
                      {nextRace && <p className="text-xs text-gray-500">{nextRace.date}</p>}
                    </>
                  )}
                </div>
                <Calendar className="w-7 h-7 text-racing-red" />
              </div>
            </div>

            <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Drivers Leader</p>
                  {loading ? <RefreshCw className="w-4 h-4 animate-spin text-gray-500 mt-1" /> : (
                    <>
                      <p className="text-lg font-bold text-white mt-1">{leader?.driver_name ?? '—'}</p>
                      <p className="text-xs text-gray-500">{leader?.points ?? 0} pts</p>
                    </>
                  )}
                </div>
                <Users className="w-7 h-7 text-turbo-teal" />
              </div>
            </div>

            <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Constructors Leader</p>
                  {loading ? <RefreshCw className="w-4 h-4 animate-spin text-gray-500 mt-1" /> : (
                    <>
                      <p className="text-lg font-bold text-white mt-1">{teamLeader?.constructor_name ?? leader?.constructor ?? '—'}</p>
                      <p className="text-xs text-gray-500">{teamLeader?.points ?? '—'} pts</p>
                    </>
                  )}
                </div>
                <Flag className="w-7 h-7 text-pit-stop-yellow" />
              </div>
            </div>

            <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Leader Wins</p>
                  {loading ? <RefreshCw className="w-4 h-4 animate-spin text-gray-500 mt-1" /> : (
                    <p className="text-3xl font-bold text-white mt-1">{leader?.wins ?? '—'}</p>
                  )}
                </div>
                <TrendingUp className="w-7 h-7 text-racing-red" />
              </div>
            </div>
          </motion.div>

          {/* Recent Races + Next Race */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
              className="bg-gray-900 rounded-xl border border-gray-800 p-5">
              <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-racing-red" /> Recent Races
              </h3>
              {loading ? (
                <div className="flex justify-center py-8"><RefreshCw className="w-5 h-5 animate-spin text-gray-500" /></div>
              ) : recentRaces.length > 0 ? (
                <div className="space-y-2">
                  {recentRaces.map(race => (
                    <div key={race.round} className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <span className="text-racing-red font-bold text-sm w-6">R{race.round}</span>
                        <div>
                          <p className="text-white text-sm font-medium">{race.race_name}</p>
                          <p className="text-gray-500 text-xs">{race.country}</p>
                        </div>
                      </div>
                      <span className="text-gray-500 text-xs">{race.date}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-500 text-sm">No completed races yet this season.</p>
              )}
            </motion.div>

            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
              className="bg-gray-900 rounded-xl border border-gray-800 p-5">
              <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
                <MapPin className="w-4 h-4 text-turbo-teal" /> Next Race
              </h3>
              {loading ? (
                <div className="flex justify-center py-8"><RefreshCw className="w-5 h-5 animate-spin text-gray-500" /></div>
              ) : nextRace ? (
                <div className="space-y-2">
                  {[
                    ['Race', nextRace.race_name],
                    ['Circuit', nextRace.circuit_name],
                    ['Country', nextRace.country],
                    ['Date', nextRace.date],
                  ].map(([label, value]) => (
                    <div key={label} className="flex justify-between items-center p-3 bg-gray-800/50 rounded-lg">
                      <span className="text-gray-400 text-sm">{label}</span>
                      <span className="text-white text-sm font-medium">{value}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-500 text-sm">No upcoming races found.</p>
              )}
            </motion.div>
          </div>
        </div>
      )}

      {tab === 'drivers' && <DriverAnalytics />}
      {tab === 'tracks'  && <TrackAnalytics />}

      {tab === 'teams' && (
        <div className="px-4 sm:px-6 lg:px-8 py-6">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-800">
              <h3 className="text-white font-semibold">Constructor Standings — {year}</h3>
            </div>
            {loading ? (
              <div className="flex justify-center py-12"><RefreshCw className="w-6 h-6 animate-spin text-gray-500" /></div>
            ) : teams.length > 0 ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-gray-500 text-xs uppercase border-b border-gray-800">
                    <th className="px-5 py-3 text-left w-10">#</th>
                    <th className="px-5 py-3 text-left">Constructor</th>
                    <th className="px-5 py-3 text-right">Points</th>
                    <th className="px-5 py-3 text-right">Wins</th>
                  </tr>
                </thead>
                <tbody>
                  {teams.map((team, i) => (
                    <tr key={team.constructor_id ?? i} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                      <td className="px-5 py-3 text-gray-400 font-mono">{team.position ?? i + 1}</td>
                      <td className="px-5 py-3 text-white font-medium">{team.constructor_name}</td>
                      <td className="px-5 py-3 text-right text-racing-red font-bold">{team.points}</td>
                      <td className="px-5 py-3 text-right text-gray-400">{team.wins ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-gray-500 text-sm px-5 py-8">No constructor standings available.</p>
            )}
          </motion.div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
