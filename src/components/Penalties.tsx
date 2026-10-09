import React from 'react';
import { Gavel } from 'lucide-react';
import { DriverPenalties, GridChange, SessionPenalties, StewardsDecision } from '../services/backendApi';
import { Card, CardHeader, Notice, Pill, TableWrap, Td, Th, Tr } from './ui';

/** Sessions whose stewards' decisions are shown with the results. */
export const PENALTY_SESSIONS = ['R', 'S', 'Q', 'SQ'];
/** OpenF1's race-control data, which the decisions come from, starts in 2023. */
export const FIRST_PENALTY_SEASON = 2023;

const KIND_LABEL: Record<StewardsDecision['kind'], (d: StewardsDecision) => string> = {
  time: (d) => `${d.seconds}s time penalty`,
  stop_go: (d) => (d.seconds ? `${d.seconds}s stop-and-go penalty` : 'Stop-and-go penalty'),
  drive_through: () => 'Drive-through penalty',
  grid: (d) => `${d.places}-place grid penalty`,
  disqualified: () => 'Disqualified',
  black_and_white: () => 'Black-and-white flag',
  reprimand: () => 'Reprimand',
  warning: () => 'Warning',
};

/** "Lap 12 · 5s time penalty: Speeding in the pit lane (served)" */
export const describeDecision = (d: StewardsDecision): string =>
  [d.lap ? `Lap ${d.lap} · ` : '', KIND_LABEL[d.kind](d), d.reason ? `: ${d.reason}` : '', d.served ? ' (served)' : ''].join('');

const describeGrid = (g: GridChange): string =>
  g.pit_lane ? `Qualified P${g.qualified}, started from the pit lane` : `Qualified P${g.qualified}, started P${g.started}: a grid penalty`;

interface Badge { label: string; tone: 'warn' | 'bad' | 'neutral'; title: string }

/** What to flag next to a driver in the results: penalties first, then flags and deleted laps. */
export function penaltyBadges(code: string, data: SessionPenalties | null, session: string): Badge[] {
  if (!data) return [];
  const key = code.toUpperCase();
  const mine = data.decisions.filter((d) => d.driver === key);
  const lines = (kinds: StewardsDecision['kind'][]) => mine.filter((d) => kinds.includes(d.kind)).map(describeDecision).join('\n');
  const summary: DriverPenalties | undefined = data.drivers[key];
  const grid = data.grid[key];
  const out: Badge[] = [];

  if (grid) {
    out.push(grid.pit_lane
      ? { label: 'Pit-lane start', tone: 'warn', title: describeGrid(grid) }
      : { label: `Grid ↓${(grid.started ?? 0) - grid.qualified}`, tone: 'warn', title: describeGrid(grid) });
  }
  if (!summary) return out;
  if (summary.disqualified) out.push({ label: 'DSQ', tone: 'bad', title: lines(['disqualified']) || 'Disqualified' });
  if (summary.time_penalty_seconds) {
    // Served at a pit stop, a time penalty never reaches the race time; otherwise it's added after.
    const time = mine.filter((d) => d.kind === 'time');
    const added = time.filter((d) => !d.served).reduce((sum, d) => sum + (d.seconds ?? 0), 0);
    const served = time.filter((d) => d.served).reduce((sum, d) => sum + (d.seconds ?? 0), 0);
    out.push({
      label: added ? `+${added}s` : `${served}s served`, tone: added ? 'warn' : 'neutral',
      title: [lines(['time']), added ? `${added}s added to the race time` : 'Served at a pit stop'].join('\n'),
    });
  }
  if (summary.penalties.includes('drive_through')) out.push({ label: 'Drive-through', tone: 'warn', title: lines(['drive_through']) });
  if (summary.penalties.includes('stop_go')) out.push({ label: 'Stop-and-go', tone: 'warn', title: lines(['stop_go']) });
  if (summary.penalties.includes('grid')) out.push({ label: 'Grid penalty (next race)', tone: 'warn', title: lines(['grid']) });
  if (summary.black_and_white) out.push({ label: 'Black-and-white flag', tone: 'neutral', title: lines(['black_and_white']) });
  // A deleted lap decides a qualifying result; in a race it's only a step toward a penalty.
  if ((session === 'Q' || session === 'SQ') && summary.deleted_laps) {
    const laps = data.deleted_laps.filter((d) => d.driver === key);
    out.push({
      label: `${summary.deleted_laps} lap${summary.deleted_laps === 1 ? '' : 's'} deleted`, tone: 'neutral',
      title: laps.map((d) => `${d.lap ? `Lap ${d.lap} · ` : ''}${d.time} deleted: ${d.reason}`).join('\n'),
    });
  }
  return out;
}

export const PenaltyBadges: React.FC<{ code: string; data: SessionPenalties | null; session: string }> = ({ code, data, session }) => {
  const badges = penaltyBadges(code, data, session);
  if (!badges.length) return null;
  return (
    <span className="mt-1 flex flex-wrap gap-1">
      {badges.map((b) => (
        <span key={b.label} title={b.title} className="cursor-help">
          <Pill tone={b.tone}>{b.label}</Pill>
        </span>
      ))}
    </span>
  );
};

/** Every stewards' decision of the session (with the lap), plus who started behind where they qualified. */
export const StewardsCard: React.FC<{ data: SessionPenalties; names: Record<string, string>; sessionLabel: string }> = ({
  data, names, sessionLabel,
}) => {
  const name = (code: string) => names[code] ?? code;
  const grid = Object.entries(data.grid).sort((a, b) => a[1].qualified - b[1].qualified);
  const deleted = Object.entries(data.drivers).filter(([, d]) => d.deleted_laps > 0)
    .sort((a, b) => b[1].deleted_laps - a[1].deleted_laps);

  return (
    <Card>
      <CardHeader
        title={<span className="flex items-center gap-2"><Gavel className="h-4 w-4 text-racing-red" aria-hidden="true" />Stewards' decisions</span>}
        subtitle={`${sessionLabel}: penalties, flags and warnings from race control`}
      />
      {data.stewards === 'locked' && (
        <div className="px-4 pt-4"><Notice tone="info">
          The stewards' decisions are paused while an F1 session is live (the data source shuts until it ends).
        </Notice></div>
      )}
      {data.stewards === 'error' && (
        <div className="px-4 pt-4"><Notice tone="warning">Couldn't load the stewards' decisions right now.</Notice></div>
      )}
      {grid.length > 0 && (
        <p className="border-b border-gray-800 px-4 py-3 text-sm text-gray-300">
          <span className="text-gray-500">Started behind where they qualified: </span>
          {grid.map(([code, g], i) => (
            <span key={code}>{i > 0 && ' · '}{name(code)} {g.pit_lane ? 'from the pit lane' : `P${g.started}`} (qualified P{g.qualified})</span>
          ))}
        </p>
      )}
      {data.decisions.length > 0 ? (
        <TableWrap>
          <thead>
            <tr className="border-b border-gray-800">
              <Th className="w-16">Lap</Th>
              <Th>Driver</Th>
              <Th>Decision</Th>
              <Th>Reason</Th>
            </tr>
          </thead>
          <tbody>
            {data.decisions.map((d, i) => (
              <Tr key={`${d.driver}-${d.kind}-${i}`}>
                <Td className="tabular-nums text-gray-400">{d.lap ?? '—'}</Td>
                <Td className="whitespace-nowrap font-medium text-white">{name(d.driver)}</Td>
                <Td className="whitespace-nowrap">
                  <Pill tone={d.kind === 'disqualified' ? 'bad' : d.kind === 'warning' || d.kind === 'reprimand' || d.kind === 'black_and_white' ? 'neutral' : 'warn'}>
                    {KIND_LABEL[d.kind](d)}
                  </Pill>
                  {d.served && <span className="ml-2 text-xs text-gray-500">served</span>}
                </Td>
                <Td className="text-gray-300">{d.reason || '—'}</Td>
              </Tr>
            ))}
          </tbody>
        </TableWrap>
      ) : data.stewards === 'ok' && (
        <p className="px-4 py-4 text-sm text-gray-400">No penalties, flags or warnings from the stewards in this session.</p>
      )}
      {deleted.length > 0 && (
        <p className="border-t border-gray-800 px-4 py-3 text-xs text-gray-400">
          Lap times deleted (track limits and the like):{' '}
          {deleted.map(([code, d], i) => <span key={code}>{i > 0 && ', '}{name(code)} ×{d.deleted_laps}</span>)}
        </p>
      )}
      <p className="border-t border-gray-800 px-4 py-3 text-xs text-gray-500">
        Grid penalties for new engine parts, or carried over from an earlier race, are announced in FIA documents, not
        race control: they show as starting behind where a driver qualified. A decision taken after the session doesn't
        always reach race control, though its effect is in the results.
      </p>
    </Card>
  );
};
