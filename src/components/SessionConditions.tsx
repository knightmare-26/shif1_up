import React, { useCallback, useEffect, useRef, useState } from 'react';
import { CloudSun, Pause, Play, X } from 'lucide-react';
import { backendApi, ReplayFrame, SessionDataError, SessionWeather } from '../services/backendApi';
import LiveTimingBoard from './LiveTimingBoard';
import WeatherPanel from './WeatherPanel';
import { Button, Card, CardBody, CardHeader, ErrorState, LoadingState, Notice, SelectField } from './ui';

const FIRST_SEASON = 2023;   // OpenF1's data starts here
const SPEEDS = [1, 10, 30, 60];

const clockLabel = (seconds: number) => {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
};

const range = (r: [number, number] | null | undefined, unit: string) =>
  r ? (Math.round(r[0]) === Math.round(r[1]) ? `${Math.round(r[0])}${unit}` : `${Math.round(r[0])}–${Math.round(r[1])}${unit}`) : null;

const LockedNotice: React.FC = () => (
  <Notice tone="warning" className="">
    Paused while an F1 session is live: the data provider shuts free access until it ends. Try again afterwards.
  </Notice>
);

/** Race Results: the session's weather, and a replay of it on the timing board (2023 onwards). */
const SessionConditions: React.FC<{ year: number; raceName: string; session: string; sessionLabel: string }> = ({
  year, raceName, session, sessionLabel,
}) => {
  const [info, setInfo] = useState<SessionWeather | null>(null);
  const [infoError, setInfoError] = useState<SessionDataError | null>(null);
  const [loading, setLoading] = useState(false);

  const [open, setOpen] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(30);
  const [t, setT] = useState(0);
  const [frame, setFrame] = useState<ReplayFrame | null>(null);
  const [frameError, setFrameError] = useState<SessionDataError | null>(null);

  const generation = useRef(0);    // bumps when the session changes: late answers are ignored
  const inFlight = useRef(false);
  const wanted = useRef<number | null>(null);

  const loadInfo = useCallback(async () => {
    const gen = ++generation.current;
    setInfo(null);
    setInfoError(null);
    setOpen(false);
    setPlaying(false);
    setFrame(null);
    setFrameError(null);
    setT(0);
    if (year < FIRST_SEASON) return;
    setLoading(true);
    try {
      const data = await backendApi.getSessionConditions(year, raceName, session);
      if (gen === generation.current) setInfo(data);
    } catch (e) {
      if (gen === generation.current) {
        setInfoError(e instanceof SessionDataError ? e : new SessionDataError('failed', 'Something went wrong'));
      }
    } finally {
      if (gen === generation.current) setLoading(false);
    }
  }, [year, raceName, session]);

  useEffect(() => { loadInfo(); }, [loadInfo]);

  // One frame request at a time; while one is out, only the latest wanted moment is kept.
  const fetchFrame = useCallback(async (seconds: number) => {
    wanted.current = seconds;
    if (inFlight.current) return;
    inFlight.current = true;
    const gen = generation.current;
    try {
      while (wanted.current != null && gen === generation.current) {
        const s = wanted.current;
        wanted.current = null;
        const f = await backendApi.getReplayFrame(year, raceName, session, s);
        if (gen === generation.current) { setFrame(f); setFrameError(null); }
      }
    } catch (e) {
      if (gen === generation.current) {
        setFrameError(e instanceof SessionDataError ? e : new SessionDataError('failed', 'Something went wrong'));
        setPlaying(false);
      }
    } finally {
      inFlight.current = false;
    }
  }, [year, raceName, session]);

  useEffect(() => { if (open) fetchFrame(t); }, [open, t, fetchFrame]);

  const duration = info?.duration_seconds ?? 0;
  useEffect(() => {
    if (!open || !playing || !frame) return undefined;   // wait for the first frame before the clock runs
    const id = setInterval(() => {
      setT((now) => {
        const next = Math.min(now + speed, duration);
        if (next >= duration) setPlaying(false);
        return next;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [open, playing, speed, duration, frame]);

  const w = info?.weather;
  const summary = w ? [
    range(w.air_range, '°C') && `air ${range(w.air_range, '°C')}`,
    range(w.track_range, '°C') && `track ${range(w.track_range, '°C')}`,
    w.rain_during ? 'rain fell' : 'no rain',
  ].filter(Boolean).join(', ') : null;

  return (
    <Card>
      <CardHeader
        title={open ? `Replay — ${sessionLabel}` : `Weather — ${sessionLabel}`}
        icon={<CloudSun className="h-4 w-4" />}
        subtitle={open
          ? 'The timing board and weather as the session unfolded'
          : info ? `At the start of the session${summary ? `. During it: ${summary}.` : ''}` : undefined}
        action={info && (open
          ? <Button variant="secondary" onClick={() => { setOpen(false); setPlaying(false); }} icon={<X className="h-4 w-4" />}>Close replay</Button>
          : <Button onClick={() => { setOpen(true); setPlaying(true); }} icon={<Play className="h-4 w-4" />}>Watch replay</Button>)}
      />
      <CardBody className="space-y-4">
        {year < FIRST_SEASON ? (
          <p className="text-sm text-gray-500">Weather and replays are available from {FIRST_SEASON}.</p>
        ) : loading ? (
          <LoadingState label="Loading the weather…" className="py-6" />
        ) : infoError?.kind === 'locked' ? (
          <LockedNotice />
        ) : infoError?.kind === 'unavailable' ? (
          <p className="text-sm text-gray-500">{infoError.message}.</p>
        ) : infoError ? (
          <ErrorState title="Couldn't load the weather" message={infoError.message} onRetry={loadInfo} />
        ) : !info ? null : !open ? (
          <WeatherPanel weather={w?.at_start} />
        ) : (
          <>
            <div className="flex flex-wrap items-end gap-4">
              <Button onClick={() => setPlaying((p) => !p)} disabled={!frame}
                icon={playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}>
                {playing ? 'Pause' : t >= duration ? 'Replay again' : 'Play'}
              </Button>
              <SelectField label="Speed" value={speed} onChange={(v) => setSpeed(Number(v))} className="min-w-[100px]">
                {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
              </SelectField>
              <label className="flex min-w-[240px] flex-1 flex-col gap-1">
                <span className="flex justify-between text-xs uppercase tracking-wide text-gray-400">
                  <span>Session time</span>
                  <span className="tabular-nums normal-case text-gray-300">{clockLabel(t)} / {clockLabel(duration)}</span>
                </span>
                <input
                  type="range" min={0} max={duration} step={10} value={t}
                  onChange={(e) => setT(Number(e.target.value))}
                  className="w-full accent-[#D62828]" aria-label="Session time"
                />
              </label>
            </div>
            {frameError?.kind === 'locked' ? <LockedNotice /> : frameError ? (
              <ErrorState title="Couldn't load the replay" message={frameError.message} onRetry={() => fetchFrame(t)} />
            ) : !frame ? (
              <LoadingState label="Loading the session — the first time takes a few seconds…" className="py-6" />
            ) : (
              <>
                <WeatherPanel weather={frame.state.weather} />
                <LiveTimingBoard state={frame.state} sessionLabel={sessionLabel} lastUpdate={null} />
              </>
            )}
          </>
        )}
      </CardBody>
    </Card>
  );
};

export default SessionConditions;
