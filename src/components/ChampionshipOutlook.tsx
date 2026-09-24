import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Flag, Info, Trophy, Users } from 'lucide-react';
import {
  backendApi, ChampionshipBacktest, ChampionshipBacktestSummary, ChampionshipOutlook as Outlook, ChampionshipRow,
} from '../services/backendApi';
import {
  Card, CardBody, CardHeader, EmptyState, ErrorState, FadeIn, LoadingState, Notice, Pill, PositionBadge,
  TabPanel, Tabs, TableWrap, TeamChip, Td, Th, Tr, teamColor,
} from './ui';

type View = 'drivers' | 'constructors';
const VIEWS: { id: View; label: string; icon: React.ReactNode }[] = [
  { id: 'drivers', label: 'Drivers', icon: <Users className="h-4 w-4" /> },
  { id: 'constructors', label: 'Constructors', icon: <Flag className="h-4 w-4" /> },
];

/** "38%", "<1%", ">99%" — a simulation can't honestly claim more precision than that. */
export function formatChance(p: number): string {
  if (p <= 0) return '0%';
  if (p < 0.01) return '<1%';
  if (p > 0.99 && p < 1) return '>99%';
  return `${Math.round(p * 100)}%`;
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** Most likely final position and its chance. */
function likeliestFinish(row: ChampionshipRow): [number, number] | null {
  const probs = row.position_probabilities;
  if (!probs?.length) return null;
  let best = 0;
  probs.forEach((p, i) => { if (p > probs[best]) best = i; });
  return [best + 1, probs[best]];
}

const StatusBanner: React.FC<{ outlook: Outlook; kind: View }> = ({ outlook, kind }) => {
  const title = kind === 'drivers' ? "Drivers' title" : "Constructors' title";
  const leader = outlook.standings[0];
  const left = outlook.remaining.length;

  if (outlook.status === 'finished') {
    return <Notice tone="info">{title}: <strong className="text-white">{outlook.champion ?? leader?.name}</strong> won the {outlook.year} championship.</Notice>;
  }
  if (outlook.clinched) {
    return (
      <Notice tone="info">
        <strong className="text-white">{outlook.champion}</strong> {kind === 'drivers' ? 'is' : 'are'} the {outlook.year} champion
        {kind === 'constructors' ? 's' : ''} — clinched with {plural(left, 'round')} to go.
      </Notice>
    );
  }
  if (outlook.status === 'pre_season' || !leader) {
    return <Notice tone="info">The {outlook.year} season hasn't started, so this is a projection from last season's form and the full calendar.</Notice>;
  }
  const hint = outlook.next_race_clinch;
  return (
    <Notice tone="info">
      {leader.name} lead{kind === 'drivers' ? 's' : ''} after {plural(outlook.rounds_completed, 'round')}. {plural(left, 'round')} left,
      with up to {outlook.max_points_remaining} points still available to {kind === 'drivers' ? 'a driver' : 'a team'}.
      {hint && (
        hint.margin_needed > 0
          ? <> {leader.name} can clinch it at the {hint.race_name} by outscoring {hint.rival_name} by {hint.margin_needed} or more points.</>
          : <> {leader.name} clinches it at the {hint.race_name} unless {hint.rival_name} outscores them by {1 - hint.margin_needed} or more.</>
      )}
    </Notice>
  );
};

const ChanceBar: React.FC<{ p: number; color: string }> = ({ p, color }) => (
  <span className="flex items-center justify-end gap-3">
    <span className="hidden h-1.5 w-24 overflow-hidden rounded bg-gray-800 sm:block" aria-hidden="true">
      <span className="block h-full rounded" style={{ width: `${Math.max(p * 100, p > 0 ? 2 : 0)}%`, backgroundColor: color }} />
    </span>
    <span className="w-10 font-bold tabular-nums text-white">{formatChance(p)}</span>
  </span>
);

const OutlookTable: React.FC<{ outlook: Outlook; kind: View }> = ({ outlook, kind }) => {
  const decided = outlook.status === 'finished';
  return (
    <TableWrap>
      <thead>
        <tr className="border-b border-gray-800">
          <Th className="w-14">Pos</Th>
          <Th>{kind === 'drivers' ? 'Driver' : 'Constructor'}</Th>
          <Th align="right">Points</Th>
          {!decided && <Th align="right" className="hidden md:table-cell">Projected</Th>}
          {!decided && <Th align="right" className="hidden lg:table-cell">Likeliest finish</Th>}
          {!decided && <Th align="right">Title chance</Th>}
        </tr>
      </thead>
      <tbody>
        {outlook.standings.map((row) => {
          const finish = likeliestFinish(row);
          const color = teamColor(kind === 'drivers' ? row.team : row.name);
          const eliminated = !row.alive && !outlook.clinched && !decided && outlook.status !== 'pre_season';
          return (
            <Tr key={row.id}>
              <Td><PositionBadge position={row.position} /></Td>
              <Td>
                {kind === 'drivers' ? (
                  <>
                    <span className="block font-medium text-white">{row.name}</span>
                    <span className="flex items-center gap-2 text-xs text-gray-500">
                      {row.team ? <TeamChip name={row.team} /> : null}
                    </span>
                  </>
                ) : <span className="font-medium text-white"><TeamChip name={row.name} /></span>}
                {eliminated && <span className="mt-1 block"><Pill tone="neutral">Out of contention</Pill></span>}
                {outlook.clinched && row.position === 1 && <span className="mt-1 block"><Pill tone="good">Champion</Pill></span>}
              </Td>
              <Td align="right" className="font-bold tabular-nums text-white">{row.points}</Td>
              {!decided && (
                <Td align="right" className="hidden tabular-nums text-gray-300 md:table-cell">
                  {Math.round(row.projected_points)}
                  {row.points_p90 > row.points_p10 && (
                    <span className="block text-xs text-gray-500">{Math.round(row.points_p10)}–{Math.round(row.points_p90)}</span>
                  )}
                </Td>
              )}
              {!decided && (
                <Td align="right" className="hidden tabular-nums text-gray-300 lg:table-cell">
                  {finish ? <>P{finish[0]} <span className="text-xs text-gray-500">({formatChance(finish[1])})</span></> : '—'}
                </Td>
              )}
              {!decided && (
                <Td align="right">
                  {eliminated ? <span className="text-gray-600">—</span> : <ChanceBar p={row.title_probability} color={color} />}
                </Td>
              )}
            </Tr>
          );
        })}
      </tbody>
    </TableWrap>
  );
};

const HowItWorks: React.FC<{ outlook: Outlook; kind: View; backtest: ChampionshipBacktest | null }> = ({ outlook, kind, backtest }) => {
  const summary = (kind === 'drivers' ? backtest?.drivers : backtest?.constructors) as ChampionshipBacktestSummary | undefined;
  const years = backtest?.seasons.map((s) => s.year) ?? [];
  const pct = (x: number) => `${Math.round(x * 100)}%`;
  return (
    <Card>
      <CardHeader title="How this is worked out" icon={<Info className="h-4 w-4" />} />
      <CardBody className="space-y-3 text-sm leading-relaxed text-gray-400">
        <p>
          <strong className="text-gray-200">Who can still win</strong> is exact: a {kind === 'drivers' ? 'driver' : 'team'} is out of
          contention once, even scoring the maximum in every remaining round
          ({kind === 'drivers' ? '25 a race, 33 on a sprint weekend' : '43 for a one-two, 58 on a sprint weekend'}) while the leader
          scores nothing, they couldn't finish ahead. Ties go to the most wins, then second places, and so on.
        </p>
        <p>
          <strong className="text-gray-200">Chances and projected points</strong> come from playing the rest of the season out
          {outlook.method.simulations ? ` ${outlook.method.simulations.toLocaleString()} times` : ''}. Each race's order is drawn from
          the race-prediction model, tuned on {outlook.method.calibration_races} real races the model hadn't seen, and each run gives
          every driver a season-long form swing so one quick car can't look like a certainty. The range under projected points covers
          the middle 80% of runs. {kind === 'constructors' && 'Team totals add up both cars from the same simulated races, so they always match the drivers\' view.'}
        </p>
        {!outlook.sprint_calendar_known && (
          <p className="text-yellow-300">The race calendar couldn't be loaded, so no sprint points are counted for the rounds still to run.</p>
        )}
        {summary && summary.checkpoints ? (
          <p>
            <strong className="text-gray-200">Track record:</strong> replaying {years.join(', ')} round by round (each season with a
            model trained only on earlier ones), it named the eventual champion {pct(summary.champion_accuracy)} of the time — simply
            backing whoever led at that point was right {pct(summary.leader_accuracy)} of the time — and gave the real champion an
            average {pct(summary.mean_p_actual_champion)} chance. That's {plural(years.length, 'season')}, so treat it as a rough guide.
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
};

const ChampionshipOutlook: React.FC<{ year: number }> = ({ year }) => {
  const [params, setParams] = useSearchParams();
  const view: View = params.get('view') === 'constructors' ? 'constructors' : 'drivers';
  const setView = (v: View) => {
    const p = new URLSearchParams(params);
    if (v === 'drivers') p.delete('view');
    else p.set('view', v);
    setParams(p, { replace: true });
  };

  const [outlook, setOutlook] = useState<Outlook | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [backtest, setBacktest] = useState<ChampionshipBacktest | null>(null);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const data = await backendApi.getChampionshipOutlook(view, year);
      if (id === requestId.current) setOutlook(data);
    } catch (e) {
      if (id === requestId.current) setError(e instanceof Error ? e.message : 'The prediction service did not respond.');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [view, year]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    let cancelled = false;
    backendApi.getChampionshipBacktest().then((b) => { if (!cancelled) setBacktest(b); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  const empty = outlook && outlook.standings.length === 0;

  return (
    <FadeIn className="space-y-6">
      <Tabs tabs={VIEWS} active={view} onChange={setView} label="Championship" idPrefix="title" />
      <TabPanel id={view} idPrefix="title">
        <div className="space-y-6">
          {loading ? <LoadingState label="Playing out the rest of the season…" /> : error ? (
            <ErrorState title="Couldn't load the championship outlook" message={error} onRetry={load} />
          ) : !outlook || empty ? (
            <EmptyState
              icon={<Trophy className="h-10 w-10" />}
              title={`No title race to show for ${year}`}
              message="The outlook is worked out from stored race results, which start in 2022."
            />
          ) : (
            <>
              <StatusBanner outlook={outlook} kind={view} />
              <Card>
                <CardHeader
                  title={`${view === 'drivers' ? "Drivers'" : "Constructors'"} Championship — ${year}`}
                  icon={<Trophy className="h-4 w-4" />}
                  subtitle={outlook.status === 'finished'
                    ? 'Final standings'
                    : `After round ${outlook.rounds_completed} of ${outlook.rounds_total} · sorted by the current table`}
                />
                <OutlookTable outlook={outlook} kind={view} />
              </Card>
              {outlook.status !== 'finished' && <HowItWorks outlook={outlook} kind={view} backtest={backtest} />}
            </>
          )}
        </div>
      </TabPanel>
    </FadeIn>
  );
};

export default ChampionshipOutlook;
