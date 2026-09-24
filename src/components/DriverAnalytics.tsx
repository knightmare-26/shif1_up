import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Award, Columns3, TrendingUp, Users } from 'lucide-react';
import { backendApi, DriverResultStats, DriverStanding, DriverStatsResponse } from '../services/backendApi';
import {
  Card, CardHeader, CheckboxMenu, EmptyState, ErrorState, FadeIn, LoadingState, PositionBadge, StatCard,
  TableWrap, TeamChip, Td, Th, Tr,
} from './ui';

const clean = (v?: string | null) => (!v || v === 'Unavailable' ? '—' : v);
const teamOf = (d: DriverStanding) => (typeof d.constructor === 'string' ? d.constructor : '');

// Optional columns, off by default. The standings feed has no podiums and doesn't split sprint
// from race wins, so these come from GET /api/driver-stats (the stored results, 2022 onwards).
export const STAT_COLUMNS = [
  { id: 'race_wins', label: 'Race wins', short: 'Wins' },
  { id: 'race_podiums', label: 'Race podiums', short: 'Podiums' },
  { id: 'sprint_wins', label: 'Sprint wins', short: 'Sprint wins' },
  { id: 'sprint_podiums', label: 'Sprint podiums', short: 'Sprint podiums' },
] as const;
type StatColumn = typeof STAT_COLUMNS[number]['id'];
const STAT_IDS: string[] = STAT_COLUMNS.map((c) => c.id);

/** Accent- and case-insensitive name, so "Nico Hülkenberg" (standings) matches "Nico Hulkenberg" (results). */
const nameKey = (name?: string | null) =>
  (name ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z ]/g, '').trim();
const lastName = (name?: string | null) => nameKey(name).split(' ').pop() ?? '';

/** Find a standings row's stats: by driver code when the API gave one, else by full name, else by
 *  a surname only one driver has ("Kimi Antonelli" vs "Andrea Kimi Antonelli"). */
export function statsMatcher(stats: DriverResultStats[]) {
  const byCode = new Map(stats.map((s) => [s.code.toUpperCase(), s]));
  const byName = new Map(stats.map((s) => [nameKey(s.driver_name), s]));
  const surnames = new Map<string, DriverResultStats | null>();
  stats.forEach((s) => {
    const key = lastName(s.driver_name);
    surnames.set(key, surnames.has(key) ? null : s); // null = ambiguous
  });
  return (d: DriverStanding): DriverResultStats | undefined =>
    (d.code ? byCode.get(d.code.toUpperCase()) : undefined)
    ?? byName.get(nameKey(d.driver_name))
    ?? surnames.get(lastName(d.driver_name))
    ?? undefined;
}

const DriverAnalytics: React.FC<{ year: number }> = ({ year }) => {
  const [drivers, setDrivers] = useState<DriverStanding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  // The chosen columns live in the URL (?cols=race_wins,sprint_podiums) like the Dashboard's other state.
  const [params, setParams] = useSearchParams();
  const columns = (params.get('cols') ?? '').split(',').filter((c): c is StatColumn => STAT_IDS.includes(c));
  const setColumns = (next: string[]) => {
    const p = new URLSearchParams(params);
    if (next.length) p.set('cols', next.join(','));
    else p.delete('cols');
    setParams(p, { replace: true });
  };

  const [stats, setStats] = useState<DriverStatsResponse | null>(null);
  const [statsState, setStatsState] = useState<'idle' | 'loading' | 'error'>('idle');
  const statsRequest = useRef(0);
  const wantStats = columns.length > 0;

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

  // Only fetched once a stats column is switched on.
  const loadStats = useCallback(async () => {
    const id = ++statsRequest.current;
    setStatsState('loading');
    try {
      const data = await backendApi.getDriverStats(year);
      if (id !== statsRequest.current) return;
      setStats(data);
      setStatsState('idle');
    } catch {
      if (id === statsRequest.current) setStatsState('error');
    }
  }, [year]);

  useEffect(() => {
    setStats(null);
    if (wantStats) loadStats();
  }, [wantStats, loadStats]);

  const findStats = useMemo(() => statsMatcher(stats?.drivers ?? []), [stats]);
  const noStatsForSeason = stats !== null && stats.drivers.length === 0;

  const leader = drivers[0];
  const mostWins = drivers.reduce<DriverStanding | undefined>(
    (best, d) => (!best || d.wins > best.wins ? d : best), undefined,
  );

  const statCell = (d: DriverStanding, col: StatColumn) => {
    if (statsState === 'loading' || !stats) return <span className="text-gray-600">…</span>;
    const s = findStats(d);
    return s ? s[col] : <span className="text-gray-600">—</span>;
  };

  let statsNote: React.ReactNode = null;
  if (wantStats) {
    if (statsState === 'error') {
      statsNote = (
        <>Couldn't load wins and podiums. <button type="button" onClick={loadStats} className="text-racing-red underline">Try again</button></>
      );
    } else if (noStatsForSeason) {
      statsNote = `Wins and podiums are counted from stored race results, which start in 2022 — not available for ${year}.`;
    } else if (stats) {
      statsNote = `Wins and podiums counted from ${stats.races_counted} ${stats.races_counted === 1 ? 'race' : 'races'}`
        + `${stats.sprints_counted ? ` and ${stats.sprints_counted} ${stats.sprints_counted === 1 ? 'sprint' : 'sprints'}` : ''}.`;
    }
  }

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
        <CardHeader
          title={`Driver Standings — ${year}`}
          icon={<Users className="h-4 w-4" />}
          subtitle={statsNote}
          action={(
            <CheckboxMenu
              label="Columns"
              icon={<Columns3 className="h-4 w-4" aria-hidden="true" />}
              options={STAT_COLUMNS.map(({ id, label }) => ({ id, label }))}
              selected={columns}
              onChange={setColumns}
            />
          )}
        />
        {loading ? <LoadingState label="Loading driver standings…" /> : error ? (
          <ErrorState title="Couldn't load driver standings" message={error} onRetry={load} />
        ) : drivers.length ? (
          <TableWrap>
            <thead>
              <tr className="border-b border-gray-800">
                <Th className="w-14">Pos</Th>
                <Th>Driver</Th>
                <Th className="hidden sm:table-cell">Team</Th>
                {STAT_COLUMNS.filter((c) => columns.includes(c.id)).map((c) => (
                  <Th key={c.id} align="right">{c.short}</Th>
                ))}
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
                  {STAT_COLUMNS.filter((c) => columns.includes(c.id)).map((c) => (
                    <Td key={c.id} align="right" className="tabular-nums text-gray-300">{statCell(d, c.id)}</Td>
                  ))}
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
