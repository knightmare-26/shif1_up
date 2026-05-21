import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Radio, Activity, Clock, MapPin, Users,
  AlertCircle, CheckCircle, RefreshCw, Play, Square, Wifi, WifiOff,
} from 'lucide-react';

const WS_BASE = (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  .replace(/^http/, 'ws');

interface LivePosition {
  position: number;
  driver_id: string;
  driver_name?: string;
  gap?: string;
  interval?: string;
  last_lap_time?: string;
  best_lap_time?: string;
  status: string;
}

interface LiveState {
  positions?: LivePosition[];
  lap?: number;
  total_laps?: number;
  track_status?: string;
  session_status?: string;
  timestamp?: string;
}

interface RaceOption { round: number; race_name: string; gp: string; }

const MAX_BACKOFF = 30_000;

const LiveDataMonitor: React.FC = () => {
  const [races, setRaces]             = useState<RaceOption[]>([]);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [selectedGp, setSelectedGp]   = useState('');
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [liveState, setLiveState]     = useState<LiveState | null>(null);
  const [connStatus, setConnStatus]   = useState<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
  const [lastUpdate, setLastUpdate]   = useState<Date | null>(null);
  const [reconnectIn, setReconnectIn] = useState<number | null>(null);

  const wsRef        = useRef<WebSocket | null>(null);
  const backoffRef   = useRef(1000);
  const retryTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load schedule for year
  useEffect(() => {
    const yr = selectedYear;
    fetch(`/data/schedule/${yr}.json`)
      .then(r => r.ok ? r.json() : [])
      .then((data: any[]) => {
        const options = data.map(r => ({
          round: r.round,
          race_name: r.race_name,
          gp: r.race_name.replace(/ /g, '_').replace(/\//g, '-'),
        }));
        setRaces(options);
        if (options.length) setSelectedGp(options[0].gp);
      })
      .catch(() => setRaces([]));
  }, [selectedYear]);

  const clearRetry = () => {
    if (retryTimeout.current) { clearTimeout(retryTimeout.current); retryTimeout.current = null; }
    if (countdownRef.current) { clearInterval(countdownRef.current); countdownRef.current = null; }
    setReconnectIn(null);
  };

  const disconnect = useCallback(() => {
    clearRetry();
    if (wsRef.current) { wsRef.current.onclose = null; wsRef.current.close(); wsRef.current = null; }
    setConnStatus('disconnected');
  }, []);

  const connect = useCallback((year: number, gp: string) => {
    if (wsRef.current) { wsRef.current.onclose = null; wsRef.current.close(); }
    const raceId = `${year}_${gp}`;
    const url    = `${WS_BASE}/ws/live/${raceId}`;
    setConnStatus('connecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnStatus('connected');
      backoffRef.current = 1000;
      clearRetry();
    };

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        const data: LiveState = msg.data ?? msg;
        setLiveState(data);
        setLastUpdate(new Date());
      } catch { /* ignore malformed */ }
    };

    ws.onerror = () => setConnStatus('error');

    ws.onclose = () => {
      wsRef.current = null;
      if (!isMonitoring) return;   // user stopped — don't retry
      setConnStatus('error');
      const delay = Math.min(backoffRef.current, MAX_BACKOFF);
      backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF);

      let remaining = Math.ceil(delay / 1000);
      setReconnectIn(remaining);
      countdownRef.current = setInterval(() => {
        remaining -= 1;
        setReconnectIn(remaining > 0 ? remaining : null);
        if (remaining <= 0 && countdownRef.current) {
          clearInterval(countdownRef.current);
          countdownRef.current = null;
        }
      }, 1000);

      retryTimeout.current = setTimeout(() => {
        if (wsRef.current === null) connect(year, gp);
      }, delay);
    };
  }, [isMonitoring]);

  useEffect(() => {
    if (isMonitoring && selectedGp) {
      connect(selectedYear, selectedGp);
    } else {
      disconnect();
      setLiveState(null);
    }
    return () => disconnect();
  }, [isMonitoring, selectedYear, selectedGp]);   // eslint-disable-line

  const statusColor = {
    disconnected: 'text-gray-500',
    connecting:   'text-yellow-500',
    connected:    'text-green-500',
    error:        'text-red-500',
  }[connStatus];

  const StatusIcon = {
    disconnected: WifiOff,
    connecting:   RefreshCw,
    connected:    CheckCircle,
    error:        AlertCircle,
  }[connStatus];

  const hasData = liveState && (liveState.positions?.length ?? 0) > 0;

  return (
    <div className="min-h-screen bg-carbon-black text-pure-white p-6">
      <div className="max-w-7xl mx-auto">

        {/* Header */}
        <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
          <h1 className="text-4xl font-racing text-racing-red mb-2">Live F1 Data Monitor</h1>
          <p className="text-gray-300">Real-time timing data during F1 sessions</p>
        </motion.div>

        {/* Control Panel */}
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
          className="bg-track-grey rounded-lg p-6 mb-8"
        >
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center space-x-4">
              {/* Year */}
              <div className="flex items-center space-x-2">
                <span className="text-carbon-black font-medium">Year:</span>
                <select
                  value={selectedYear}
                  onChange={e => { setSelectedYear(+e.target.value); setIsMonitoring(false); }}
                  className="px-3 py-1 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-racing-red text-carbon-black"
                  disabled={isMonitoring}
                >
                  {Array.from({ length: 6 }, (_, i) => new Date().getFullYear() - i).map(y => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </div>

              {/* GP */}
              <div className="flex items-center space-x-2">
                <span className="text-carbon-black font-medium">Race:</span>
                <select
                  value={selectedGp}
                  onChange={e => { setSelectedGp(e.target.value); setIsMonitoring(false); }}
                  className="px-3 py-1 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-racing-red text-carbon-black"
                  disabled={isMonitoring}
                >
                  {races.map(r => (
                    <option key={r.gp} value={r.gp}>R{r.round} — {r.race_name}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex items-center space-x-4">
              {/* Status indicator */}
              <div className={`flex items-center space-x-2 ${statusColor}`}>
                <StatusIcon className={`w-4 h-4 ${connStatus === 'connecting' ? 'animate-spin' : ''}`} />
                <span className="text-sm font-medium capitalize">{connStatus}</span>
                {reconnectIn !== null && (
                  <span className="text-xs text-gray-400">(retry in {reconnectIn}s)</span>
                )}
              </div>

              {lastUpdate && (
                <div className="flex items-center space-x-2 text-gray-500 text-sm">
                  <Clock className="w-4 h-4" />
                  <span>{lastUpdate.toLocaleTimeString()}</span>
                </div>
              )}

              <button
                onClick={() => setIsMonitoring(m => !m)}
                disabled={!selectedGp}
                className={`px-4 py-2 rounded-lg font-medium flex items-center space-x-2 transition-colors ${
                  isMonitoring
                    ? 'bg-red-600 hover:bg-red-700 text-white'
                    : 'bg-racing-red hover:bg-red-700 text-white disabled:opacity-40'
                }`}
              >
                {isMonitoring ? <><Square className="w-4 h-4" /><span>Stop</span></>
                              : <><Play  className="w-4 h-4" /><span>Start Monitoring</span></>}
              </button>
            </div>
          </div>
        </motion.div>

        {/* Live Data */}
        <AnimatePresence>
          {isMonitoring && (
            <motion.div
              key="live"
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            >
              {!hasData ? (
                /* No data yet */
                <div className="bg-track-grey rounded-lg p-12 text-center">
                  {connStatus === 'connected' ? (
                    <>
                      <Radio className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                      <p className="text-xl font-bold text-carbon-black mb-2">No live session active</p>
                      <p className="text-gray-600 text-sm">
                        Live data appears here during an active F1 session. Data streams automatically when a race weekend is underway.
                      </p>
                    </>
                  ) : (
                    <>
                      <Wifi className="w-12 h-12 text-yellow-400 mx-auto mb-4 animate-pulse" />
                      <p className="text-xl font-bold text-carbon-black">
                        {connStatus === 'connecting' ? 'Connecting…' : 'Connection lost — retrying…'}
                      </p>
                    </>
                  )}
                </div>
              ) : (
                /* Real data */
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                  {/* Positions */}
                  <div className="bg-track-grey rounded-lg p-6">
                    <h2 className="text-2xl font-bold text-carbon-black mb-4 flex items-center">
                      <Users className="w-6 h-6 mr-2 text-racing-red" />
                      Live Positions
                      {liveState?.lap && (
                        <span className="ml-auto text-sm font-normal text-gray-600">
                          Lap {liveState.lap}{liveState.total_laps ? ` / ${liveState.total_laps}` : ''}
                        </span>
                      )}
                    </h2>
                    <div className="space-y-2">
                      {liveState!.positions!.map((pos, i) => (
                        <motion.div
                          key={pos.driver_id}
                          initial={{ opacity: 0, x: -20 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.05 }}
                          className="bg-white rounded-lg p-4 flex items-center justify-between"
                        >
                          <div className="flex items-center space-x-4">
                            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-sm ${
                              pos.position <= 3 ? 'bg-racing-red' : 'bg-gray-500'
                            }`}>
                              {pos.position}
                            </div>
                            <div>
                              <p className="font-bold text-carbon-black">{pos.driver_name ?? pos.driver_id.toUpperCase()}</p>
                              <p className="text-xs text-gray-500">{pos.status}</p>
                            </div>
                          </div>
                          <div className="text-right font-mono text-sm">
                            <p className="text-carbon-black">{pos.last_lap_time ?? '—'}</p>
                            <p className="text-gray-500">{pos.gap ?? ''}</p>
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  </div>

                  {/* Session info */}
                  <div className="bg-track-grey rounded-lg p-6">
                    <h2 className="text-2xl font-bold text-carbon-black mb-4 flex items-center">
                      <Activity className="w-6 h-6 mr-2 text-racing-red" />
                      Session Info
                    </h2>
                    <div className="grid grid-cols-2 gap-4">
                      {[
                        ['Session Status', liveState?.session_status ?? '—'],
                        ['Track Status',   liveState?.track_status   ?? '—'],
                        ['Lap',           liveState?.lap ? `${liveState.lap} / ${liveState.total_laps ?? '?'}` : '—'],
                        ['Last Update',   lastUpdate?.toLocaleTimeString() ?? '—'],
                      ].map(([label, value]) => (
                        <div key={label} className="bg-white rounded-lg p-4 text-center">
                          <p className="text-2xl font-bold text-carbon-black">{value}</p>
                          <p className="text-sm text-gray-600">{label}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Idle state */}
        {!isMonitoring && (
          <div className="bg-track-grey rounded-lg p-12 text-center">
            <MapPin className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <p className="text-xl font-bold text-carbon-black mb-2">Select a race and press Start</p>
            <p className="text-gray-600 text-sm">
              Live data streams automatically during active F1 race weekends.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default LiveDataMonitor;
