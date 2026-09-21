import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ListOrdered } from 'lucide-react';
import { backendApi, RaceEvent } from '../services/backendApi';
import { formatDate, isPastDate } from '../utils/dates';
import { gpToken, isRaceRound } from '../utils/races';
import {
  Card, CardHeader, EmptyState, ErrorState, FadeIn, FilterBar, LoadingState, PositionBadge,
  SelectField, TableWrap, TeamChip, Td, Th, Tr,
} from './ui';

const SESSIONS: { id: string; label: string }[] = [
  { id: 'R',   label: 'Race' },
  { id: 'Q',   label: 'Qualifying' },
  { id: 'S',   label: 'Sprint' },
  { id: 'SQ',  label: 'Sprint Qualifying' },
  { id: 'FP1', label: 'Practice 1' },
  { id: 'FP2', label: 'Practice 2' },
  { id: 'FP3', label: 'Practice 3' },
];

interface RaceResult {
  DriverNumber: string;
  BroadcastName: string;
  Abbreviation: string;
  DriverId: string;
  TeamName: string;
  TeamColor: string;
  TeamId: string;
  FirstName: string;
  LastName: string;
  FullName: string;
  HeadshotUrl: string;
  CountryCode: string;
  Position: string;
  ClassifiedPosition: string;
  GridPosition: string;
  Time: number;
  Status: string;
  Points: string;
  Laps: string;
}

interface RaceResultsData {
  year: number;
  gp: string;
  session: string;
  results: RaceResult[];
}

const formatTime = (time: number): string => {
  if (isNaN(time) || time === 0) return '—';
  const minutes = Math.floor(time / 60);
  const seconds = (time % 60).toFixed(3);
  return `${minutes}:${seconds.padStart(6, '0')}`;
};

const initials = (name: string) =>
  name.split(' ').filter(Boolean).map((p) => p[0]).slice(0, 2).join('').toUpperCase();

const RaceResults: React.FC<{ year: number; initialGp?: string }> = ({ year, initialGp }) => {
  const [raceData, setRaceData] = useState<RaceResultsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [schedule, setSchedule] = useState<RaceEvent[]>([]);
  const [scheduleLoaded, setScheduleLoaded] = useState(false);
  const [scheduleFailed, setScheduleFailed] = useState(false);
  const [scheduleTry, setScheduleTry] = useState(0);
  const [selectedGP, setSelectedGP] = useState('');
  const [selectedSession, setSelectedSession] = useState('R');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const requestId = useRef(0);

  // Pick the weekend to show first: a deep-linked one, else the latest that has
  // actually been run (never "pre-season testing", never a future race).
  useEffect(() => {
    let cancelled = false;
    setScheduleLoaded(false);
    setScheduleFailed(false);
    setSelectedGP('');
    setRaceData(null);
    setLoading(true);
    backendApi.getRaceSchedule(year)
      .then((events) => {
        if (cancelled) return;
        const list = (Array.isArray(events) ? events : []).filter(isRaceRound);
        setSchedule(list);
        const linked = initialGp && list.find((r) => gpToken(r.race_name) === initialGp);
        const latest = [...list].reverse().find((r) => isPastDate(r.date)) ?? list[0];
        const pick = linked || latest;
        setScheduleLoaded(true);
        if (pick) setSelectedGP(gpToken(pick.race_name)); // loadRaceResults takes over from here
        else setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setSchedule([]);
        setScheduleLoaded(true);
        setScheduleFailed(true);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [year, initialGp, scheduleTry]);

  const loadRaceResults = useCallback(async () => {
    if (!selectedGP) return;
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    setNotFound(false);
    try {
      const results = await backendApi.getRaceResults(year, selectedGP, selectedSession);
      if (id !== requestId.current) return;

      // Backend returns a flat array; normalise into the expected shape
      const normalized: RaceResultsData = Array.isArray(results)
        ? { year, gp: selectedGP, session: selectedSession, results }
        : results;
      if ((normalized as any).error) throw new Error((normalized as any).error);

      setRaceData(normalized);
      setLastUpdated(new Date());
    } catch (err: any) {
      if (id !== requestId.current) return;
      setRaceData(null);
      if (String(err?.message || '').includes('404')) setNotFound(true);
      else setError(err instanceof Error ? err.message : 'Failed to load race results');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [year, selectedGP, selectedSession]);

  useEffect(() => { loadRaceResults(); }, [loadRaceResults]);

  const selectedScheduleEntry = schedule.find((r) => gpToken(r.race_name) === selectedGP);
  const raceName = selectedScheduleEntry?.race_name ?? `${selectedGP} Grand Prix`;
  const raceDate = selectedScheduleEntry ? formatDate(selectedScheduleEntry.date) : '';
  const sessionLabel = SESSIONS.find((s) => s.id === selectedSession)?.label ?? selectedSession;

  return (
    <FadeIn>
      <FilterBar>
        <SelectField label="Grand Prix" value={selectedGP} onChange={setSelectedGP}
          className="min-w-[260px]" disabled={schedule.length === 0}>
          {schedule.length === 0 && <option value="">{scheduleLoaded ? `No calendar for ${year}` : 'Loading…'}</option>}
          {schedule.map((r) => (
            <option key={r.round} value={gpToken(r.race_name)}>Round {r.round} — {r.race_name}</option>
          ))}
        </SelectField>
        <SelectField label="Session" value={selectedSession} onChange={setSelectedSession} className="min-w-[200px]">
          {SESSIONS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </SelectField>
      </FilterBar>

      <Card>
        <CardHeader
          title={selectedGP ? `${year} ${raceName} — ${sessionLabel}` : 'Race results'}
          icon={<ListOrdered className="h-4 w-4" />}
          subtitle={raceData && !loading
            ? `${raceData.results.length} drivers${lastUpdated ? ` · Updated ${lastUpdated.toLocaleTimeString()}` : ''}`
            : undefined}
        />

        {scheduleFailed ? (
          <ErrorState title="Couldn't load the race calendar"
            message="The server didn't answer. If it was asleep it should be ready in a moment."
            onRetry={() => setScheduleTry((n) => n + 1)} />
        ) : loading ? <LoadingState label="Loading race results…" /> : error ? (
          <ErrorState title="Couldn't load race results" message={error} onRetry={loadRaceResults} />
        ) : notFound ? (
          <EmptyState icon={<ListOrdered className="h-10 w-10" />}
            title={`No ${sessionLabel.toLowerCase()} results for this race`}
            message="This session may not have taken place at this weekend, or hasn't been run yet." />
        ) : raceData && raceData.results.length ? (
          <TableWrap>
            <thead>
              <tr className="border-b border-gray-800">
                <Th>Grand Prix</Th>
                <Th>Date</Th>
                <Th>Positions</Th>
                <Th>Team</Th>
                <Th>Laps</Th>
                <Th>Race Time</Th>
                <Th>Points</Th>
              </tr>
            </thead>
            <tbody>
              {raceData.results.map((result) => (
                <Tr key={result.DriverId}>
                  <Td className="whitespace-nowrap text-gray-300">{raceName}</Td>
                  <Td className="whitespace-nowrap text-gray-300">{raceDate}</Td>
                  <Td>
                    <span className="flex items-center gap-3">
                      <PositionBadge position={result.Position} label={result.ClassifiedPosition} />
                      <span className="relative flex h-9 w-9 flex-shrink-0 items-center justify-center overflow-hidden rounded-full bg-gray-800 text-xs font-bold text-gray-400">
                        {initials(result.FullName)}
                        {result.HeadshotUrl && (
                          <img
                            src={result.HeadshotUrl}
                            alt=""
                            className="absolute inset-0 h-full w-full object-cover"
                            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                          />
                        )}
                      </span>
                      <span className="min-w-0">
                        <span className="block whitespace-nowrap font-medium text-white">{result.FullName}</span>
                        <span className="block text-xs text-gray-500">
                          #{result.DriverNumber}{result.CountryCode ? ` · ${result.CountryCode}` : ''}
                        </span>
                      </span>
                    </span>
                  </Td>
                  <Td className="whitespace-nowrap text-gray-300">
                    <TeamChip name={result.TeamName} color={result.TeamColor ? `#${result.TeamColor}` : undefined} />
                  </Td>
                  <Td className="text-gray-300">{result.Laps || '—'}</Td>
                  <Td className="whitespace-nowrap text-gray-300">{formatTime(result.Time)}</Td>
                  <Td>
                    <span className={`font-bold ${parseFloat(result.Points) > 0 ? 'text-green-400' : 'text-gray-500'}`}>
                      {result.Points}
                    </span>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </TableWrap>
        ) : (
          <EmptyState icon={<ListOrdered className="h-10 w-10" />} title="Pick a Grand Prix to see its results" />
        )}
      </Card>
    </FadeIn>
  );
};

export default RaceResults;
