import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { TrendingUp, RefreshCw, History, ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import ChampionshipOutlook from './ChampionshipOutlook';
import {
  backendApi, PredictableRace, BacktestRace, BacktestDriverRow, BacktestHitRates, BacktestProbabilityScores, BacktestResult,
  HitRate, ProbabilityScore,
} from '../services/backendApi';
import {
  Button, Card, CardHeader, CheckboxField, EmptyState, ErrorState, FadeIn, FilterBar, HowItWorksCard, LoadingState, Notice,
  PageHeader, PageShell, Pill, PositionBadge, SelectField, TabPanel, Tabs, TableWrap, Td, Th, Tr,
} from './ui';
import { formatChance } from '../utils/probability';

interface PredictionRow {
  predicted_rank: number;
  driver_id: string;
  driver_name: string;
  constructor_id: string;
  constructor_name: string;
  predicted_position?: number;
  predicted_grid?: number;
  circuit_avg_finish?: number | null;
  circuit_avg_grid?: number | null;
  rolling_avg_finish?: number | null;
  rolling_avg_grid?: number | null;
  /** From simulating the session with the calibrated model (race and qualifying only). */
  expected_position?: number;
  win_probability?: number;
  podium_probability?: number;
  /** What lifted (+) or held back (−) this driver against the field's average, biggest first. */
  factors?: Record<string, number>;
}

/** "▲ Team · ▼ This circuit": the two biggest things behind a driver's place, the rest on hover. */
const WhyLine: React.FC<{ factors?: Record<string, number> }> = ({ factors }) => {
  const entries = Object.entries(factors ?? {}).filter(([k, v]) => k !== 'Other' && Math.abs(v) >= 0.01)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  if (!entries.length) return null;
  const full = entries.map(([k, v]) => `${v > 0 ? '+' : '−'} ${k} (${Math.abs(v).toFixed(2)})`).join('\n');
  return (
    <span className="mt-0.5 block text-xs font-normal text-gray-500" title={`Against the field's average driver:\n${full}`}>
      {entries.slice(0, 2).map(([k, v], i) => (
        <span key={k}>
          {i > 0 && ' · '}
          <span className={v > 0 ? 'text-green-400' : 'text-red-400'} aria-hidden="true">{v > 0 ? '▲' : '▼'}</span>
          <span className="sr-only">{v > 0 ? 'helped by' : 'held back by'}</span> {k}
        </span>
      ))}
    </span>
  );
};

interface PredictionResult {
  success: boolean;
  circuit: string;
  model: string;
  grid_data_available: boolean;
  predictions: PredictionRow[];
  odds_available?: boolean;
  /** Where the driver list came from: "this weekend's qualifying", "the practice 2 entry list",
   *  or "the last race's line-up" when nothing says who's entered yet. */
  field_source?: string;
  /** This weekend's stored practice pace went in (else it was left neutral). */
  practice_used?: boolean;
  /** Race/sprint: the grid it starts from — "this weekend's qualifying" once stored, else "predicted qualifying". */
  grid_source?: string;
  error?: string;
}

const positionColor = (pos: number): string => {
  if (pos <= 3)  return 'text-yellow-400 font-bold';
  if (pos <= 10) return 'text-green-400';
  return 'text-gray-400';
};

const PredictionTable: React.FC<{
  title: string;
  subtitle: string;
  data: PredictionRow[];
  valueKey: 'predicted_grid' | 'predicted_position';
  avgKey: 'circuit_avg_grid' | 'circuit_avg_finish';
  rollingKey: 'rolling_avg_grid' | 'rolling_avg_finish';
  gridMissing: boolean;
  /** Qualifying calls a win "pole" and a podium "top 3". */
  qualifying?: boolean;
}> = ({ title, subtitle, data, valueKey, avgKey, rollingKey, gridMissing, qualifying }) => {
  const odds = data.some((r) => r.win_probability != null);
  return (
  <Card className="min-w-0 flex-1">
    <CardHeader
      title={title}
      subtitle={subtitle}
      action={gridMissing && valueKey === 'predicted_position' ? <Pill tone="warn">No grid data</Pill> : undefined}
    />
    <TableWrap>
      <thead>
        <tr className="border-b border-gray-800">
          <Th className="w-14">#</Th>
          <Th>Driver</Th>
          <Th className="hidden sm:table-cell">Team</Th>
          <Th align="right">Predicted</Th>
          {odds && <Th align="right">{qualifying ? 'Pole' : 'Win'}</Th>}
          <Th align="right" className="hidden md:table-cell">Circuit Avg</Th>
          <Th align="right" className="hidden md:table-cell">Form (5R)</Th>
        </tr>
      </thead>
      <tbody>
        {data.map((row) => (
          <Tr key={row.driver_id}>
            <Td><PositionBadge position={row.predicted_rank} /></Td>
            <Td className="font-medium text-white">{row.driver_name}<WhyLine factors={row.factors} /></Td>
            <Td className="hidden text-xs text-gray-400 sm:table-cell">{row.constructor_name}</Td>
            <Td align="right" className={`font-semibold ${positionColor(row.predicted_rank)}`}>
              P{Math.round(row[valueKey] ?? row.predicted_rank)}
              {row.expected_position != null && (
                <span className="block text-xs font-normal text-gray-500" title="Average finishing position over the simulated sessions">
                  avg P{row.expected_position.toFixed(1)}
                </span>
              )}
            </Td>
            {odds && (
              <Td align="right" className="tabular-nums text-gray-200">
                {row.win_probability != null ? formatChance(row.win_probability) : '—'}
                {row.podium_probability != null && (
                  <span className="block text-xs text-gray-500">{qualifying ? 'top 3' : 'podium'} {formatChance(row.podium_probability)}</span>
                )}
              </Td>
            )}
            <Td align="right" className="hidden text-xs text-gray-400 md:table-cell">
              {row[avgKey] != null ? `P${row[avgKey]!.toFixed(1)}` : '—'}
            </Td>
            <Td align="right" className="hidden text-xs text-gray-400 md:table-cell">
              {row[rollingKey] != null ? `P${row[rollingKey]!.toFixed(1)}` : '—'}
            </Td>
          </Tr>
        ))}
      </tbody>
    </TableWrap>
  </Card>
  );
};

const UnavailableCard: React.FC<{ what: string; reason?: string; severe?: boolean }> = ({ what, reason, severe }) => (
  <Card className="flex-1">
    <EmptyState
      icon={<TrendingUp className={`h-8 w-8 ${severe ? 'text-red-500/60' : 'text-yellow-500/60'}`} />}
      title={`${what} unavailable`}
      message={reason}
    />
  </Card>
);

/** Rank error: average places a prediction was off by. Lower is better. */
/** "Baku · drivers: this weekend's practice 2 · with this weekend's practice pace" */
const predictionSubtitle = (r: PredictionResult) => [
  r.circuit,
  r.field_source && `drivers: ${r.field_source}`,
  r.practice_used != null && (r.practice_used ? "with this weekend's practice pace" : 'before practice: no pace data yet'),
  r.grid_source && r.grid_source !== 'predicted qualifying' && `grid: ${r.grid_source}`,
].filter(Boolean).join(' · ');

const errorTone = (err: number | null | undefined): 'good' | 'warn' | 'bad' | 'neutral' => {
  if (err == null) return 'neutral';
  if (err <= 1.5) return 'good';
  if (err <= 3) return 'warn';
  return 'bad';
};

type SortKey = 'driver_name' | 'predicted_grid' | 'actual_quali' | 'actual_grid' | 'predicted_position' | 'actual_position'
  | 'predicted_sprint' | 'actual_sprint' | 'pole_probability' | 'win_probability' | 'podium_probability';
const CHANCE_KEYS: SortKey[] = ['pole_probability', 'win_probability', 'podium_probability'];
type SortDir = 'asc' | 'desc';

const SortableHeader: React.FC<{
  label: string;
  col: SortKey;
  align?: 'left' | 'right';
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (col: SortKey) => void;
}> = ({ label, col, align = 'right', sortKey, sortDir, onSort }) => {
  const active = sortKey === col;
  const Icon = active ? (sortDir === 'asc' ? ArrowUp : ArrowDown) : ArrowUpDown;
  return (
    <th
      scope="col"
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
      className={`whitespace-nowrap px-4 py-3 text-xs font-medium uppercase tracking-wide ${align === 'left' ? 'text-left' : 'text-right'}`}
    >
      <button
        type="button"
        onClick={() => onSort(col)}
        className={`inline-flex items-center gap-1 rounded uppercase tracking-wide transition-colors hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/60 ${active ? 'text-white' : 'text-gray-500'}`}
      >
        {label} <Icon className="h-3 w-3" aria-hidden="true" />
      </button>
    </th>
  );
};

const sortValue = (d: BacktestDriverRow, key: SortKey): number | string => {
  const v = d[key];
  if (key === 'driver_name') return (v as string) ?? '';
  return v == null ? Number.POSITIVE_INFINITY : (v as number);
};

const BacktestRaceDetail: React.FC<{ race: BacktestRace }> = ({ race }) => {
  const [sortKey, setSortKey] = useState<SortKey>('actual_position');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const onSort = (col: SortKey) => {
    if (col === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(col);
      setSortDir(CHANCE_KEYS.includes(col) ? 'desc' : 'asc');   // biggest chance first
    }
  };

  const sortedDrivers = useMemo(() => {
    const rows = [...race.drivers];
    rows.sort((a, b) => {
      const av = sortValue(a, sortKey);
      const bv = sortValue(b, sortKey);
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return rows;
  }, [race.drivers, sortKey, sortDir]);

  const hasChances = race.drivers.some((d) => d.win_probability != null || d.pole_probability != null);
  const hasSprint = race.drivers.some((d) => d.actual_sprint != null);
  const raceRun = !race.in_progress;
  const chance = (p: number | undefined) => (p != null ? formatChance(p) : '—');
  const place = (p: number | null | undefined) => (p != null ? `P${p}` : '—');
  const facts = [race.circuit_name, String(race.year)];
  if (race.in_progress) facts.push('race still to run');
  if (race.practice_data === false) facts.push('no practice data stored, so predicted without practice pace');

  return (
    <Card>
      <CardHeader
        title={`Round ${race.round} — ${race.race_name}`}
        subtitle={facts.join(' · ')}
        action={
          <div className="flex flex-wrap items-center gap-2">
            {hasSprint && <Pill tone={errorTone(race.sprint_mae)}>Sprint off by {race.sprint_mae != null ? race.sprint_mae.toFixed(1) : '—'}</Pill>}
            <Pill tone={errorTone(race.quali_mae)}>Qualifying off by {race.quali_mae != null ? race.quali_mae.toFixed(1) : '—'}</Pill>
            {raceRun
              ? <Pill tone={errorTone(race.race_mae)}>Race off by {race.race_mae != null ? race.race_mae.toFixed(1) : '—'}</Pill>
              : <Pill tone="neutral">Race still to run</Pill>}
          </div>
        }
      />
      <TableWrap>
        <thead>
          <tr className="border-b border-gray-800">
            <SortableHeader label="Driver"       col="driver_name"        align="left" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
            {hasSprint && <SortableHeader label="Pred. Sprint"  col="predicted_sprint" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />}
            {hasSprint && <SortableHeader label="Actual Sprint" col="actual_sprint"    sortKey={sortKey} sortDir={sortDir} onSort={onSort} />}
            <SortableHeader label="Pred. Quali"  col="predicted_grid"     sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
            <SortableHeader label="Actual Quali" col="actual_quali"       sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
            {hasChances && <SortableHeader label="Pole chance" col="pole_probability" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />}
            {raceRun && <SortableHeader label="Pred. Finish" col="predicted_position" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />}
            {raceRun && <SortableHeader label="Actual Finish" col="actual_position"   sortKey={sortKey} sortDir={sortDir} onSort={onSort} />}
            {raceRun && hasChances && <SortableHeader label="Win chance"    col="win_probability"    sortKey={sortKey} sortDir={sortDir} onSort={onSort} />}
            {raceRun && hasChances && <SortableHeader label="Podium chance" col="podium_probability" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />}
          </tr>
        </thead>
        <tbody>
          {sortedDrivers.map((d) => (
            <Tr key={d.driver_id}>
              <Td className="font-medium text-white">{d.driver_name}</Td>
              {hasSprint && <Td align="right" className="tabular-nums text-gray-400">{place(d.predicted_sprint)}</Td>}
              {hasSprint && <Td align="right" className="tabular-nums text-white">{place(d.actual_sprint)}</Td>}
              <Td align="right" className="tabular-nums text-gray-400">{place(d.predicted_grid)}</Td>
              <Td align="right" className="tabular-nums text-white">{(d.actual_quali ?? d.actual_grid) != null ? `P${d.actual_quali ?? d.actual_grid}` : '—'}</Td>
              {hasChances && <Td align="right" className="tabular-nums text-gray-400">{chance(d.pole_probability)}</Td>}
              {raceRun && <Td align="right" className="tabular-nums text-gray-400">{place(d.predicted_position)}</Td>}
              {raceRun && <Td align="right" className="tabular-nums text-white">{place(d.actual_position)}</Td>}
              {raceRun && hasChances && <Td align="right" className="tabular-nums text-gray-400">{chance(d.win_probability)}</Td>}
              {raceRun && hasChances && <Td align="right" className="tabular-nums text-gray-400">{chance(d.podium_probability)}</Td>}
            </Tr>
          ))}
        </tbody>
      </TableWrap>
    </Card>
  );
};

const MARKET_LABELS: { kind: 'race' | 'sprint' | 'qualifying'; key: string; label: string }[] = [
  { kind: 'qualifying', key: 'pole', label: 'Pole' },
  { kind: 'race', key: 'win', label: 'Race win' },
  { kind: 'race', key: 'podium', label: 'Podium' },
  { kind: 'race', key: 'points', label: 'Points (top 10)' },
  { kind: 'sprint', key: 'win', label: 'Sprint win' },
  { kind: 'sprint', key: 'podium', label: 'Sprint podium' },
  { kind: 'sprint', key: 'points', label: 'Sprint points (top 8)' },
];

/** "18% better" / "24% worse" — Brier skill against a baseline. */
const skillLabel = (skill: number | undefined) => {
  if (skill == null) return '—';
  const pct = Math.round(Math.abs(skill) * 100);
  return pct === 0 ? 'level' : `${pct}% ${skill > 0 ? 'better' : 'worse'}`;
};
const skillTone = (skill: number | undefined): 'good' | 'bad' | 'neutral' =>
  skill == null || Math.abs(skill) < 0.02 ? 'neutral' : skill > 0 ? 'good' : 'bad';

/** How good the chances were: each market against two baselines, plus the clearest calibration gap. */
const ChanceScores: React.FC<{ scores: BacktestProbabilityScores }> = ({ scores }) => {
  const rows = MARKET_LABELS
    .map((m) => ({ ...m, score: ((scores[m.kind] ?? {}) as Record<string, ProbabilityScore | undefined>)[m.key] }))
    .filter((m): m is typeof m & { score: ProbabilityScore } => m.score != null);
  if (!rows.length) return null;
  // The band of win chances furthest from what happened (with enough drivers in it to mean something).
  const win = scores.race.win;
  const gap = win?.reliability
    .filter((b) => b.n >= 20)
    .sort((a, b) => Math.abs(b.observed - b.predicted) - Math.abs(a.observed - a.predicted))[0];

  return (
    <Card className="mt-6">
      <CardHeader
        title="How good the chances were"
        subtitle={`Pole, win, podium and points chances for ${scores.races_scored} races, each worked out before the race from earlier races only`}
      />
      <TableWrap>
        <thead>
          <tr className="border-b border-gray-800">
            <Th>Chance of</Th>
            <Th align="right">vs. everyone equal</Th>
            <Th align="right">vs. history of the grid slot</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ key, label, score }) => (
            <Tr key={key}>
              <Td className="font-medium text-white">{label}</Td>
              <Td align="right"><Pill tone={skillTone(score.skill_vs_uniform)}>{skillLabel(score.skill_vs_uniform)}</Pill></Td>
              <Td align="right">
                {score.skill_vs_starting_slot != null
                  ? <Pill tone={skillTone(score.skill_vs_starting_slot)}>{skillLabel(score.skill_vs_starting_slot)}</Pill>
                  : <span className="text-gray-600">—</span>}
              </Td>
            </Tr>
          ))}
        </tbody>
      </TableWrap>
      {gap && Math.abs(gap.observed - gap.predicted) >= 0.05 && (
        <p className="border-t border-gray-800 px-4 py-3 text-sm text-gray-400">
          Drivers given {formatChance(gap.predicted)} to win on average won {formatChance(gap.observed)} of the time
          ({gap.n} drivers) — the race chances are {Math.abs(gap.observed - gap.predicted) >= 0.15 ? 'too' : 'a little'}{' '}
          {gap.observed > gap.predicted ? 'cautious' : 'confident'} at the front.
        </p>
      )}
    </Card>
  );
};

const HIT_ROWS: { key: keyof HitRate; race: string; sprint: string; qualifying: string }[] = [
  { key: 'top1', race: 'Picked the winner', sprint: 'Picked the winner', qualifying: 'Picked pole' },
  { key: 'top3', race: 'Podium named', sprint: 'Podium named', qualifying: 'Top 3 named' },
  { key: 'top10', race: 'Top 10 named', sprint: 'Top 10 named', qualifying: 'Q3 (top 10) named' },
  { key: 'mae', race: 'Places off (avg)', sprint: 'Places off (avg)', qualifying: 'Places off (avg)' },
];

/** The predicted order against simple guesses: the starting grid and the championship order. */
const HitRates: React.FC<{ rates: BacktestHitRates }> = ({ rates }) => {
  const sections = ([
    rates.qualifying && { kind: 'qualifying' as const, title: 'Qualifying', races: rates.qualifying.races,
      columns: [['Model', rates.qualifying.model], ['Championship order', rates.qualifying.standings]] as [string, HitRate][] },
    rates.race && { kind: 'race' as const, title: 'Race (with the grid known)', races: rates.race.races,
      columns: [['Model', rates.race.model], ['Starting grid', rates.race.grid], ['Championship order', rates.race.standings]] as [string, HitRate][] },
    rates.sprint && { kind: 'sprint' as const, title: 'Sprint (with the grid known)', races: rates.sprint.races,
      columns: [['Model', rates.sprint.model], ['Starting grid', rates.sprint.grid], ['Championship order', rates.sprint.standings]] as [string, HitRate][] },
  ]).filter(Boolean) as { kind: 'race' | 'sprint' | 'qualifying'; title: string; races: number; columns: [string, HitRate][] }[];
  if (!sections.length) return null;

  const format = (key: keyof HitRate, v: number) => (key === 'mae' ? v.toFixed(2) : `${Math.round(v * 100)}%`);
  const best = (key: keyof HitRate, cols: [string, HitRate][]) =>
    (key === 'mae' ? Math.min : Math.max)(...cols.map(([, r]) => r[key]));

  return (
    <Card className="mt-6">
      <CardHeader
        title="Against simple guesses"
        subtitle="The predicted order next to two guesses anyone could make: the starting grid, and the championship order going into the weekend"
      />
      <div className="grid gap-0 lg:grid-cols-2">
        {sections.map(({ kind, title, races, columns }) => (
          <div key={kind} className="min-w-0">{/* lets the table scroll inside its column instead of widening the page */}
          <TableWrap>
            <thead>
              <tr className="border-b border-gray-800">
                <Th>{title} · {races} races</Th>
                {columns.map(([label]) => <Th key={label} align="right">{label}</Th>)}
              </tr>
            </thead>
            <tbody>
              {HIT_ROWS.map(({ key, ...labels }) => {
                const top = best(key, columns);
                return (
                  <Tr key={key}>
                    <Td className="text-gray-300">{labels[kind]}</Td>
                    {columns.map(([label, r]) => (
                      <Td key={label} align="right" className={`tabular-nums ${r[key] === top ? 'font-semibold text-white' : 'text-gray-400'}`}>
                        {format(key, r[key])}
                      </Td>
                    ))}
                  </Tr>
                );
              })}
            </tbody>
          </TableWrap>
          </div>
        ))}
      </div>
    </Card>
  );
};

const BacktestTab: React.FC = () => {
  const [races, setRaces]                   = useState<BacktestRace[] | null>(null);
  const [error, setError]                   = useState<string | null>(null);
  const [yearFilter, setYearFilter]         = useState<number | null>(null);
  const [selectedRaceId, setSelectedRaceId] = useState<string>('');
  // Two races can share a name (e.g. a Grand Prix that changed circuit), so this
  // lets the user switch the dropdown to circuit names to tell them apart.
  const [showCircuitName, setShowCircuitName] = useState(false);

  // The server rebuilds this list by itself after a race weekend's results come in; while it
  // works (`updating`) the current list is shown and checked again every 30s.
  const [updating, setUpdating]             = useState(false);
  const [scores, setScores]                 = useState<BacktestProbabilityScores | null>(null);
  const [hitRates, setHitRates]             = useState<BacktestHitRates | null>(null);
  const [latestSeason, setLatestSeason]     = useState<number | null>(null);
  const latestId = useRef<string | null>(null);
  const selectedRef = useRef(selectedRaceId);
  selectedRef.current = selectedRaceId;

  const apply = useCallback((r: BacktestResult) => {
    setRaces(r.races);
    setUpdating(Boolean(r.updating));
    setScores(r.probability_scores ?? null);
    setHitRates(r.hit_rates ?? null);
    setLatestSeason(r.method?.latest_season ?? null);
    if (r.races.length === 0) return;
    const newest = r.races[0];   // most recent first
    // Default to the latest race — and move along to a newly added one unless the user picked another.
    if (!selectedRef.current || selectedRef.current === latestId.current) {
      setYearFilter(newest.year);
      setSelectedRaceId(newest.race_id);
    }
    latestId.current = newest.race_id;
  }, []);

  const load = useCallback(() => {
    setError(null);
    setRaces(null);
    backendApi.getPredictionBacktest()
      .then(apply)
      .catch((e) => setError(e.message || 'Failed to load backtest results'));
  }, [apply]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!updating) return undefined;
    const id = setInterval(() => {
      backendApi.getPredictionBacktest().then(apply).catch(() => { /* keep showing what we have */ });
    }, 30000);
    return () => clearInterval(id);
  }, [updating, apply]);

  const years = useMemo(
    () => Array.from(new Set((races ?? []).map((r) => r.year))).sort((a, b) => b - a),
    [races]
  );

  // Every race within the selected year, ordered by round.
  const raceOptions = useMemo(
    () => (races ?? [])
      .filter((r) => yearFilter == null || r.year === yearFilter)
      .slice()
      .sort((a, b) => a.round - b.round),
    [races, yearFilter]
  );

  // Keep the selection valid whenever the year changes.
  useEffect(() => {
    if (raceOptions.length && !raceOptions.some((r) => r.race_id === selectedRaceId)) {
      setSelectedRaceId(raceOptions[0].race_id);
    }
  }, [raceOptions, selectedRaceId]);

  const selectedRace = useMemo(
    () => (races ?? []).find((r) => r.race_id === selectedRaceId) ?? null,
    [races, selectedRaceId]
  );

  if (error) return <Card><ErrorState title="Couldn't load past predictions" message={error} onRetry={load} /></Card>;
  if (!races) return <Card><LoadingState label="Loading past seasons…" /></Card>;
  if (races.length === 0) {
    return (
      <Card>
        <EmptyState icon={<History className="h-10 w-10" />} title="No completed races with predictions yet" />
      </Card>
    );
  }

  const mean = (xs: (number | null)[]) => {
    const v = xs.filter((x): x is number => x != null);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  };
  const quali = mean(races.map((r) => r.quali_mae));
  const race = mean(races.map((r) => r.race_mae));
  const raced = races.filter((r) => !r.in_progress).length;
  const seasons = years.slice().sort((a, b) => a - b);

  return (
    <FadeIn>
      <FilterBar>
        <SelectField label="Year" value={yearFilter ?? ''} onChange={(v) => setYearFilter(Number(v))}>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </SelectField>
        <SelectField label="Circuit" value={selectedRaceId} onChange={setSelectedRaceId} className="min-w-[260px]">
          {raceOptions.map((r) => (
            <option key={r.race_id} value={r.race_id}>
              Round {r.round} — {showCircuitName ? r.circuit_name : r.race_name}{r.in_progress ? ' (race to come)' : ''}
            </option>
          ))}
        </SelectField>
        <CheckboxField label="Circuit name" checked={showCircuitName} onChange={setShowCircuitName} />
      </FilterBar>

      {updating && (
        <Notice tone="info" className="mb-6">
          Adding the latest races: the models are being re-scored against them. This takes a few minutes and the list
          updates by itself.
        </Notice>
      )}

      {selectedRace ? (
        <BacktestRaceDetail race={selectedRace} />
      ) : (
        <Card><EmptyState title="No race matches the selected filters" /></Card>
      )}

      {hitRates && <HitRates rates={hitRates} />}
      {scores && <ChanceScores scores={scores} />}

      <div className="mt-6">
        <HowItWorksCard>
          <p>
            <strong className="text-gray-200">Honest by design:</strong> every race is predicted by a model that never saw
            it. {latestSeason
              ? `In ${latestSeason} each race is predicted by a model trained on everything up to the race before (as the site does, since it retrains after every race); earlier seasons by one model trained on the seasons before them.`
              : 'Each season is predicted by a model trained only on earlier seasons.'}{' '}
            "Off by" is how many places a prediction missed by, averaged over the drivers in that session: lower is better.
            A weekend shows up here as soon as its first predicted session (sprint or qualifying) is done, with the race
            added once it's run.
          </p>
          {scores && (
            <p>
              <strong className="text-gray-200">Chances</strong> come from playing each session out thousands of times, as
              on the Upcoming tab: each driver's strength is the model's score — and in a race their starting position — fitted
              on the front of earlier races' results, with retirements drawn from each driver's recent record. A race's
              predicted order is that strength, so it can differ from the model's raw order. They're compared with two
              simple guesses: every driver equally likely, and how often a car starting from that grid slot has won,
              podiumed or scored before. "Better" means a lower Brier score: the chances sat closer to what happened.
            </p>
          )}
          {quali != null && race != null && (
            <p>
              <strong className="text-gray-200">Overall:</strong> across {raced} races
              ({seasons[0]}–{seasons[seasons.length - 1]}), qualifying was off by {quali.toFixed(1)} places on average and
              the race by {race.toFixed(1)}. F1 is unpredictable (retirements, strategy, weather), so a few places is
              normal for any model.
            </p>
          )}
        </HowItWorksCard>
      </div>
    </FadeIn>
  );
};

type PredictionTab = 'upcoming' | 'title' | 'backtest';

/** One session's prediction at a time, chosen from a dropdown (?session=, Race by default). */
type PredictedSession = 'sprint' | 'qualifying' | 'race';
const SESSION_LABELS: Record<PredictedSession, string> = { sprint: 'Sprint', qualifying: 'Qualifying', race: 'Race' };
/** In weekend order: a sprint weekend runs the sprint on Saturday before qualifying. */
const sessionsFor = (sprintWeekend: boolean): PredictedSession[] =>
  sprintWeekend ? ['sprint', 'qualifying', 'race'] : ['qualifying', 'race'];
const PREDICTION_TABS: { id: PredictionTab; label: string }[] = [
  { id: 'upcoming', label: 'Upcoming Predictions' },
  { id: 'title', label: 'Title Race' },
  { id: 'backtest', label: 'Predicted vs Actual' },
];
const PREDICTION_TAB_IDS = PREDICTION_TABS.map((t) => t.id);
/** "Sprint", "Sprint and Qualifying". */
const listOf = (items: string[]) => (items.length > 1 ? `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}` : items[0] ?? '');
const CURRENT_YEAR = new Date().getFullYear();

const Predictions: React.FC = () => {
  const [circuits, setCircuits]       = useState<PredictableRace[]>([]);
  const [circuitsLoaded, setCircuitsLoaded] = useState(false);
  const [selected, setSelected]       = useState('');
  const [loading, setLoading]         = useState(false);
  const [qualiResult, setQualiResult]   = useState<PredictionResult | null>(null);
  const [raceResult, setRaceResult]     = useState<PredictionResult | null>(null);
  const [sprintResult, setSprintResult] = useState<PredictionResult | null>(null);
  const [error, setError]             = useState<string | null>(null);
  const [status, setStatus]           = useState<any>(null);
  // The tab lives in the URL (?tab=title) so links and refreshes land on it.
  const [params, setParams] = useSearchParams();
  const rawTab = params.get('tab') as PredictionTab | null;
  const tab: PredictionTab = rawTab && PREDICTION_TAB_IDS.includes(rawTab) ? rawTab : 'upcoming';
  const setTab = (t: PredictionTab) => setParams(t === 'upcoming' ? {} : { tab: t });
  const rawSession = params.get('session') as PredictedSession | null;
  const setSession = (s: PredictedSession) => setParams(s === 'race' ? {} : { session: s });
  const [showCircuitName, setShowCircuitName] = useState(false);
  const requestId = useRef(0);

  const refreshStatus = useCallback(
    (force = false) => backendApi.getPredictionStatus(force).then(setStatus).catch(() => {}),
    [],
  );

  useEffect(() => {
    refreshStatus();
    backendApi.getPredictionCircuits().then((c) => {
      setCircuits(c);
      if (c.length) setSelected(c[0].circuit_name);
    }).catch(() => {}).finally(() => setCircuitsLoaded(true));
  }, [refreshStatus]);

  const selectedRace = circuits.find((c) => c.circuit_name === selected);
  const isSprintWeekend = !!selectedRace?.is_sprint;
  // A finished session moves to Predicted vs Actual (the race never shows up here as done: the
  // weekend leaves the list once its race is stored).
  const doneSessions = sessionsFor(isSprintWeekend).filter((s) => selectedRace?.completed_sessions?.includes(s));
  const sessionOptions = sessionsFor(isSprintWeekend).filter((s) => !doneSessions.includes(s));
  // A sprint picked for one weekend falls back to the race on a weekend without one.
  const session: PredictedSession = rawSession && sessionOptions.includes(rawSession) ? rawSession : 'race';

  const runPredictions = useCallback(async () => {
    if (!selected) return;
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    setQualiResult(null);
    setRaceResult(null);
    setSprintResult(null);
    try {
      const race = circuits.find((c) => c.circuit_name === selected);
      const done = race?.completed_sessions ?? [];
      const [q, r, s] = await Promise.all([
        done.includes('qualifying') ? Promise.resolve(null) : backendApi.predictQualifying(selected),
        backendApi.predictRace(selected),
        race?.is_sprint && !done.includes('sprint') ? backendApi.predictSprint(selected) : Promise.resolve(null),
      ]);
      if (id !== requestId.current) return; // a different circuit was picked meanwhile
      if (q) setQualiResult(q);
      setRaceResult(r);
      if (s) setSprintResult(s);
    } catch (e: any) {
      if (id === requestId.current) setError(e.message || 'Predictions are unavailable right now. Try again in a moment.');
    } finally {
      if (id === requestId.current) setLoading(false);
      // The first prediction after a restart is what trains the models, so the status
      // fetched when the page opened ("not trained") is stale by now.
      refreshStatus(true);
    }
  }, [selected, circuits, refreshStatus]);

  // Predictions are cheap (cached server-side), so generate them as soon as a
  // circuit is chosen instead of making the user click a second time.
  useEffect(() => { if (selected) runPredictions(); }, [selected, runPredictions]);

  // A freshly started server has no models yet and reports every flag as false. That isn't
  // "grid data missing" — only say so once the models are trained and still report no grid.
  // ...and only while a prediction is actually pending: with no upcoming race nothing will ever train them.
  const warmingUp = !!status && !status.trained && (loading || !!selected);
  const gridMissing = !!status?.trained && !status.grid_data_available;
  const hasResults = !!(qualiResult || raceResult || sprintResult);
  const shown = { qualifying: qualiResult, sprint: sprintResult, race: raceResult }[session];

  return (
    <PageShell>
      <PageHeader title="Predictions" subtitle="Qualifying and race predictions, the title race, and how past predictions held up" />

      <Tabs tabs={PREDICTION_TABS} active={tab} onChange={setTab} label="Prediction views" idPrefix="pred" />

      <div className="pt-6">
        {tab === 'backtest' && <TabPanel id="backtest" idPrefix="pred"><BacktestTab /></TabPanel>}
        {tab === 'title' && <TabPanel id="title" idPrefix="pred"><ChampionshipOutlook year={CURRENT_YEAR} /></TabPanel>}

        {tab === 'upcoming' && (
          <TabPanel id="upcoming" idPrefix="pred">
            {gridMissing && (
              <Notice tone="warning">
                <strong>Grid data missing.</strong> Race predictions still work from rolling form
                averages, but accuracy improves significantly once qualifying grid positions are loaded.
              </Notice>
            )}

            <FilterBar>
              <SelectField label="Grand Prix" value={selected} onChange={setSelected}
                className="min-w-[280px]" disabled={circuits.length === 0}>
                {circuits.length === 0 && (
                  <option value="">{circuitsLoaded ? 'No upcoming races on the calendar' : 'Loading…'}</option>
                )}
                {circuits.map((c) => (
                  <option key={c.circuit_name} value={c.circuit_name}>
                    Round {c.round} — {showCircuitName ? c.circuit_name : c.race_name}{c.is_sprint ? ' (Sprint weekend)' : ''}
                  </option>
                ))}
              </SelectField>
              <SelectField label="Session" value={session} onChange={(v) => setSession(v as PredictedSession)}
                className="min-w-[160px]" disabled={circuits.length === 0}>
                {sessionOptions.map((s) => <option key={s} value={s}>{SESSION_LABELS[s]}</option>)}
              </SelectField>
              <CheckboxField label="Circuit name" checked={showCircuitName} onChange={setShowCircuitName} />

              <Button
                variant="secondary" onClick={runPredictions} loading={loading} disabled={!selected}
                icon={<RefreshCw className="h-4 w-4" />}
              >
                {loading ? 'Predicting…' : 'Refresh'}
              </Button>

              {warmingUp && (
                <div className="ml-auto">
                  <Pill tone="neutral">Models warming up — trained on the first prediction after a restart</Pill>
                </div>
              )}

              {status && !warmingUp && (
                <div className="ml-auto flex flex-wrap items-center gap-2">
                  <Pill tone={status.race_model_ready ? 'good' : 'bad'}>Race: {status.race_model_ready ? 'ready' : 'not trained'}</Pill>
                  <Pill tone={status.quali_model_ready ? 'good' : 'warn'}>Quali: {status.quali_model_ready ? 'ready' : 'needs grid data'}</Pill>
                  {isSprintWeekend && (
                    <Pill tone={status.sprint_model_ready ? 'good' : 'warn'}>
                      Sprint: {status.sprint_model_ready ? 'ready' : 'not enough sprint history'}
                    </Pill>
                  )}
                  {status.training_rows > 0 && <Pill tone="neutral">{status.training_rows} rows · {status.circuits} circuits</Pill>}
                </div>
              )}
            </FilterBar>

            {doneSessions.length > 0 && (
              <Notice tone="info">
                <span>
                  {listOf(doneSessions.map((s) => SESSION_LABELS[s]))} {doneSessions.length > 1 ? 'are' : 'is'} done
                  — see how {doneSessions.length > 1 ? 'they' : 'it'} compared with the prediction in{' '}
                  <button type="button" className="font-semibold underline hover:text-white" onClick={() => setTab('backtest')}>
                    Predicted vs Actual
                  </button>.
                </span>
              </Notice>
            )}

            {error ? (
              <Card><ErrorState title="Couldn't generate predictions" message={error} onRetry={runPredictions} /></Card>
            ) : loading && !hasResults ? (
              <Card><LoadingState label={warmingUp ? "Training the models — the first run after a restart takes a little longer…" : "Generating predictions…"} /></Card>
            ) : hasResults ? (
              <FadeIn key={session}>
                {shown?.predictions.length ? (
                  session === 'qualifying' ? (
                    <PredictionTable title="Qualifying Prediction" subtitle={predictionSubtitle(shown)} data={shown.predictions}
                      valueKey="predicted_grid" avgKey="circuit_avg_grid" rollingKey="rolling_avg_grid" gridMissing={gridMissing} qualifying />
                  ) : (
                    <PredictionTable title={`${SESSION_LABELS[session]} Prediction`} subtitle={predictionSubtitle(shown)}
                      data={shown.predictions} valueKey="predicted_position" avgKey="circuit_avg_finish"
                      rollingKey="rolling_avg_finish" gridMissing={gridMissing} />
                  )
                ) : shown ? (
                  <UnavailableCard what={`${SESSION_LABELS[session]} prediction`} reason={shown.error} severe={session === 'race'} />
                ) : (
                  <Card><LoadingState label={`Generating the ${SESSION_LABELS[session].toLowerCase()} prediction…`} /></Card>
                )}
              </FadeIn>
            ) : null}
            {!error && hasResults && (
              <div className="mt-6">
                <HowItWorksCard>
                  <p>
                    <strong className="text-gray-200">The order</strong> comes from ranking models trained on every race
                    since 2022 — gradient-boosted trees and a linear model, averaged, as they make different mistakes:
                    recent form, form at this circuit, the team's pace, practice, reliability and the predicted grid.
                  </p>
                  {shown?.odds_available && (
                    <p>
                      <strong className="text-gray-200">avg and the win / pole and podium chances</strong> come from
                      playing the session out 20,000 times. Each driver's strength is the model's score — in a race also
                      their starting position (the predicted one until qualifying, then the real one, which counts for
                      more) — with retirements drawn from their recent record, all tuned on how the front of real races
                      it hadn't seen turned out. The race and sprint order follows that strength, so it always agrees
                      with the chances (a sprint's points chance is the top 8).
                    </p>
                  )}
                  <p>
                    <strong className="text-gray-200">▲ / ▼ under a driver</strong> are the two biggest things lifting
                    them above, or holding them below, the field's average driver: recent form, the team, this
                    circuit, practice, the starting grid (predicted, until qualifying), reliability or the driver themselves (hover for the full
                    list). They come from the model itself — each input's share of the score — and in a race include how
                    much the starting position counts.
                  </p>
                  <p>
                    <strong className="text-gray-200">The drivers</strong> are the ones entered for this weekend, taken
                    from its latest session so far (qualifying first; first practice only as a last resort, since
                    rookies often stand in there). Before a weekend starts, the last race's line-up is used, so a
                    driver returning from injury appears once practice begins.
                  </p>
                  <p>
                    See how past predictions held up in <strong className="text-gray-200">Predicted vs Actual</strong>.
                  </p>
                </HowItWorksCard>
              </div>
            )}
            {!error && !hasResults && !loading && (
              <Card>
                <EmptyState
                  icon={<TrendingUp className="h-10 w-10" />}
                  title={circuitsLoaded && circuits.length === 0 ? 'No upcoming races to predict' : 'Choose a Grand Prix'}
                  message="Predictions are generated from historical F1 race data."
                />
              </Card>
            )}
          </TabPanel>
        )}
      </div>
    </PageShell>
  );
};

export default Predictions;
