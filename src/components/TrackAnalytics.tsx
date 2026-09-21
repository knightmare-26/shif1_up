import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Calendar, Flag, MapPin } from 'lucide-react';
import { backendApi, RaceEvent } from '../services/backendApi';
import { getTrackFacts } from '../data/trackFacts';
import { describeDaysUntil, daysUntil, formatDate, isPastDate } from '../utils/dates';
import { isRaceRound } from '../utils/races';
import {
  Card, CardHeader, EmptyState, ErrorState, FadeIn, LoadingState, StatCard, TableWrap, Td, Th, Tr,
} from './ui';

type Status = 'completed' | 'next' | 'upcoming';

const STATUS_STYLES: Record<Status, string> = {
  completed: 'border-gray-700 text-gray-500',
  next: 'border-racing-red/50 bg-racing-red/10 text-racing-red',
  upcoming: 'border-gray-700 text-gray-300',
};
const STATUS_LABEL: Record<Status, string> = { completed: 'Completed', next: 'Next', upcoming: 'Upcoming' };

const TrackAnalytics: React.FC<{ year: number }> = ({ year }) => {
  const [schedule, setSchedule] = useState<RaceEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const data = await backendApi.getRaceSchedule(year);
      if (id === requestId.current) setSchedule(Array.isArray(data) ? data.filter(isRaceRound) : []);
    } catch (e) {
      if (id === requestId.current) setError(e instanceof Error ? e.message : 'The schedule service did not respond.');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [year]);

  useEffect(() => { load(); }, [load]);

  const nextRace = schedule.find((r) => !isPastDate(r.date));
  const remaining = schedule.filter((r) => !isPastDate(r.date)).length;
  const countries = new Set(schedule.map((r) => r.country)).size;
  const nextIn = nextRace ? daysUntil(nextRace.date) : null;

  const statusOf = (r: RaceEvent): Status =>
    isPastDate(r.date) ? 'completed' : r === nextRace ? 'next' : 'upcoming';

  return (
    <FadeIn className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Races" loading={loading} icon={<Flag className="h-6 w-6" />}
          value={schedule.length || '—'} sub={`${year} World Championship`} />
        <StatCard label="Countries" loading={loading} icon={<MapPin className="h-6 w-6" />} accent="text-turbo-teal"
          value={countries || '—'} sub="Host nations this season" />
        <StatCard label="Remaining" loading={loading} icon={<Calendar className="h-6 w-6" />} accent="text-pit-stop-yellow"
          value={schedule.length ? remaining : '—'}
          sub={nextRace ? `Next: ${nextRace.race_name.replace(' Grand Prix', '')} · ${describeDaysUntil(nextIn)}` : 'Season complete'} />
      </div>

      <Card>
        <CardHeader title={`${year} Race Calendar`} icon={<MapPin className="h-4 w-4" />} />
        {loading ? <LoadingState label="Loading race calendar…" /> : error ? (
          <ErrorState title="Couldn't load the race calendar" message={error} onRetry={load} />
        ) : schedule.length ? (
          <TableWrap>
            <thead>
              <tr className="border-b border-gray-800">
                <Th className="w-16">Round</Th>
                <Th>Grand Prix</Th>
                <Th>Date</Th>
                <Th align="right" className="hidden md:table-cell">Length</Th>
                <Th align="right" className="hidden md:table-cell">Corners</Th>
                <Th className="hidden lg:table-cell">Lap record</Th>
                <Th align="right">Status</Th>
              </tr>
            </thead>
            <tbody>
              {schedule.map((r) => {
                const facts = getTrackFacts(r.location);
                const status = statusOf(r);
                return (
                  <Tr key={r.round} className={status === 'next' ? 'bg-racing-red/5' : ''}>
                    <Td className={`font-bold ${status === 'next' ? 'text-racing-red' : 'text-gray-500'}`}>R{r.round}</Td>
                    <Td>
                      <span className={`block font-medium ${status === 'completed' ? 'text-gray-300' : 'text-white'}`}>{r.race_name}</span>
                      <span className="block text-xs text-gray-500">{r.circuit_name} · {r.country}</span>
                    </Td>
                    <Td className="whitespace-nowrap text-gray-300">{formatDate(r.date)}</Td>
                    <Td align="right" className="hidden text-gray-300 md:table-cell">{facts?.length ?? '—'}</Td>
                    <Td align="right" className="hidden text-gray-300 md:table-cell">{facts?.corners ?? '—'}</Td>
                    <Td className="hidden lg:table-cell">
                      {facts?.record ? (
                        <>
                          <span className="block text-gray-200">{facts.record.time}</span>
                          <span className="block text-xs text-gray-500">{facts.record.holder} ({facts.record.year})</span>
                        </>
                      ) : <span className="text-gray-600">—</span>}
                    </Td>
                    <Td align="right">
                      <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}>
                        {STATUS_LABEL[status]}
                      </span>
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </TableWrap>
        ) : <EmptyState icon={<Calendar className="h-10 w-10" />} title={`No calendar published for ${year}`} />}
      </Card>
    </FadeIn>
  );
};

export default TrackAnalytics;
