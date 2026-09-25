import React, { useCallback, useMemo } from 'react';
import { Flag } from 'lucide-react';
import { backendApi, ConstructorStanding } from '../services/backendApi';
import {
  Card, CardHeader, EmptyState, ErrorState, FadeIn, LoadingState, PositionBadge, TableWrap, TeamChip, Td, Th, Tr, teamColor,
} from './ui';
import { STAT_COLUMNS, StatColumn, StatColumnsMenu, statsNote, statValue, useResultStats, useStatColumns } from './statColumns';

/** The Teams tab: constructor standings with the same optional win/podium columns as the Drivers
 *  tab. The standings are loaded by the Dashboard (the Overview uses them too). */
const ConstructorAnalytics: React.FC<{
  year: number;
  teams: ConstructorStanding[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}> = ({ year, teams, loading, error, onRetry }) => {
  const [columns, setColumns] = useStatColumns();
  const wantStats = columns.length > 0;
  const fetchStats = useCallback((y: number) => backendApi.getConstructorStats(y), []);
  const { stats, state: statsState, reload } = useResultStats(fetchStats, year, wantStats);

  // Team ids are the same in the standings and the stored results (red_bull, rb, audi, ...).
  const byId = useMemo(() => new Map((stats?.constructors ?? []).map((t) => [t.constructor_id, t])), [stats]);
  const statCell = (t: ConstructorStanding, col: StatColumn) =>
    statValue(stats ? byId.get(t.constructor_id)?.[col] : undefined, statsState === 'loading' || !stats);
  const note = statsNote(wantStats, stats, statsState, stats !== null && stats.constructors.length === 0, year, reload,
    columns.some((c) => c.endsWith('podiums')) ? ' Podiums count every car on the podium, so a one-two is two.' : '');
  const shown = STAT_COLUMNS.filter((c) => columns.includes(c.id));

  return (
    <FadeIn>
      <Card>
        <CardHeader
          title={`Constructor Standings — ${year}`}
          icon={<Flag className="h-4 w-4" />}
          subtitle={note}
          action={<StatColumnsMenu columns={columns} onChange={setColumns} />}
        />
        {loading ? <LoadingState /> : error ? (
          <ErrorState title="Couldn't load constructor standings" message={error} onRetry={onRetry} />
        ) : teams.length ? (
          <TableWrap>
            <thead>
              <tr className="border-b border-gray-800">
                <Th className="w-14">Pos</Th>
                <Th>Constructor</Th>
                {shown.map((c) => <Th key={c.id} align="right">{c.short}</Th>)}
                <Th align="right">Points</Th>
              </tr>
            </thead>
            <tbody>
              {teams.map((t) => (
                <Tr key={t.constructor_id}>
                  <Td><PositionBadge position={t.position} /></Td>
                  <Td className="font-medium text-white"><TeamChip name={t.constructor_name} /></Td>
                  {shown.map((c) => (
                    <Td key={c.id} align="right" className="tabular-nums text-gray-300">{statCell(t, c.id)}</Td>
                  ))}
                  <Td align="right">
                    <span className="flex items-center justify-end gap-3">
                      <span className="hidden h-1.5 w-28 overflow-hidden rounded bg-gray-800 sm:block" aria-hidden="true">
                        <span
                          className="block h-full rounded"
                          style={{
                            width: `${teams[0]?.points ? (t.points / teams[0].points) * 100 : 0}%`,
                            backgroundColor: teamColor(t.constructor_name),
                          }}
                        />
                      </span>
                      <span className="w-12 font-bold text-white">{t.points}</span>
                    </span>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </TableWrap>
        ) : <EmptyState title="No constructor standings available" />}
      </Card>
    </FadeIn>
  );
};

export default ConstructorAnalytics;
