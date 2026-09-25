import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Radio, Clock, AlertCircle, CheckCircle, RefreshCw, Play, Square, Wifi, WifiOff } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { backendApi } from '../services/backendApi';
import { isPastDate } from '../utils/dates';
import { isRaceRound, LiveSession, LIVE_SESSION_LABELS, liveRaceId, sessionsForWeekend } from '../utils/races';
import LiveSectionTabs from './LiveSectionTabs';
import LiveComingSoon from './LiveComingSoon';
import { useLiveTiming } from '../config/features';
import LiveTimingBoard, { LiveState } from './LiveTimingBoard';
import {
  Button, Card, CheckboxField, EmptyState, FadeIn, FilterBar, LoadingState, PageHeader, PageShell, SelectField, TabPanel,
} from './ui';

const WS_BASE = (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  .replace(/^http/, 'ws');

interface RaceOption { round: number; race_name: string; circuit_name: string; gp: string; is_sprint: boolean; }

const MAX_BACKOFF = 30_000;
const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 6 }, (_, i) => CURRENT_YEAR - i);

const CONNECTION = {
  disconnected: { color: 'text-gray-500',   Icon: WifiOff,     label: 'Disconnected' },
  connecting:   { color: 'text-yellow-500', Icon: RefreshCw,   label: 'Connecting' },
  connected:    { color: 'text-green-500',  Icon: CheckCircle, label: 'Connected' },
  error:        { color: 'text-red-500',    Icon: AlertCircle, label: 'Connection lost' },
} as const;

const SESSION_CODES = Object.keys(LIVE_SESSION_LABELS) as LiveSession[];

const LiveMonitor: React.FC = () => {
  // A link from the Live Overview (?year=&gp=&session=) opens straight onto that session and starts monitoring.
  const [params] = useSearchParams();
  const linkedYear = Number(params.get('year')) || null;
  const linkedGp = params.get('gp');
  const linkedSessionParam = params.get('session') as LiveSession | null;
  const linkedSession = linkedSessionParam && SESSION_CODES.includes(linkedSessionParam) ? linkedSessionParam : null;
  const [races, setRaces]             = useState<RaceOption[]>([]);
  const [selectedYear, setSelectedYear] = useState(linkedYear && YEARS.includes(linkedYear) ? linkedYear : CURRENT_YEAR);
  const [selectedGp, setSelectedGp]   = useState('');
  const [selectedSession, setSelectedSession] = useState<LiveSession>(linkedSession ?? 'R');
  const [isMonitoring, setIsMonitoring] = useState(false);
  const autoStarted = useRef(false);
  const [liveState, setLiveState]     = useState<LiveState | null>(null);
  const [connStatus, setConnStatus]   = useState<keyof typeof CONNECTION>('disconnected');
  const [lastUpdate, setLastUpdate]   = useState<Date | null>(null);
  const [reconnectIn, setReconnectIn] = useState<number | null>(null);
  const [showCircuitName, setShowCircuitName] = useState(false);

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
          circuit_name: r.circuit_name,
          gp: r.race_name.replace(/ /g, '_').replace(/\//g, '-'),
          is_sprint: !!r.is_sprint,
        }));
        setRaces(options);
        const pick = list.find((r) => !isPastDate(r.date)) ?? list[list.length - 1];
        // The link only decides the first load; later year changes go back to the usual pick.
        const linked = !autoStarted.current && linkedGp ? options.find((o) => o.gp === linkedGp) : undefined;
        setSelectedGp(linked ? linked.gp : pick ? pick.race_name.replace(/ /g, '_').replace(/\//g, '-') : '');
        if (linked) { autoStarted.current = true; if (linkedSession) setIsMonitoring(true); }
      })
      .catch(() => { if (!cancelled) { setRaces([]); setSelectedGp(''); } });
    return () => { cancelled = true; };
  }, [selectedYear, linkedGp, linkedSession]);

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

  const connect = useCallback((year: number, gp: string, session: LiveSession) => {
    if (wsRef.current) { wsRef.current.onclose = null; wsRef.current.close(); }
    const raceId = liveRaceId(year, gp, session);
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
        if (wsRef.current === null) connect(year, gp, session);
      }, delay);
    };
  }, [isMonitoring]);

  useEffect(() => {
    if (isMonitoring && selectedGp) {
      connect(selectedYear, selectedGp, selectedSession);
    } else {
      disconnect();
      setLiveState(null);
    }
    return () => disconnect();
  }, [isMonitoring, selectedYear, selectedGp, selectedSession]);   // eslint-disable-line

  const { color: statusColor, Icon: StatusIcon, label: statusLabel } = CONNECTION[connStatus];
  const hasData = liveState && (liveState.positions?.length ?? 0) > 0;
  const weekend = races.find((r) => r.gp === selectedGp);
  const isSprintWeekend = !!weekend?.is_sprint;
  const sessionOptions = useMemo(() => sessionsForWeekend(isSprintWeekend), [isSprintWeekend]);
  // A session that doesn't exist on this weekend (e.g. Sprint on a normal one) falls back to the race.
  useEffect(() => {
    // Only once the weekend is known — a linked Sprint session must survive the calendar still loading.
    if (weekend && !sessionOptions.includes(selectedSession)) setSelectedSession('R');
  }, [weekend, sessionOptions, selectedSession]);

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
            {races.map((r) => (
              <option key={r.gp} value={r.gp}>
                Round {r.round} — {showCircuitName ? r.circuit_name : r.race_name}
              </option>
            ))}
          </SelectField>
          <SelectField label="Session" value={selectedSession} disabled={isMonitoring || !selectedGp}
            className="min-w-[190px]" onChange={(v) => { setSelectedSession(v as LiveSession); setIsMonitoring(false); }}>
            {sessionOptions.map((code) => <option key={code} value={code}>{LIVE_SESSION_LABELS[code]}</option>)}
          </SelectField>
          <CheckboxField label="Circuit name" checked={showCircuitName} onChange={setShowCircuitName} />

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
              title="Select a Grand Prix and session, then press Start Monitoring"
              message="Live data streams during active F1 sessions — practice, qualifying, sprint and race."
            />
          </Card>
        ) : !hasData ? (
          <Card>
            {connStatus === 'connected' ? (
              <EmptyState
                icon={<Radio className="h-10 w-10" />}
                title="No live session active"
                message={`Nothing is streaming for ${LIVE_SESSION_LABELS[selectedSession]} yet. Live data appears here while the session is running.`}
              />
            ) : (
              <EmptyState
                icon={<Wifi className="h-10 w-10 animate-pulse text-yellow-500/60" />}
                title={connStatus === 'connecting' ? 'Connecting…' : 'Connection lost — retrying…'}
              />
            )}
          </Card>
        ) : (
          <FadeIn>
            <LiveTimingBoard state={liveState!} sessionLabel={LIVE_SESSION_LABELS[selectedSession]} lastUpdate={lastUpdate} />
          </FadeIn>
        )}
      </TabPanel>
    </PageShell>
  );
};

const LiveDataMonitor: React.FC = () => {
  const { enabled, loading } = useLiveTiming();
  if (loading) return <PageShell><LoadingState label="Checking the live feed…" /></PageShell>;
  return enabled ? <LiveMonitor /> : <LiveComingSoon />;
};

export default LiveDataMonitor;
