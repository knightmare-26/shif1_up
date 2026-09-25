import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { BarChart3, Calendar, ChevronRight, Flag, ListOrdered, MapPin, TrendingUp, Trophy, Users } from 'lucide-react';
import { backendApi, DriverStanding, ConstructorStanding, RaceEvent } from '../services/backendApi';
import { describeDaysUntil, daysUntil, formatDate, isPastDate } from '../utils/dates';
import { gpToken, isRaceRound } from '../utils/races';
import ChampionshipOutlook from './ChampionshipOutlook';
import ConstructorAnalytics from './ConstructorAnalytics';
import DriverAnalytics from './DriverAnalytics';
import TrackAnalytics from './TrackAnalytics';
import RaceResults from './RaceResults';
import {
  Card, CardHeader, DetailList, ErrorState, EmptyState, FadeIn, LoadingState, PageHeader, PageShell,
  PositionBadge, SelectField, StatCard, TabPanel, Tabs, TableWrap, TeamChip, Td, Tr,
} from './ui';

type Tab = 'overview' | 'drivers' | 'teams' | 'title' | 'tracks' | 'results';

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'overview', label: 'Overview',     icon: <BarChart3 className="h-4 w-4" /> },
  { id: 'drivers',  label: 'Drivers',      icon: <Users className="h-4 w-4" /> },
  { id: 'teams',    label: 'Teams',        icon: <Flag className="h-4 w-4" /> },
  { id: 'title',    label: 'Title Race',   icon: <Trophy className="h-4 w-4" /> },
  { id: 'tracks',   label: 'Tracks',       icon: <MapPin className="h-4 w-4" /> },
  { id: 'results',  label: 'Race Results', icon: <ListOrdered className="h-4 w-4" /> },
];
const TAB_IDS = TABS.map((t) => t.id);

const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = Array.from({ length: CURRENT_YEAR - 2000 + 1 }, (_, i) => CURRENT_YEAR - i);

const TOP_N = 5;

const Dashboard: React.FC = () => {
  // Tab and year live in the URL so refresh, back/forward and shared links all
  // land where the user was.
  const [params, setParams] = useSearchParams();
  const rawTab = params.get('tab') as Tab | null;
  const tab: Tab = rawTab && TAB_IDS.includes(rawTab) ? rawTab : 'overview';
  const rawYear = Number(params.get('year'));
  const year = YEAR_OPTIONS.includes(rawYear) ? rawYear : CURRENT_YEAR;

  const navigate = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([k, v]) => (v === null ? next.delete(k) : next.set(k, v)));
    setParams(next);
  };
  const setTab = (t: Tab) => navigate({ tab: t === 'overview' ? null : t, gp: null });
  const setYear = (y: number) => navigate({ year: y === CURRENT_YEAR ? null : String(y), gp: null });

  const [drivers, setDrivers] = useState<DriverStanding[]>([]);
  const [teams, setTeams]     = useState<ConstructorStanding[]>([]);
  const [races, setRaces]     = useState<RaceEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const [d, c, r] = await Promise.all([
        backendApi.getDriverStandings(year),
        backendApi.getConstructorStandings(year),
        backendApi.getRaceSchedule(year),
      ]);
      if (id !== requestId.current) return; // a newer year was picked meanwhile
      setDrivers(Array.isArray(d) ? d : []);
      setTeams(Array.isArray(c) ? c : []);
      setRaces(Array.isArray(r) ? r.filter(isRaceRound) : []);
    } catch (e) {
      if (id !== requestId.current) return;
      setError(e instanceof Error ? e.message : 'The standings service did not respond.');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [year]);

  useEffect(() => { load(); }, [load]);

  const completed    = races.filter((r) => isPastDate(r.date));
  const nextRace     = races.find((r) => !isPastDate(r.date));
  const recentRaces  = [...completed].sort((a, b) => b.round - a.round).slice(0, 3);
  const seasonDone   = races.length > 0 && !nextRace;
  const leader       = drivers[0];
  const runnerUp     = drivers[1];
  const teamLeader   = teams[0];
  const nextIn       = nextRace ? daysUntil(nextRace.date) : null;

  return (
    <PageShell>
      <PageHeader
        title="Dashboard"
        subtitle={`Formula 1 analytics — ${year} season`}
        actions={
          <SelectField label="Year" value={year} onChange={(v) => setYear(Number(v))}>
            {YEAR_OPTIONS.map((y) => <option key={y} value={y}>{y}</option>)}
          </SelectField>
        }
      />

      <Tabs tabs={TABS} active={tab} onChange={setTab} label="Dashboard sections" idPrefix="dash" />

      <div className="pt-6">
        {tab === 'overview' && (
          <TabPanel id="overview" idPrefix="dash">
            {error ? (
              <Card><ErrorState title="Couldn't load the season overview" message={error} onRetry={load} /></Card>
            ) : (
              <FadeIn className="space-y-6">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <StatCard
                    label="Next Race" loading={loading} icon={<Calendar className="h-6 w-6" />}
                    value={nextRace ? gpToken(nextRace.race_name) : seasonDone ? 'Season complete' : '—'}
                    sub={nextRace ? `${formatDate(nextRace.date)} · ${describeDaysUntil(nextIn)}` : `${races.length} rounds`}
                  />
                  <StatCard
                    label={seasonDone ? "Drivers' Champion" : "Drivers' Leader"} loading={loading}
                    icon={<Users className="h-6 w-6" />} accent="text-turbo-teal"
                    value={leader?.driver_name ?? '—'}
                    sub={leader ? `${leader.points} pts${runnerUp ? ` · +${leader.points - runnerUp.points} on P2` : ''}` : undefined}
                  />
                  <StatCard
                    label={seasonDone ? "Constructors' Champion" : "Constructors' Leader"} loading={loading}
                    icon={<Flag className="h-6 w-6" />} accent="text-pit-stop-yellow"
                    value={teamLeader?.constructor_name ?? '—'}
                    sub={teamLeader ? `${teamLeader.points} pts` : undefined}
                  />
                  <StatCard
                    label="Season Progress" loading={loading} icon={<TrendingUp className="h-6 w-6" />}
                    value={races.length ? `${completed.length} / ${races.length}` : '—'}
                    sub={races.length ? `${races.length - completed.length} rounds remaining` : undefined}
                  />
                </div>

                <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                  <Card>
                    <CardHeader
                      title="Drivers' Championship" icon={<Users className="h-4 w-4" />}
                      action={<ViewAll onClick={() => setTab('drivers')} />}
                    />
                    {loading ? <LoadingState /> : drivers.length ? (
                      <TableWrap>
                        <tbody>
                          {drivers.slice(0, TOP_N).map((d) => (
                            <Tr key={d.driver_id}>
                              <Td className="w-14 pr-0"><PositionBadge position={d.position} /></Td>
                              <Td className="font-medium text-white">{d.driver_name}</Td>
                              <Td className="hidden text-gray-400 sm:table-cell"><TeamChip name={d.constructor} /></Td>
                              <Td align="right" className="font-bold text-white">{d.points}</Td>
                            </Tr>
                          ))}
                        </tbody>
                      </TableWrap>
                    ) : <EmptyState title="No driver standings yet" />}
                  </Card>

                  <Card>
                    <CardHeader
                      title="Constructors' Championship" icon={<Flag className="h-4 w-4" />}
                      action={<ViewAll onClick={() => setTab('teams')} />}
                    />
                    {loading ? <LoadingState /> : teams.length ? (
                      <TableWrap>
                        <tbody>
                          {teams.slice(0, TOP_N).map((t) => (
                            <Tr key={t.constructor_id}>
                              <Td className="w-14 pr-0"><PositionBadge position={t.position} /></Td>
                              <Td className="font-medium text-white"><TeamChip name={t.constructor_name} /></Td>
                              <Td align="right" className="font-bold text-white">{t.points}</Td>
                            </Tr>
                          ))}
                        </tbody>
                      </TableWrap>
                    ) : <EmptyState title="No constructor standings yet" />}
                  </Card>
                </div>

                <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                  <Card>
                    <CardHeader
                      title="Recent Races" icon={<BarChart3 className="h-4 w-4" />}
                      action={<ViewAll onClick={() => setTab('results')} label="All results" />}
                    />
                    {loading ? <LoadingState /> : recentRaces.length ? (
                      <ul>
                        {recentRaces.map((r) => (
                          <li key={r.round} className="border-b border-gray-800/60 last:border-b-0">
                            <Link
                              to={`/dashboard?tab=results&year=${year}&gp=${encodeURIComponent(gpToken(r.race_name))}`}
                              className="flex items-center justify-between gap-3 px-5 py-3 transition-colors hover:bg-gray-800/40 focus:outline-none focus-visible:bg-gray-800/60"
                            >
                              <span className="flex min-w-0 items-center gap-3">
                                <span className="w-8 text-sm font-bold text-racing-red">R{r.round}</span>
                                <span className="min-w-0">
                                  <span className="block truncate text-sm font-medium text-white">{r.race_name}</span>
                                  <span className="block text-xs text-gray-500">{r.country}</span>
                                </span>
                              </span>
                              <span className="flex items-center gap-2 text-xs text-gray-500">
                                {formatDate(r.date)}<ChevronRight className="h-4 w-4" aria-hidden="true" />
                              </span>
                            </Link>
                          </li>
                        ))}
                      </ul>
                    ) : <EmptyState title="No completed races yet this season" />}
                  </Card>

                  <Card>
                    <CardHeader
                      title={seasonDone ? 'Season Finale' : 'Next Race'} icon={<MapPin className="h-4 w-4" />}
                      action={<ViewAll onClick={() => setTab('tracks')} label="Calendar" />}
                    />
                    {loading ? <LoadingState /> : (nextRace ?? races[races.length - 1]) ? (
                      <DetailList
                        rows={(() => {
                          const r = (nextRace ?? races[races.length - 1])!;
                          return [
                            ['Race', r.race_name],
                            ['Circuit', r.circuit_name],
                            ['Country', r.country],
                            ['Date', `${formatDate(r.date)}${nextRace ? ` · ${describeDaysUntil(nextIn)}` : ''}`],
                          ];
                        })()}
                      />
                    ) : <EmptyState title="No races on the calendar" />}
                  </Card>
                </div>
              </FadeIn>
            )}
          </TabPanel>
        )}

        {tab === 'drivers' && <TabPanel id="drivers" idPrefix="dash"><DriverAnalytics year={year} /></TabPanel>}
        {tab === 'title'   && <TabPanel id="title"   idPrefix="dash"><ChampionshipOutlook year={year} /></TabPanel>}
        {tab === 'tracks'  && <TabPanel id="tracks"  idPrefix="dash"><TrackAnalytics  year={year} /></TabPanel>}
        {tab === 'results' && (
          <TabPanel id="results" idPrefix="dash">
            <RaceResults year={year} initialGp={params.get('gp') ?? undefined} />
          </TabPanel>
        )}

        {tab === 'teams' && (
          <TabPanel id="teams" idPrefix="dash">
            <ConstructorAnalytics year={year} teams={teams} loading={loading} error={error} onRetry={load} />
          </TabPanel>
        )}
      </div>
    </PageShell>
  );
};

const ViewAll: React.FC<{ onClick: () => void; label?: string }> = ({ onClick, label = 'View all' }) => (
  <button
    type="button"
    onClick={onClick}
    className="flex items-center gap-1 rounded text-xs font-medium text-gray-400 transition-colors hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/60"
  >
    {label}<ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
  </button>
);

export default Dashboard;
