import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { TrendingUp, RefreshCw, History, ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import ChampionshipOutlook from './ChampionshipOutlook';
import { backendApi, PredictableRace, BacktestRace, BacktestDriverRow } from '../services/backendApi';
import {
  Button, Card, CardHeader, CheckboxField, EmptyState, ErrorState, FadeIn, FilterBar, LoadingState, Notice,
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
}

interface PredictionResult {
  success: boolean;
  circuit: string;
  model: string;
  grid_data_available: boolean;
  predictions: PredictionRow[];
  odds_available?: boolean;
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
            <Td className="font-medium text-white">{row.driver_name}</Td>
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

const errorColor = (err: number | null | undefined): string => {
  if (err == null) return 'text-gray-500';
  if (err <= 1.5) return 'text-green-400';
  if (err <= 3) return 'text-yellow-400';
  return 'text-red-400';
};

type SortKey = 'driver_name' | 'predicted_grid' | 'actual_grid' | 'predicted_position' | 'actual_position';
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
      setSortDir('asc');
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

  return (
    <Card>
      <CardHeader
        title={`Round ${race.round} — ${race.race_name}`}
        subtitle={race.practice_data === false
          ? `${race.circuit_name} · ${race.year} · no practice data stored, so predicted without practice pace`
          : `${race.circuit_name} · ${race.year}`}
        action={
          <div className="flex items-center gap-2">
            <span className={`rounded bg-gray-800 px-2 py-1 text-xs tabular-nums ${errorColor(race.quali_mae)}`}>
              Quali err {race.quali_mae != null ? race.quali_mae.toFixed(2) : '—'}
            </span>
            <span className={`rounded bg-gray-800 px-2 py-1 text-xs tabular-nums ${errorColor(race.race_mae)}`}>
              Race err {race.race_mae != null ? race.race_mae.toFixed(2) : '—'}
            </span>
          </div>
        }
      />
      <TableWrap>
        <thead>
          <tr className="border-b border-gray-800">
            <SortableHeader label="Driver"       col="driver_name"        align="left" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
            <SortableHeader label="Pred. Grid"   col="predicted_grid"     sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
            <SortableHeader label="Actual Grid"  col="actual_grid"        sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
            <SortableHeader label="Pred. Finish" col="predicted_position" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
            <SortableHeader label="Actual Finish" col="actual_position"   sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
          </tr>
        </thead>
        <tbody>
          {sortedDrivers.map((d) => (
            <Tr key={d.driver_id}>
              <Td className="font-medium text-white">{d.driver_name}</Td>
              <Td align="right" className="text-xs text-gray-400">{d.predicted_grid != null ? `P${d.predicted_grid}` : '—'}</Td>
              <Td align="right" className="text-xs text-white">{d.actual_grid != null ? `P${d.actual_grid}` : '—'}</Td>
              <Td align="right" className="text-xs text-gray-400">{d.predicted_position != null ? `P${d.predicted_position}` : '—'}</Td>
              <Td align="right" className="text-xs text-white">{d.actual_position != null ? `P${d.actual_position}` : '—'}</Td>
            </Tr>
          ))}
        </tbody>
      </TableWrap>
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

  const load = useCallback(() => {
    setError(null);
    setRaces(null);
    backendApi.getPredictionBacktest()
      .then((r) => {
        setRaces(r.races);
        // Backend returns most-recent-first — default to the latest race.
        if (r.races.length > 0) {
          setYearFilter(r.races[0].year);
          setSelectedRaceId(r.races[0].race_id);
        }
      })
      .catch((e) => setError(e.message || 'Failed to load backtest results'));
  }, []);

  useEffect(() => { load(); }, [load]);

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

  return (
    <FadeIn>
      <p className="mb-4 max-w-3xl text-sm text-gray-500">
        Each race's predictions use only data available before it was run — the current model
        scored retrospectively against real results. Lower error is better.
      </p>

      <FilterBar>
        <SelectField label="Year" value={yearFilter ?? ''} onChange={(v) => setYearFilter(Number(v))}>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </SelectField>
        <SelectField label="Circuit" value={selectedRaceId} onChange={setSelectedRaceId} className="min-w-[260px]">
          {raceOptions.map((r) => (
            <option key={r.race_id} value={r.race_id}>
              Round {r.round} — {showCircuitName ? r.circuit_name : r.race_name}
            </option>
          ))}
        </SelectField>
        <CheckboxField label="Circuit name" checked={showCircuitName} onChange={setShowCircuitName} />
      </FilterBar>

      {selectedRace ? (
        <BacktestRaceDetail race={selectedRace} />
      ) : (
        <Card><EmptyState title="No race matches the selected filters" /></Card>
      )}
    </FadeIn>
  );
};

type PredictionTab = 'upcoming' | 'title' | 'backtest';
const PREDICTION_TABS: { id: PredictionTab; label: string }[] = [
  { id: 'upcoming', label: 'Upcoming Predictions' },
  { id: 'title', label: 'Title Race' },
  { id: 'backtest', label: 'Predicted vs Actual' },
];
const PREDICTION_TAB_IDS = PREDICTION_TABS.map((t) => t.id);
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

  const runPredictions = useCallback(async () => {
    if (!selected) return;
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    setQualiResult(null);
    setRaceResult(null);
    setSprintResult(null);
    try {
      const sprint = circuits.find((c) => c.circuit_name === selected)?.is_sprint;
      const [q, r, s] = await Promise.all([
        backendApi.predictQualifying(selected),
        backendApi.predictRace(selected),
        sprint ? backendApi.predictSprint(selected) : Promise.resolve(null),
      ]);
      if (id !== requestId.current) return; // a different circuit was picked meanwhile
      setQualiResult(q);
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

  return (
    <PageShell>
      <PageHeader title="Race Predictions" subtitle="ML-powered qualifying and race predictions" />

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

            {error ? (
              <Card><ErrorState title="Couldn't generate predictions" message={error} onRetry={runPredictions} /></Card>
            ) : loading && !hasResults ? (
              <Card><LoadingState label={warmingUp ? "Training the models — the first run after a restart takes a little longer…" : "Generating predictions…"} /></Card>
            ) : hasResults ? (
              <FadeIn className="flex flex-col gap-6 lg:flex-row">
                {qualiResult?.predictions.length ? (
                  <PredictionTable title="Qualifying Prediction" subtitle={qualiResult.circuit} data={qualiResult.predictions}
                    valueKey="predicted_grid" avgKey="circuit_avg_grid" rollingKey="rolling_avg_grid" gridMissing={gridMissing} qualifying />
                ) : qualiResult && <UnavailableCard what="Qualifying prediction" reason={qualiResult.error} />}

                {sprintResult?.predictions.length ? (
                  <PredictionTable title="Sprint Prediction" subtitle={sprintResult.circuit} data={sprintResult.predictions}
                    valueKey="predicted_position" avgKey="circuit_avg_finish" rollingKey="rolling_avg_finish" gridMissing={gridMissing} />
                ) : sprintResult && <UnavailableCard what="Sprint prediction" reason={sprintResult.error} />}

                {raceResult?.predictions.length ? (
                  <PredictionTable title="Race Prediction" subtitle={raceResult.circuit} data={raceResult.predictions}
                    valueKey="predicted_position" avgKey="circuit_avg_finish" rollingKey="rolling_avg_finish" gridMissing={gridMissing} />
                ) : raceResult && <UnavailableCard what="Race prediction" reason={raceResult.error} severe />}
              </FadeIn>
            ) : null}
            {!error && hasResults && (raceResult?.odds_available || qualiResult?.odds_available) && (
              <p className="mt-4 text-xs leading-relaxed text-gray-500">
                The order is the model's prediction. <strong className="text-gray-400">avg</strong> and the win / pole and
                podium chances come from playing the session out 20,000 times with the same model, tuned on real races it
                hadn't seen, so a favourite's chance reflects how often favourites really do win. Sprints show the order only.
              </p>
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
