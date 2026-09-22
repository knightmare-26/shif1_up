import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BarChart3, Clock, Timer, Trophy } from 'lucide-react';
import { backendApi, RaceEvent } from '../services/backendApi';
import { isPastDate } from '../utils/dates';
import { gpToken, isRaceRound } from '../utils/races';
import {
  Button, Card, CardHeader, CheckboxField, EmptyState, ErrorState, FadeIn, FilterBar, LoadingState, PageHeader,
  PageShell, SelectField, StatCard, TableWrap, TextField, Td, Th, Tr,
} from './ui';

interface LapDataItem {
  Driver: string;
  LapNumber: string;
  LapTime: number;
  Sector1?: number;
  Sector2?: number;
  Sector3?: number;
  PitIn?: boolean;
  PitOut?: boolean;
}

const PAGE_SIZE = 50;
const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = Array.from({ length: CURRENT_YEAR - 2018 + 1 }, (_, i) => CURRENT_YEAR - i);

const formatLapTime = (time: number): string => {
  if (isNaN(time) || time === 0) return '—';
  const minutes = Math.floor(time / 60);
  const seconds = (time % 60).toFixed(3);
  return `${minutes}:${seconds.padStart(6, '0')}`;
};

// Sector splits are well under a minute — show them as plain seconds.
const formatSector = (time?: number): string => (time && time > 0 ? time.toFixed(3) : '—');

const LapData: React.FC = () => {
  const [year, setYear] = useState(CURRENT_YEAR);
  const [schedule, setSchedule] = useState<RaceEvent[]>([]);
  const [gp, setGp] = useState('');
  const [driverInput, setDriverInput] = useState('');
  const [driver, setDriver] = useState('');
  const [laps, setLaps] = useState<LapDataItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState(PAGE_SIZE);
  const [showCircuitName, setShowCircuitName] = useState(false);
  const requestId = useRef(0);

  // Latest completed race of the chosen season is the sensible starting point.
  useEffect(() => {
    let cancelled = false;
    setGp('');
    setLaps(null);
    setLoading(true);
    backendApi.getRaceSchedule(year)
      .then((events) => {
        if (cancelled) return;
        const list = (Array.isArray(events) ? events : []).filter(isRaceRound);
        setSchedule(list);
        const pick = [...list].reverse().find((r) => isPastDate(r.date)) ?? list[0];
        if (pick) setGp(gpToken(pick.race_name));
        else setLoading(false);
      })
      .catch(() => { if (!cancelled) { setSchedule([]); setLoading(false); } });
    return () => { cancelled = true; };
  }, [year]);

  // Wait for the user to stop typing before asking the server for one driver's laps.
  useEffect(() => {
    const t = setTimeout(() => setDriver(driverInput.trim()), 400);
    return () => clearTimeout(t);
  }, [driverInput]);

  const load = useCallback(async () => {
    if (!gp) return;
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    setVisible(PAGE_SIZE);
    try {
      // Two payload shapes come back and they use different units: stored laps
      // are a flat array with snake_case keys in MILLISECONDS (`lap_time_ms`),
      // while the live fallback is `{ laps: [...] }` with PascalCase keys already
      // in SECONDS (`LapTime`). Normalise both to seconds.
      const raw = await backendApi.getSessionLaps(year, gp, 'R', driver || undefined);
      if (id !== requestId.current) return;
      const apiError: string | undefined = (raw as any)?.error;
      if (apiError && !/no laps/i.test(apiError)) throw new Error(apiError);
      const rows: any[] = Array.isArray(raw) ? raw : (raw as any).laps ?? [];
      const num = (v: any) => (v != null && !isNaN(Number(v)) ? Number(v) : null);
      const toSeconds = (ms: any, sec: any) => {
        const m = num(ms);
        if (m !== null) return m / 1000;
        return num(sec) ?? 0;
      };
      setLaps(rows.map((r: any) => ({
        Driver:    r.driver_name ?? r.Driver ?? r.driver_id ?? '',
        LapNumber: String(Math.round(num(r.lap_number ?? r.LapNumber) ?? 0) || ''),
        LapTime:   toSeconds(r.lap_time_ms, r.LapTime),
        Sector1:   toSeconds(r.sector1_ms, r.Sector1),
        Sector2:   toSeconds(r.sector2_ms, r.Sector2),
        Sector3:   toSeconds(r.sector3_ms, r.Sector3),
        PitIn:     r.pit ?? r.PitIn  ?? false,
        PitOut:    r.pit ?? r.PitOut ?? false,
      })));
    } catch (err) {
      if (id !== requestId.current) return;
      setLaps(null);
      setError(err instanceof Error ? err.message : 'Failed to load lap data');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [year, gp, driver]);

  useEffect(() => { load(); }, [load]);

  const timed = useMemo(() => (laps ?? []).filter((l) => !isNaN(l.LapTime) && l.LapTime > 0), [laps]);
  const fastestLap = useMemo(
    () => timed.reduce<LapDataItem | null>((best, l) => (!best || l.LapTime < best.LapTime ? l : best), null),
    [timed],
  );
  const stats = useMemo(() => {
    if (!timed.length) return null;
    const times = timed.map((l) => l.LapTime);
    return {
      fastest: Math.min(...times),
      slowest: Math.max(...times),
      average: times.reduce((s, t) => s + t, 0) / times.length,
    };
  }, [timed]);

  const raceName = schedule.find((r) => gpToken(r.race_name) === gp)?.race_name ?? `${gp} Grand Prix`;

  return (
    <PageShell>
      <PageHeader title="Lap Data" subtitle="Race lap times and sector splits" />

      <FilterBar>
        <SelectField label="Year" value={year} onChange={(v) => setYear(Number(v))}>
          {YEAR_OPTIONS.map((y) => <option key={y} value={y}>{y}</option>)}
        </SelectField>
        <SelectField label="Grand Prix" value={gp} onChange={setGp} className="min-w-[260px]" disabled={schedule.length === 0}>
          {schedule.length === 0 && <option value="">No calendar for {year}</option>}
          {schedule.map((r) => (
            <option key={r.round} value={gpToken(r.race_name)}>
              Round {r.round} — {showCircuitName ? r.circuit_name : r.race_name}
            </option>
          ))}
        </SelectField>
        <TextField label="Driver" value={driverInput} onChange={(v) => setDriverInput(v.toUpperCase())}
          placeholder="Code, e.g. VER" className="min-w-[160px]" />
        <CheckboxField label="Circuit name" checked={showCircuitName} onChange={setShowCircuitName} />
      </FilterBar>

      <FadeIn className="space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Fastest Lap" loading={loading && !stats} icon={<Trophy className="h-6 w-6" />} accent="text-yellow-400"
            value={stats ? formatLapTime(stats.fastest) : '—'}
            sub={fastestLap ? `Lap ${fastestLap.LapNumber} · ${fastestLap.Driver}` : undefined} />
          <StatCard label="Average Lap" loading={loading && !stats} icon={<Clock className="h-6 w-6" />}
            value={stats ? formatLapTime(stats.average) : '—'} sub={stats ? `${timed.length} timed laps` : undefined} />
          <StatCard label="Slowest Lap" loading={loading && !stats} icon={<BarChart3 className="h-6 w-6" />} accent="text-turbo-teal"
            value={stats ? formatLapTime(stats.slowest) : '—'} />
          <StatCard label="Lap Spread" loading={loading && !stats} icon={<Timer className="h-6 w-6" />} accent="text-pit-stop-yellow"
            value={stats ? `${(stats.slowest - stats.fastest).toFixed(3)}s` : '—'} sub="Slowest minus fastest" />
        </div>

        <Card>
          <CardHeader
            title={gp ? `${year} ${raceName} — Laps` : 'Laps'}
            icon={<Clock className="h-4 w-4" />}
            subtitle={laps && laps.length ? `${laps.length} laps${driver ? ` · ${driver}` : ''}` : undefined}
          />
          {loading ? <LoadingState label="Loading lap data — a race that hasn't been opened before can take up to a minute…" /> : error ? (
            <ErrorState title="Couldn't load lap data" message={error} onRetry={load} />
          ) : laps && laps.length ? (
            <>
              <TableWrap>
                <thead>
                  <tr className="border-b border-gray-800">
                    <Th>Lap</Th><Th>Driver</Th><Th align="right">Lap time</Th>
                    <Th align="right">S1</Th><Th align="right">S2</Th><Th align="right">S3</Th><Th align="center">Pit</Th>
                  </tr>
                </thead>
                <tbody>
                  {laps.slice(0, visible).map((lap) => {
                    const isFastest = lap === fastestLap;
                    return (
                      <Tr key={`${lap.Driver}-${lap.LapNumber}`} className={isFastest ? 'bg-yellow-500/10' : ''}>
                        <Td className="font-semibold text-white">{lap.LapNumber}</Td>
                        <Td className="text-white">{lap.Driver}</Td>
                        <Td align="right" className={isFastest ? 'font-bold text-yellow-400' : 'text-white'}>{formatLapTime(lap.LapTime)}</Td>
                        <Td align="right" className="text-gray-400">{formatSector(lap.Sector1)}</Td>
                        <Td align="right" className="text-gray-400">{formatSector(lap.Sector2)}</Td>
                        <Td align="right" className="text-gray-400">{formatSector(lap.Sector3)}</Td>
                        <Td align="center">
                          {lap.PitIn || lap.PitOut
                            ? <span className="rounded bg-orange-500/15 px-2 py-0.5 text-xs font-medium text-orange-400">PIT</span>
                            : <span className="text-gray-600">—</span>}
                        </Td>
                      </Tr>
                    );
                  })}
                </tbody>
              </TableWrap>
              {laps.length > visible && (
                <div className="flex items-center justify-between border-t border-gray-800 px-5 py-3 text-sm text-gray-500">
                  <span>Showing {visible} of {laps.length} laps</span>
                  <Button variant="secondary" onClick={() => setVisible((v) => v + PAGE_SIZE)}>Show more</Button>
                </div>
              )}
            </>
          ) : (
            <EmptyState icon={<Clock className="h-10 w-10" />} title="No lap data for this race yet"
              message="Lap-by-lap timing hasn't been loaded for this race." />
          )}
        </Card>
      </FadeIn>
    </PageShell>
  );
};

export default LapData;
