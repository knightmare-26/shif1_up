import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, CloudSun, Pause, Play, PlayCircle, X } from 'lucide-react';
import { backendApi, ReplayFrame, ReplayLapFrame, SessionDataError, SessionWeather } from '../services/backendApi';
import LiveTimingBoard from './LiveTimingBoard';
import WeatherPanel from './WeatherPanel';
import { Button, Card, CardBody, CardHeader, ErrorState, LoadingState, Notice, SelectField } from './ui';

const FIRST_SEASON = 2023;   // OpenF1's data starts here
const SPEEDS = [1, 10, 30, 60];   // practice and qualifying: session seconds per second
const PACES = [{ ms: 3000, label: '3 s a lap' }, { ms: 1500, label: '1.5 s a lap' }, { ms: 700, label: '0.7 s a lap' }];

/** Races and sprints are replayed lap by lap; practice and qualifying have no race laps, so they
 *  play through the session's time. */
export const isLapSession = (session: string) => session === 'R' || session === 'S';

/** Where the page's "watch the replay" and weather shortcuts scroll to. */
export const REPLAY_ANCHOR = 'session-replay';
export const WEATHER_ANCHOR = 'session-weather';

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

/**
 * Race Results, under the classification: a replay of the session on the timing board (a race or
 * sprint lap by lap), and below it, in its own box, the session's weather (2023 onwards).
 * `onInfo` tells the page once both are available (for its shortcuts at the top); a new
 * `replayRequest` opens the replay, starts it and scrolls to it.
 */
const SessionConditions: React.FC<{
  year: number; raceName: string; session: string; sessionLabel: string;
  onInfo?: (info: SessionWeather | null) => void;
  replayRequest?: number;
}> = ({ year, raceName, session, sessionLabel, onInfo, replayRequest = 0 }) => {
  const byLap = isLapSession(session);
  const [info, setInfo] = useState<SessionWeather | null>(null);
  const [infoError, setInfoError] = useState<SessionDataError | null>(null);
  const [loading, setLoading] = useState(false);

  const [open, setOpen] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(30);
  const [t, setT] = useState(0);
  const [lap, setLap] = useState(0);
  const [laps, setLaps] = useState<number | null>(null);
  const [pace, setPace] = useState(1500);
  const [frame, setFrame] = useState<ReplayFrame | ReplayLapFrame | null>(null);
  const [frameError, setFrameError] = useState<SessionDataError | null>(null);

  const generation = useRef(0);    // bumps when the session changes: late answers are ignored
  const inFlight = useRef(false);
  const wanted = useRef<number | null>(null);
  const replayBox = useRef<HTMLDivElement>(null);

  const loadInfo = useCallback(async () => {
    const gen = ++generation.current;
    setInfo(null);
    setInfoError(null);
    setOpen(false);
    setPlaying(false);
    setFrame(null);
    setFrameError(null);
    setT(0);
    setLap(0);
    setLaps(null);
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
  useEffect(() => { onInfo?.(info); }, [info, onInfo]);

  // The page's "watch the replay" button.
  useEffect(() => {
    if (!replayRequest) return;
    setOpen(true);
    setPlaying(true);
    replayBox.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }, [replayRequest]);

  // One frame request at a time; while one is out, only the latest wanted lap (moment) is kept.
  const fetchFrame = useCallback(async (position: number) => {
    wanted.current = position;
    if (inFlight.current) return;
    inFlight.current = true;
    const gen = generation.current;
    try {
      while (wanted.current != null && gen === generation.current) {
        const p = wanted.current;
        wanted.current = null;
        const lapFrame = byLap ? await backendApi.getReplayLap(year, raceName, session, p) : null;
        const f = lapFrame ?? await backendApi.getReplayFrame(year, raceName, session, p);
        if (gen === generation.current) {
          setFrame(f);
          setFrameError(null);
          if (lapFrame) setLaps(lapFrame.laps);
        }
      }
    } catch (e) {
      if (gen === generation.current) {
        setFrameError(e instanceof SessionDataError ? e : new SessionDataError('failed', 'Something went wrong'));
        setPlaying(false);
      }
    } finally {
      inFlight.current = false;
    }
  }, [byLap, year, raceName, session]);

  const position = byLap ? lap : t;
  useEffect(() => { if (open) fetchFrame(position); }, [open, position, fetchFrame]);

  // Practice and qualifying: the session clock runs at `speed`, once the first frame is in.
  const duration = info?.duration_seconds ?? 0;
  useEffect(() => {
    if (byLap || !open || !playing || !frame) return undefined;
    const id = setInterval(() => {
      setT((now) => {
        const next = Math.min(now + speed, duration);
        if (next >= duration) setPlaying(false);
        return next;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [byLap, open, playing, speed, duration, frame]);

  // A race or sprint: each lap stays on screen for `pace` once it has arrived, so none is skipped.
  const shownLap = frame && 'lap' in frame ? frame.lap : null;
  useEffect(() => {
    if (!byLap || !open || !playing || shownLap !== lap || laps == null) return undefined;
    if (lap >= laps) { setPlaying(false); return undefined; }
    const id = setTimeout(() => setLap((l) => Math.min(l + 1, laps)), pace);
    return () => clearTimeout(id);
  }, [byLap, open, playing, shownLap, lap, laps, pace]);

  const atEnd = byLap ? laps != null && lap >= laps : t >= duration;
  const togglePlay = () => {
    if (!playing && atEnd) {            // from the top again
      if (byLap) setLap(0); else setT(0);
    }
    setPlaying((p) => !p);
  };
  const stepLap = (delta: number) => {
    setPlaying(false);
    setLap((l) => Math.min(Math.max(l + delta, 0), laps ?? l));
  };

  const w = info?.weather;
  const summary = w ? [
    range(w.air_range, '°C') && `air ${range(w.air_range, '°C')}`,
    range(w.track_range, '°C') && `track ${range(w.track_range, '°C')}`,
    w.rain_during ? 'rain fell' : 'no rain',
  ].filter(Boolean).join(', ') : null;

  if (!info) {
    return (
      <Card>
        <CardHeader title={`Replay and weather — ${sessionLabel}`} icon={<PlayCircle className="h-4 w-4" />} />
        <CardBody>
          {year < FIRST_SEASON ? (
            <p className="text-sm text-gray-500">Weather and replays are available from {FIRST_SEASON}.</p>
          ) : loading ? (
            <LoadingState label="Loading the replay and weather…" className="py-6" />
          ) : infoError?.kind === 'locked' ? (
            <LockedNotice />
          ) : infoError?.kind === 'unavailable' ? (
            <p className="text-sm text-gray-500">{infoError.message}.</p>
          ) : infoError ? (
            <ErrorState title="Couldn't load the replay and weather" message={infoError.message} onRetry={loadInfo} />
          ) : null}
        </CardBody>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div id={REPLAY_ANCHOR} ref={replayBox} className="scroll-mt-24">
        <Card>
          <CardHeader
            title={`Replay — ${sessionLabel}`}
            icon={<PlayCircle className="h-4 w-4" />}
            subtitle={byLap ? 'Lap by lap, on the timing board' : 'On the timing board, through the session'}
            action={open
              ? <Button variant="secondary" onClick={() => { setOpen(false); setPlaying(false); }} icon={<X className="h-4 w-4" />}>Close replay</Button>
              : <Button onClick={() => { setOpen(true); setPlaying(true); }} icon={<Play className="h-4 w-4" />}>Watch replay</Button>}
          />
          {open && (
            <CardBody className="space-y-4">
              <div className="flex flex-wrap items-end gap-3">
                <Button onClick={togglePlay} disabled={!frame}
                  icon={playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}>
                  {playing ? 'Pause' : atEnd ? 'Replay again' : 'Play'}
                </Button>
                {byLap ? (
                  <>
                    <Button variant="secondary" aria-label="Previous lap" onClick={() => stepLap(-1)} disabled={!frame || lap <= 0}
                      icon={<ChevronLeft className="h-4 w-4" />} />
                    <Button variant="secondary" aria-label="Next lap" onClick={() => stepLap(1)} disabled={!frame || laps == null || lap >= laps}
                      icon={<ChevronRight className="h-4 w-4" />} />
                    <SelectField label="Pace" value={pace} onChange={(v) => setPace(Number(v))} className="min-w-[130px]">
                      {PACES.map((p) => <option key={p.ms} value={p.ms}>{p.label}</option>)}
                    </SelectField>
                    <label className="flex min-w-[240px] flex-1 flex-col gap-1">
                      <span className="flex justify-between text-xs uppercase tracking-wide text-gray-400">
                        <span>Lap</span>
                        <span className="tabular-nums text-gray-300">
                          {lap === 0 ? 'Start' : `Lap ${lap}`}{laps != null ? ` / ${laps}` : ''}
                        </span>
                      </span>
                      <input
                        type="range" min={0} max={laps ?? 0} step={1} value={lap} disabled={laps == null}
                        onChange={(e) => { setPlaying(false); setLap(Number(e.target.value)); }}
                        className="w-full accent-[#D62828]" aria-label="Lap"
                      />
                    </label>
                  </>
                ) : (
                  <>
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
                  </>
                )}
              </div>
              {frameError?.kind === 'locked' ? <LockedNotice /> : frameError ? (
                <ErrorState title="Couldn't load the replay" message={frameError.message} onRetry={() => fetchFrame(position)} />
              ) : !frame ? (
                <LoadingState label="Loading the session — the first time takes a few seconds…" className="py-6" />
              ) : (
                <LiveTimingBoard state={frame.state} sessionLabel={sessionLabel} lastUpdate={null} />
              )}
            </CardBody>
          )}
        </Card>
      </div>

      <div id={WEATHER_ANCHOR} className="scroll-mt-24">
        <Card>
          <CardHeader
            title={`Weather — ${sessionLabel}`}
            icon={<CloudSun className="h-4 w-4" />}
            subtitle={`At the start of the session${summary ? `. During it: ${summary}` : ''}.`}
          />
          <CardBody>
            <WeatherPanel weather={w?.at_start} />
          </CardBody>
        </Card>
      </div>
    </div>
  );
};

export default SessionConditions;
