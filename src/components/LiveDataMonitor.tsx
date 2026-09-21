import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Radio, Activity, Clock, Users, AlertCircle, CheckCircle, RefreshCw, Play, Square, Wifi, WifiOff } from 'lucide-react';
import { backendApi } from '../services/backendApi';
import { isPastDate } from '../utils/dates';
import { isRaceRound } from '../utils/races';
import LiveSectionTabs from './LiveSectionTabs';
import {
  Button, Card, CardBody, CardHeader, EmptyState, FadeIn, FilterBar, PageHeader, PageShell,
  PositionBadge, SelectField, TabPanel,
} from './ui';

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
const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 6 }, (_, i) => CURRENT_YEAR - i);

const CONNECTION = {
  disconnected: { color: 'text-gray-500',   Icon: WifiOff,     label: 'Disconnected' },
  connecting:   { color: 'text-yellow-500', Icon: RefreshCw,   label: 'Connecting' },
  connected:    { color: 'text-green-500',  Icon: CheckCircle, label: 'Connected' },
  error:        { color: 'text-red-500',    Icon: AlertCircle, label: 'Connection lost' },
} as const;

const LiveDataMonitor: React.FC = () => {
  const [races, setRaces]             = useState<RaceOption[]>([]);
  const [selectedYear, setSelectedYear] = useState(CURRENT_YEAR);
  const [selectedGp, setSelectedGp]   = useState('');
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [liveState, setLiveState]     = useState<LiveState | null>(null);
  const [connStatus, setConnStatus]   = useState<keyof typeof CONNECTION>('disconnected');
  const [lastUpdate, setLastUpdate]   = useState<Date | null>(null);
  const [reconnectIn, setReconnectIn] = useState<number | null>(null);

  const wsRef        = useRef<WebSocket | null>(null);
  const backoffRef   = useRef(1000);
  const retryTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load the schedule for the year and preselect the weekend most likely to be
  // live: the next race, or the latest one once the season is over.
  useEffect(() => {
    let cancelled = false;
    backendApi.getRaceSchedule(selectedYear)
      .then((data) => {
        if (cancelled) return;
        const list = (Array.isArray(data) ? data : []).filter(isRaceRound);
        const options = list.map((r) => ({
          round: r.round,
          race_name: r.race_name,
          gp: r.race_name.replace(/ /g, '_').replace(/\//g, '-'),
        }));
        setRaces(options);
        const pick = list.find((r) => !isPastDate(r.date)) ?? list[list.length - 1];
        setSelectedGp(pick ? pick.race_name.replace(/ /g, '_').replace(/\//g, '-') : '');
      })
      .catch(() => { if (!cancelled) { setRaces([]); setSelectedGp(''); } });
    return () => { cancelled = true; };
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

  const { color: statusColor, Icon: StatusIcon, label: statusLabel } = CONNECTION[connStatus];
  const hasData = liveState && (liveState.positions?.length ?? 0) > 0;

  return (
    <PageShell>
      <PageHeader title="Live" subtitle="Real-time timing data during F1 sessions" />
      <LiveSectionTabs active="monitor" />

      <TabPanel id="monitor" idPrefix="live" className="pt-6">
        <FilterBar>
          <SelectField label="Year" value={selectedYear} disabled={isMonitoring}
            onChange={(v) => { setSelectedYear(Number(v)); setIsMonitoring(false); }}>
            {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
          </SelectField>
          <SelectField label="Grand Prix" value={selectedGp} disabled={isMonitoring || races.length === 0}
            className="min-w-[260px]" onChange={(v) => { setSelectedGp(v); setIsMonitoring(false); }}>
            {races.length === 0 && <option value="">No calendar for {selectedYear}</option>}
            {races.map((r) => <option key={r.gp} value={r.gp}>Round {r.round} — {r.race_name}</option>)}
          </SelectField>

          <div className="ml-auto flex flex-wrap items-center gap-4">
            <div className={`flex items-center gap-2 text-sm font-medium ${statusColor}`} role="status">
              <StatusIcon className={`h-4 w-4 ${connStatus === 'connecting' ? 'animate-spin' : ''}`} aria-hidden="true" />
              <span>{statusLabel}</span>
              {reconnectIn !== null && <span className="text-xs text-gray-500">(retry in {reconnectIn}s)</span>}
            </div>
            {lastUpdate && (
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <Clock className="h-4 w-4" aria-hidden="true" />
                <span>{lastUpdate.toLocaleTimeString()}</span>
              </div>
            )}
            <Button
              variant={isMonitoring ? 'danger' : 'primary'}
              disabled={!selectedGp}
              onClick={() => setIsMonitoring((m) => !m)}
              icon={isMonitoring ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            >
              {isMonitoring ? 'Stop' : 'Start Monitoring'}
            </Button>
          </div>
        </FilterBar>

        {!isMonitoring ? (
          <Card>
            <EmptyState
              icon={<Radio className="h-10 w-10" />}
              title="Select a Grand Prix and press Start Monitoring"
              message="Live data streams automatically during active F1 race weekends."
            />
          </Card>
        ) : !hasData ? (
          <Card>
            {connStatus === 'connected' ? (
              <EmptyState
                icon={<Radio className="h-10 w-10" />}
                title="No live session active"
                message="Live data appears here during an active F1 session. It streams automatically when a race weekend is underway."
              />
            ) : (
              <EmptyState
                icon={<Wifi className="h-10 w-10 animate-pulse text-yellow-500/60" />}
                title={connStatus === 'connecting' ? 'Connecting…' : 'Connection lost — retrying…'}
              />
            )}
          </Card>
        ) : (
          <FadeIn className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader
                title="Live Positions"
                icon={<Users className="h-4 w-4" />}
                subtitle={liveState?.lap ? `Lap ${liveState.lap}${liveState.total_laps ? ` / ${liveState.total_laps}` : ''}` : undefined}
              />
              <ul>
                {liveState!.positions!.map((pos) => (
                  <li key={pos.driver_id} className="flex items-center justify-between gap-3 border-b border-gray-800/60 px-5 py-3 last:border-b-0">
                    <span className="flex items-center gap-3">
                      <PositionBadge position={pos.position} />
                      <span>
                        <span className="block font-medium text-white">{pos.driver_name ?? pos.driver_id.toUpperCase()}</span>
                        <span className="block text-xs text-gray-500">{pos.status}</span>
                      </span>
                    </span>
                    <span className="text-right text-sm tabular-nums">
                      <span className="block text-white">{pos.last_lap_time ?? '—'}</span>
                      <span className="block text-gray-500">{pos.gap ?? ''}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </Card>

            <Card>
              <CardHeader title="Session Info" icon={<Activity className="h-4 w-4" />} />
              <CardBody className="grid grid-cols-2 gap-3">
                {[
                  ['Session Status', liveState?.session_status ?? '—'],
                  ['Track Status',   liveState?.track_status   ?? '—'],
                  ['Lap',            liveState?.lap ? `${liveState.lap} / ${liveState.total_laps ?? '?'}` : '—'],
                  ['Last Update',    lastUpdate?.toLocaleTimeString() ?? '—'],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg bg-gray-800/50 p-4 text-center">
                    <p className="text-xl font-bold capitalize text-white">{value}</p>
                    <p className="mt-1 text-xs uppercase tracking-wide text-gray-500">{label}</p>
                  </div>
                ))}
              </CardBody>
            </Card>
          </FadeIn>
        )}
      </TabPanel>
    </PageShell>
  );
};

export default LiveDataMonitor;
