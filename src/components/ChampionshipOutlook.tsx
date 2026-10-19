import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Lightbulb, Trophy } from 'lucide-react';
import {
  backendApi, ChampionshipBacktest, ChampionshipBacktestSummary, ChampionshipOutlook as Outlook, ChampionshipRow,
} from '../services/backendApi';
import {
  Button, Card, CardHeader, EmptyState, ErrorState, FadeIn, FilterBar, HowItWorksCard, LoadingState, Pill,
  PositionBadge, SelectField, TableWrap, TeamChip, Td, Th, Tr, teamColor,
} from './ui';
import { formatChance } from '../utils/probability';
import { useOnDataChange } from '../hooks/useDataVersion';

type View = 'drivers' | 'constructors';
const VIEWS: { id: View; label: string }[] = [
  { id: 'drivers', label: "Drivers' championship" },
  { id: 'constructors', label: "Constructors' championship" },
];

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** Most likely final position and its chance. */
function likeliestFinish(row: ChampionshipRow): [number, number] | null {
  const probs = row.position_probabilities;
  if (!probs?.length) return null;
  let best = 0;
  probs.forEach((p, i) => { if (p > probs[best]) best = i; });
  return [best + 1, probs[best]];
}

const round1 = (n: number) => Math.round(n * 10) / 10;

/**
 * The title race in one or two lines: where it stands, then what settles it next (the clinch
 * scenario at the next race) or, failing that, the title chances. Worked out from the outlook, so it
 * changes after every race weekend (and refreshes on an open page when new results land).
 */
export function titleInsights(outlook: Outlook, kind: View): string[] {
  const [leader, second] = outlook.standings;
  const left = outlook.remaining.length;
  const s = kind === 'drivers' ? 's' : '';
  const pts = (n: number) => `${n} point${n === 1 ? '' : 's'}`;

  if (outlook.status === 'finished') {
    const by = leader && second ? ` by ${pts(round1(leader.points - second.points))} over ${second.name}` : '';
    return [`${outlook.champion ?? leader?.name} won the ${outlook.year} title${by}.`];
  }
  if (outlook.clinched) return [`${outlook.champion} clinched the ${outlook.year} title with ${plural(left, 'round')} to go.`];

  const favourites = [...outlook.standings].sort((a, b) => b.title_probability - a.title_probability)
    .filter((r) => r.title_probability > 0).slice(0, 3);
  const chances = favourites.length
    ? `Title chances: ${favourites.map((r) => `${r.name} ${formatChance(r.title_probability)}`).join(', ')}.` : null;
  if (outlook.status === 'pre_season' || !leader) {
    return [`The ${outlook.year} season hasn't started yet.`, ...(chances ? [chances] : [])];
  }

  const gap = second ? round1(leader.points - second.points) : 0;
  const standing = !second ? `${leader.name} lead${s}`
    : gap === 0 ? `${leader.name} and ${second.name} are level on points`
      : `${leader.name} lead${s} ${second.name} by ${pts(gap)}`;
  const lines = [`${standing} with ${plural(left, 'round')} (up to ${outlook.max_points_remaining} points) left.`];
  const hint = outlook.next_race_clinch;
  const race = hint ? `${hint.race_name.replace(/\s*Grand Prix$/i, '')} GP` : '';
  if (hint && hint.margin_needed > 0) {
    lines.push(`${leader.name} can clinch it at the ${race} by outscoring ${hint.rival_name} by ${pts(hint.margin_needed)} or more.`);
  } else if (hint) {
    lines.push(`${leader.name} clinch${kind === 'drivers' ? 'es' : ''} it at the ${race} unless ${hint.rival_name} outscore${s} them by ${pts(1 - hint.margin_needed)} or more.`);
  } else if (chances) {
    lines.push(chances);
  }
  return lines;
}

const InsightsPanel: React.FC<{ id: string; outlook: Outlook; kind: View }> = ({ id, outlook, kind }) => (
  <section id={id} aria-label="Insights" className="border-l-2 border-racing-red bg-ink-900 px-5 py-4">
    <p className="label text-muted">
      {outlook.status === 'finished' ? `The ${outlook.year} season, final`
        : `After round ${outlook.rounds_completed} of ${outlook.rounds_total}`}
    </p>
    {titleInsights(outlook, kind).map((line) => (
      <p key={line} className="mt-2 text-base leading-relaxed text-white">{line}</p>
    ))}
  </section>
);

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
                {!eliminated && row.racing === false && !decided && (
                  <span className="mt-1 block"><Pill tone="warn">Missed last race</Pill></span>
                )}
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
    <HowItWorksCard>
        <p>
          <strong className="text-gray-200">Who can still win</strong> is exact: a {kind === 'drivers' ? 'driver' : 'team'} is out of
          contention once, even scoring the maximum in every remaining round
          ({kind === 'drivers' ? '25 a race, 33 on a sprint weekend' : '43 for a one-two, 58 on a sprint weekend'}) while the leader
          scores nothing, they couldn't finish ahead. Ties go to the most wins, then second places, and so on.
        </p>
        <p>
          <strong className="text-gray-200">Chances and projected points</strong> come from playing the rest of the season out
          {outlook.method.simulations ? ` ${outlook.method.simulations.toLocaleString()} times` : ''}. Each race's order is drawn as on the
          Predictions page — every driver's strength from the race-prediction model and their predicted grid, tuned on how the front
          of {outlook.method.calibration_races} real races the model hadn't seen turned out, with retirements — and each run gives
          every car and every driver a season-long form swing, so one quick car can't look like a certainty. The range under projected points covers
          the middle 80% of runs. A driver who missed the latest race — injured or out of the seat — is projected to score
          nothing more, since there's no telling when they'll be back; who can still win stays pure maths. {kind === 'constructors' && 'Team totals add up both cars from the same simulated races, so they always match the drivers\' view.'}
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
    </HowItWorksCard>
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
  const [showInsights, setShowInsights] = useState(false);
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
  // New results stored while the page is open (a sprint's points): refresh behind what's shown.
  useOnDataChange(() => {
    const id = ++requestId.current;
    backendApi.getChampionshipOutlook(view, year)
      .then((data) => { if (id === requestId.current) setOutlook(data); })
      .catch(() => undefined);
  });

  useEffect(() => {
    let cancelled = false;
    backendApi.getChampionshipBacktest().then((b) => { if (!cancelled) setBacktest(b); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  const empty = outlook && outlook.standings.length === 0;

  // The first load is just "Loading predictions…"; after that the dropdown stays while the other
  // championship loads.
  if (loading && !outlook && !error) return <Card><LoadingState label="Loading predictions…" /></Card>;

  return (
    <FadeIn>
      <FilterBar>
        <SelectField label="Championship" value={view} onChange={(v) => setView(v as View)} className="min-w-[240px]">
          {VIEWS.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
        </SelectField>
        {outlook && !empty && (
          <Button variant="secondary" icon={<Lightbulb className="h-4 w-4" />}
            aria-expanded={showInsights} aria-controls="title-insights" onClick={() => setShowInsights((v) => !v)}>
            Insights
          </Button>
        )}
      </FilterBar>
      <div className="space-y-6">
        {loading ? <Card><LoadingState label="Loading predictions…" /></Card> : error ? (
          <Card><ErrorState title="Couldn't load the championship outlook" message={error} onRetry={load} /></Card>
        ) : !outlook || empty ? (
          <Card>
            <EmptyState
              icon={<Trophy className="h-10 w-10" />}
              title={`No title race to show for ${year}`}
              message="The outlook is worked out from stored race results, which start in 2022."
            />
          </Card>
        ) : (
          <>
            {showInsights && <InsightsPanel id="title-insights" outlook={outlook} kind={view} />}
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
    </FadeIn>
  );
};

export default ChampionshipOutlook;
