import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Award, TrendingUp, Users } from 'lucide-react';
import { backendApi, DriverStanding } from '../services/backendApi';
import {
  Card, CardHeader, EmptyState, ErrorState, FadeIn, LoadingState, PositionBadge, StatCard,
  TableWrap, TeamChip, Td, Th, Tr,
} from './ui';

const clean = (v?: string | null) => (!v || v === 'Unavailable' ? '—' : v);
const teamOf = (d: DriverStanding) => (typeof d.constructor === 'string' ? d.constructor : '');

// Podiums are deliberately not shown: the standings source doesn't provide
// them, so every driver would read 0.
const DriverAnalytics: React.FC<{ year: number }> = ({ year }) => {
  const [drivers, setDrivers] = useState<DriverStanding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const data = await backendApi.getDriverStandings(year);
      if (id === requestId.current) setDrivers(Array.isArray(data) ? data : []);
    } catch (e) {
      if (id === requestId.current) setError(e instanceof Error ? e.message : 'The standings service did not respond.');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [year]);

  useEffect(() => { load(); }, [load]);

  const leader = drivers[0];
  const mostWins = drivers.reduce<DriverStanding | undefined>(
    (best, d) => (!best || d.wins > best.wins ? d : best), undefined,
  );

  return (
    <FadeIn className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <StatCard
          label="Season Leader" loading={loading} icon={<TrendingUp className="h-6 w-6" />}
          value={leader ? leader.driver_name : '—'}
          sub={leader ? `${leader.points} pts · ${leader.wins} ${leader.wins === 1 ? 'win' : 'wins'}` : undefined}
        />
        <StatCard
          label="Most Wins" loading={loading} icon={<Award className="h-6 w-6" />} accent="text-turbo-teal"
          value={mostWins && mostWins.wins > 0 ? mostWins.wins : '—'}
          sub={mostWins && mostWins.wins > 0 ? mostWins.driver_name : 'No wins yet'}
        />
      </div>

      <Card>
        <CardHeader title={`Driver Standings — ${year}`} icon={<Users className="h-4 w-4" />} />
        {loading ? <LoadingState label="Loading driver standings…" /> : error ? (
          <ErrorState title="Couldn't load driver standings" message={error} onRetry={load} />
        ) : drivers.length ? (
          <TableWrap>
            <thead>
              <tr className="border-b border-gray-800">
                <Th className="w-14">Pos</Th>
                <Th>Driver</Th>
                <Th className="hidden sm:table-cell">Team</Th>
                <Th align="right">Wins</Th>
                <Th align="right">Points</Th>
              </tr>
            </thead>
            <tbody>
              {drivers.map((d) => (
                <Tr key={d.driver_id}>
                  <Td><PositionBadge position={d.position} /></Td>
                  <Td>
                    <span className="block font-medium text-white">{clean(d.driver_name)}</span>
                    <span className="block text-xs text-gray-500">
                      {d.number ? `#${d.number} · ` : ''}{clean(d.nationality)}
                    </span>
                  </Td>
                  <Td className="hidden text-gray-300 sm:table-cell"><TeamChip name={teamOf(d)} /></Td>
                  <Td align="right" className="text-gray-400">{d.wins}</Td>
                  <Td align="right" className="font-bold text-white">{d.points}</Td>
                </Tr>
              ))}
            </tbody>
          </TableWrap>
        ) : <EmptyState icon={<Users className="h-10 w-10" />} title="No driver standings for this season yet" />}
      </Card>
    </FadeIn>
  );
};

export default DriverAnalytics;
