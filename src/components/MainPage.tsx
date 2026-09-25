import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, ArrowRight, Calendar, Car, Flag, ListOrdered, MapPin, TrendingUp, Users } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { backendApi, ConstructorStanding, DriverStanding, RaceEvent } from '../services/backendApi';
import { describeDaysUntil, daysUntil, formatDate, isPastDate } from '../utils/dates';
import { gpToken, isRaceRound } from '../utils/races';
import { useLiveTiming } from '../config/features';
import { Button, Card, FadeIn, PageShell, Pill, StatCard } from './ui';

const features = (liveOn: boolean) => [
  { to: '/dashboard',                 icon: Users,       title: 'Championship Standings', text: 'Driver and constructor points, season by season.' },
  { to: '/dashboard?tab=results',     icon: ListOrdered, title: 'Race Results',           text: 'Full classifications for races, qualifying, sprints and practice.' },
  { to: '/predictions',               icon: TrendingUp,  title: 'Predictions',            text: 'Qualifying and race forecasts, checked against what actually happened.' },
  { to: '/live',                      icon: Activity,    title: 'Live Timing',            text: 'Positions and gaps as they change during a session.', soon: !liveOn },
];

const MainPage: React.FC = () => {
  const { isAuthenticated, user } = useAuth();
  const { enabled: liveOn } = useLiveTiming();
  const year = new Date().getFullYear();

  const [drivers, setDrivers] = useState<DriverStanding[]>([]);
  const [teams, setTeams] = useState<ConstructorStanding[]>([]);
  const [races, setRaces] = useState<RaceEvent[]>([]);
  const [loading, setLoading] = useState(true);

  // A live snapshot of the season; if any of it fails the page still works.
  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([
      backendApi.getDriverStandings(year),
      backendApi.getConstructorStandings(year),
      backendApi.getRaceSchedule(year),
    ]).then(([d, c, r]) => {
      if (cancelled) return;
      if (d.status === 'fulfilled' && Array.isArray(d.value)) setDrivers(d.value);
      if (c.status === 'fulfilled' && Array.isArray(c.value)) setTeams(c.value);
      if (r.status === 'fulfilled' && Array.isArray(r.value)) setRaces(r.value.filter(isRaceRound));
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [year]);

  const nextRace = races.find((r) => !isPastDate(r.date));
  const nextIn = nextRace ? daysUntil(nextRace.date) : null;
  const leader = drivers[0];
  const teamLeader = teams[0];
  const hasSnapshot = loading || nextRace || leader || teamLeader;

  return (
    <PageShell>
      <FadeIn>
        <section className="max-w-3xl py-8 sm:py-12">
          {isAuthenticated && user ? (
            <p className="mb-2 text-sm text-gray-400">Welcome back, {user.username}</p>
          ) : null}
          <h1 className="font-racing text-5xl leading-tight text-racing-red sm:text-6xl">Shif1 UP</h1>
          <p className="mt-3 text-xl text-white">Your F1 insights hub</p>
          <p className="mt-4 max-w-2xl text-base leading-relaxed text-gray-400">
            Championship standings, race results, model-based predictions{liveOn ? ' and live timing' : ''} for
            Formula 1 — all in one place, no account needed.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/dashboard"><Button icon={<ArrowRight className="h-4 w-4" />}>Open dashboard</Button></Link>
            <Link to="/predictions"><Button variant="secondary" icon={<TrendingUp className="h-4 w-4" />}>See predictions</Button></Link>
          </div>
        </section>
      </FadeIn>

      {hasSnapshot && (
        <section aria-label={`${year} season snapshot`} className="mb-8">
          <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-gray-500">{year} season snapshot</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard label="Next Race" loading={loading} icon={<Calendar className="h-6 w-6" />}
              value={nextRace ? gpToken(nextRace.race_name) : '—'}
              sub={nextRace ? `${formatDate(nextRace.date)} · ${describeDaysUntil(nextIn)}` : 'Season complete'} />
            <StatCard label="Drivers' Leader" loading={loading} icon={<Users className="h-6 w-6" />} accent="text-turbo-teal"
              value={leader?.driver_name ?? '—'} sub={leader ? `${leader.points} pts` : undefined} />
            <StatCard label="Constructors' Leader" loading={loading} icon={<Flag className="h-6 w-6" />} accent="text-pit-stop-yellow"
              value={teamLeader?.constructor_name ?? '—'} sub={teamLeader ? `${teamLeader.points} pts` : undefined} />
          </div>
        </section>
      )}

      {isAuthenticated && user && (
        <section aria-label="Your preferences" className="mb-8">
          <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-gray-500">Your preferences</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Favorite Driver" icon={<Car className="h-6 w-6" />} value={user.preferences.favoriteDriver} />
            <StatCard label="Favorite Track" icon={<MapPin className="h-6 w-6" />} accent="text-turbo-teal" value={user.preferences.favoriteTrack} />
            <StatCard label="Favorite Team" icon={<Flag className="h-6 w-6" />} accent="text-pit-stop-yellow" value={user.preferences.favoriteTeam} />
            <StatCard label="Experience" icon={<TrendingUp className="h-6 w-6" />}
              value={<span className="capitalize">{user.preferences.experienceLevel}</span>} />
          </div>
        </section>
      )}

      <section aria-label="What you can do here" className="pb-8">
        <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-gray-500">Explore</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {features(liveOn).map(({ to, icon: Icon, title, text, soon }) => (
            <Link
              key={to}
              to={to}
              className="group rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/60"
            >
              <Card className="h-full p-5 transition-colors group-hover:border-gray-600">
                <Icon className="mb-4 h-6 w-6 text-racing-red" aria-hidden="true" />
                <h3 className="flex items-center justify-between font-semibold text-white">
                  {title}
                  <ArrowRight className="h-4 w-4 text-gray-600 transition-colors group-hover:text-white" aria-hidden="true" />
                </h3>
                <p className="mt-1 text-sm text-gray-400">{text}</p>
                {soon && <div className="mt-3"><Pill tone="warn">Coming soon</Pill></div>}
              </Card>
            </Link>
          ))}
        </div>
      </section>
    </PageShell>
  );
};

export default MainPage;
