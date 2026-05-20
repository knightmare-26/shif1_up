import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, Clock, TrendingUp, Calendar, MapPin, RefreshCw } from 'lucide-react';
import { backendApi, RaceEvent, LiveRaceState } from '../services/backendApi';

const LIVE_POLL_MS = 15_000;

const LiveAnalytics: React.FC = () => {
  const year = new Date().getFullYear();
  const [schedule, setSchedule] = useState<RaceEvent[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [liveState, setLiveState] = useState<LiveRaceState | null>(null);

  useEffect(() => {
    backendApi.getRaceSchedule(year)
      .then(data => setSchedule(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [year]);

  const now       = new Date();
  const nextRace  = schedule.find(r => new Date(r.date) >= now);
  const lastRace  = [...schedule]
    .filter(r => new Date(r.date) < now)
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())[0];

  // Poll live state for the next race — shows positions if a session is active.
  useEffect(() => {
    if (!nextRace) return;
    const raceId = `${year}_${nextRace.race_name.replace(/ /g, '_').replace(/\//g, '-')}`;
    let cancelled = false;
    const fetchState = () => {
      backendApi.getLiveRaceState(raceId)
        .then(s => { if (!cancelled) setLiveState(s); })
        .catch(() => {});
    };
    fetchState();
    const id = setInterval(fetchState, LIVE_POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [nextRace?.race_name, year]);

  const sessionLive = liveState?.session_status === 'live'
    && (liveState?.positions?.length ?? 0) > 0;

  const daysUntil = nextRace
    ? Math.ceil((new Date(nextRace.date).getTime() - now.getTime()) / 86_400_000)
    : null;

  return (
    <div className="min-h-screen bg-carbon-black p-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}
        className="mb-8"
      >
        <h1 className="text-4xl font-racing text-racing-red mb-2">Live Analytics</h1>
        <p className="text-pure-white text-lg">Real-time Formula 1 data — active during race weekends</p>
      </motion.div>

      {/* Live session banner */}
      <motion.div
        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.2 }}
        className="bg-gradient-to-r from-racing-red to-red-700 rounded-xl p-6 text-pure-white shadow-lg mb-8"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold flex items-center">
            <Activity className="w-6 h-6 mr-3" />
            Live Race Status
          </h2>
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${
            sessionLive ? 'bg-green-500/80' : 'bg-white/20'
          }`}>
            {sessionLive ? `LIVE — Lap ${liveState?.lap ?? '?'}${liveState?.total_laps ? ` / ${liveState.total_laps}` : ''}` : 'No session active'}
          </span>
        </div>

        {sessionLive ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {liveState!.positions!.slice(0, 10).map(p => (
              <div key={p.driver_id} className="flex justify-between items-center bg-white/10 rounded px-3 py-2 text-sm">
                <span className="font-mono">
                  <span className="font-bold mr-2">P{p.position}</span>
                  {p.driver_name || p.driver_id}
                </span>
                <span className="opacity-80 font-mono">{p.gap ?? p.last_lap_time ?? '—'}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="opacity-80 text-sm">
            Live timing data streams here during F1 sessions. Use the <strong>Live Data Monitor</strong> to
            connect to the WebSocket feed when a session is running.
          </p>
        )}
      </motion.div>

      {/* Next race / Last race */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
        {/* Next race */}
        <motion.div
          initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.6, delay: 0.3 }}
          className="bg-track-grey rounded-xl p-6 shadow-lg"
        >
          <h3 className="text-xl font-bold text-carbon-black mb-4 flex items-center">
            <Calendar className="w-5 h-5 text-racing-red mr-2" />
            Next Race — {year}
          </h3>
          {loading ? (
            <div className="flex items-center justify-center h-24">
              <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : nextRace ? (
            <div className="space-y-3">
              {[
                ['Race',    nextRace.race_name],
                ['Circuit', nextRace.circuit_name],
                ['Country', nextRace.country],
                ['Date',    nextRace.date],
                ['In',      daysUntil !== null ? `${daysUntil} day${daysUntil === 1 ? '' : 's'}` : '—'],
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between items-center p-3 bg-pure-white rounded-lg">
                  <span className="text-carbon-black">{label}</span>
                  <span className="font-bold text-racing-red">{value}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">No upcoming races found for {year}.</p>
          )}
        </motion.div>

        {/* Last race */}
        <motion.div
          initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.6, delay: 0.4 }}
          className="bg-track-grey rounded-xl p-6 shadow-lg"
        >
          <h3 className="text-xl font-bold text-carbon-black mb-4 flex items-center">
            <MapPin className="w-5 h-5 text-turbo-teal mr-2" />
            Last Race — {year}
          </h3>
          {loading ? (
            <div className="flex items-center justify-center h-24">
              <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : lastRace ? (
            <div className="space-y-3">
              {[
                ['Race',    lastRace.race_name],
                ['Circuit', lastRace.circuit_name],
                ['Country', lastRace.country],
                ['Date',    lastRace.date],
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between items-center p-3 bg-pure-white rounded-lg">
                  <span className="text-carbon-black">{label}</span>
                  <span className="font-bold text-turbo-teal">{value}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">No completed races yet this season.</p>
          )}
        </motion.div>
      </div>

      {/* Season at a glance */}
      <motion.div
        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.5 }}
        className="bg-track-grey rounded-xl p-6 shadow-lg mb-8"
      >
        <h3 className="text-xl font-bold text-carbon-black mb-4 flex items-center">
          <TrendingUp className="w-5 h-5 text-racing-red mr-2" />
          {year} Season Progress
        </h3>
        {loading ? (
          <div className="flex items-center justify-center h-12">
            <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
          </div>
        ) : (
          <div className="flex items-center space-x-4">
            <div className="flex-1 bg-pure-white rounded-full h-4 overflow-hidden">
              <div
                className="h-full bg-racing-red rounded-full transition-all duration-700"
                style={{
                  width: schedule.length
                    ? `${(schedule.filter(r => new Date(r.date) < now).length / schedule.length) * 100}%`
                    : '0%'
                }}
              />
            </div>
            <span className="text-carbon-black font-bold text-sm whitespace-nowrap">
              {schedule.filter(r => new Date(r.date) < now).length} / {schedule.length} races
            </span>
          </div>
        )}
      </motion.div>

      {/* Live features note */}
      <motion.div
        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.6 }}
        className="bg-gradient-to-r from-pit-stop-yellow to-yellow-600 rounded-xl p-8 text-center text-pure-white shadow-lg"
      >
        <h3 className="text-2xl font-bold mb-2">Live Data — Race Weekends Only</h3>
        <p className="opacity-90 text-sm max-w-2xl mx-auto">
          During an F1 session, start <code className="bg-white/20 px-1 rounded">live/poller.py</code> to push
          real-time timing to Redis. The <strong>Live Data Monitor</strong> page then streams it directly to your
          browser via WebSocket.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6 text-sm">
          <div><p className="font-bold">WebSocket Streaming</p><p className="opacity-80">Sub-second updates via Redis pub/sub</p></div>
          <div><p className="font-bold">Auto-reconnect</p><p className="opacity-80">Exponential backoff on disconnect</p></div>
          <div><p className="font-bold">Historical Fallback</p><p className="opacity-80">Post-race data loads from DuckDB</p></div>
        </div>
      </motion.div>
    </div>
  );
};

export default LiveAnalytics;
