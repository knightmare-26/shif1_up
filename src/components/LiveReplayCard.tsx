import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Play, Radio, Square } from 'lucide-react';
import { getStoredToken } from '../services/authApi';
import { listLiveRelays, LiveRelay, startLiveRelay, stopLiveRelay } from '../services/adminApi';
import { backendApi, RaceEvent } from '../services/backendApi';
import { isPastDate } from '../utils/dates';
import { isRaceRound, LiveSession, LIVE_SESSION_LABELS, liveMonitorPath, sessionsForWeekend } from '../utils/races';
import { useLiveTiming } from '../config/features';
import { Button, Card, CardBody, CardHeader, Pill, SelectField } from './ui';

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = [CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2, CURRENT_YEAR - 3];
const SPEEDS = [10, 30, 60, 120];
const gpId = (raceName: string) => raceName.replace(/ /g, '_').replace(/\//g, '-');

/** Data Manager: the live feed's state, and replays of finished sessions (OpenF1's historical
 *  data is free, so this works without the paid live feed — handy to check the Live pages). */
const LiveReplayCard: React.FC = () => {
  const { status } = useLiveTiming();
  const [year, setYear] = useState(CURRENT_YEAR);
  const [races, setRaces] = useState<RaceEvent[]>([]);
  const [race, setRace] = useState('');
  const [session, setSession] = useState<LiveSession>('R');
  const [speed, setSpeed] = useState(30);
  const [relays, setRelays] = useState<LiveRelay[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    backendApi.getRaceSchedule(year).then((data) => {
      if (cancelled) return;
      const past = (Array.isArray(data) ? data : []).filter((r) => isRaceRound(r) && isPastDate(r.date));
      setRaces(past);
      setRace(past.length ? past[past.length - 1].race_name : '');
    }).catch(() => { if (!cancelled) setRaces([]); });
    return () => { cancelled = true; };
  }, [year]);

  const refresh = useCallback(async () => {
    const token = getStoredToken();
    if (!token) return;
    try { setRelays(await listLiveRelays(token)); } catch { /* keep the last list */ }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  const selected = races.find((r) => r.race_name === race);
  const sessions = sessionsForWeekend(!!selected?.is_sprint);

  const start = async () => {
    const token = getStoredToken();
    if (!token || !race) return;
    setBusy(true);
    setError(null);
    try {
      await startLiveRelay(token, year, race, session, speed);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start the replay');
    } finally {
      setBusy(false);
    }
  };

  const stop = async (raceId: string) => {
    const token = getStoredToken();
    if (!token) return;
    try { await stopLiveRelay(token, raceId); } catch { /* already stopped */ }
    await refresh();
  };

  return (
    <Card>
      <CardHeader
        title="Live Timing"
        icon={<Radio className="h-4 w-4" />}
        subtitle={status?.live_available
          ? 'The OpenF1 live feed is connected: sessions are followed automatically while they run.'
          : 'The live feed isn\'t connected (set OPENF1_USERNAME / OPENF1_PASSWORD on the API). Replays of finished sessions still work.'}
        action={<Pill tone={status?.live_available ? 'good' : 'neutral'}>{status?.live_available ? 'Live feed on' : 'Replays only'}</Pill>}
      />
      <CardBody className="space-y-4">
        <div className="flex flex-wrap items-end gap-4">
          <SelectField label="Season" value={year} onChange={(v) => setYear(Number(v))}>
            {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
          </SelectField>
          <SelectField label="Grand Prix" value={race} onChange={setRace} className="min-w-[220px]" disabled={!races.length}>
            {!races.length && <option value="">No finished races</option>}
            {races.map((r) => <option key={r.round} value={r.race_name}>Round {r.round} — {r.race_name}</option>)}
          </SelectField>
          <SelectField label="Session" value={session} onChange={(v) => setSession(v as LiveSession)}>
            {sessions.map((s) => <option key={s} value={s}>{LIVE_SESSION_LABELS[s]}</option>)}
          </SelectField>
          <SelectField label="Speed" value={speed} onChange={(v) => setSpeed(Number(v))} className="min-w-[100px]">
            {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
          </SelectField>
          <Button onClick={start} loading={busy} disabled={!race} icon={<Play className="h-4 w-4" />}>Start replay</Button>
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
        {relays.length > 0 && (
          <ul className="divide-y divide-gray-800 rounded-lg border border-gray-800">
            {relays.map((r) => {
              const running = r.status === 'running' || r.status === 'starting';
              return (
                <li key={r.race_id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-2 text-sm">
                  <span className="text-gray-200">
                    {r.year} {r.gp} — {LIVE_SESSION_LABELS[r.session as LiveSession] ?? r.session}
                    {r.replay ? ` · replay ${r.replay_speed}×` : ' · live'}
                  </span>
                  <span className="flex items-center gap-2">
                    <Pill tone={running ? 'good' : r.status === 'failed' ? 'bad' : 'neutral'}>{r.status}</Pill>
                    {r.detail && <span className="text-xs text-gray-500">{r.detail}</span>}
                    {running && (
                      <>
                        <Link to={liveMonitorPath(r.year, gpId(r.gp), r.session as LiveSession)} className="text-racing-red underline">Watch</Link>
                        <Button variant="secondary" onClick={() => stop(r.race_id)} icon={<Square className="h-3 w-3" />}>Stop</Button>
                      </>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </CardBody>
    </Card>
  );
};

export default LiveReplayCard;
