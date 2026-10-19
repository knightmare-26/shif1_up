import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { backendApi, ChampionshipOutlook, ConstructorStanding, DriverStanding, RaceEvent } from '../services/backendApi';
import { describeDaysUntil, daysUntil, formatDate, isPastDate } from '../utils/dates';
import { isRaceRound } from '../utils/races';
import { useLiveTiming } from '../config/features';
import { teamColor } from './ui';
import { Typewriter } from './home/Typewriter';
import { ScrollStatement } from './home/ScrollStatement';
import { CircuitArt } from './home/CircuitArt';
import { ContendersCarousel, splitName } from './home/ContendersCarousel';
import { Faq, FaqItem } from './home/Faq';

const PHRASES = ['PREDICT THE GRID', 'READ THE RACE', 'PROVE THE PACE', 'CHASE THE TITLE'];

/** "BRAND | SECTION" section heading: red, a thin bar, white. */
const SectionTitle: React.FC<{ red: string; white: string; id?: string }> = ({ red, white, id }) => (
  <h2 id={id} className="display text-[clamp(2.4rem,5vw,4.5rem)] uppercase">
    <span className="text-racing-red">{red}</span>
    <span className="mx-[0.22em] font-light text-white/80">|</span>
    <span className="text-white">{white}</span>
  </h2>
);

/** The small red tab in a tile's corner. */
const TileTag: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span className="label absolute bottom-5 right-5 bg-racing-red px-3 py-2 text-white transition-colors group-hover:bg-white group-hover:text-black">
    {children}
  </span>
);

const FAQ: FaqItem[] = [
  { q: 'Where does the data come from?',
    a: 'Results and timing from FastF1 and OpenF1, standings and calendars from Jolpica (the successor to the Ergast API). Each session is stored by itself after it finishes — usually within half an hour of the flag.' },
  { q: 'How are the predictions made?',
    a: 'Ranking models trained on every race since 2022 — gradient-boosted trees and a linear model, averaged — from recent form, form at the circuit, the team\'s pace, practice, reliability and the grid. The chances come from playing each session out 20,000 times.' },
  { q: 'How good are they?',
    a: 'Every race is re-predicted by a model that never saw it and scored in Predicted vs Actual: about three places off per driver on average, and the winner named roughly two times in three once the grid is known.' },
  { q: 'When does it update?',
    a: 'After every session. New results are stored by themselves, the last two weeks are re-checked for post-race penalties, and over a race weekend it checks every 15 minutes after each session ends.' },
  { q: 'Is there live timing?',
    a: 'Not yet. Finished sessions can be replayed lap by lap, with the weather, on Race Results.' },
  { q: 'Do I need an account?', a: 'No. Everything here is open.' },
];

const EXPLORE = [
  { to: '/dashboard', tag: 'Standings', title: 'The championship', text: 'Driver and constructor tables, season by season back to 2000, with wins, podiums, poles and sprint results.' },
  { to: '/dashboard?tab=results', tag: 'Results', title: 'Every session', text: 'Practice to the race: classifications, the stewards\' decisions, the weather and a lap-by-lap replay.' },
  { to: '/predictions', tag: 'Predictions', title: 'The next race', text: 'Qualifying, sprint and race orders with pole, win and podium chances — and how every past prediction held up.' },
  { to: '/predictions?tab=title', tag: 'Title race', title: 'Who can still win', text: 'The exact maths of who\'s still in it, and the rest of the season played out 10,000 times.' },
];

const MainPage: React.FC = () => {
  const { isAuthenticated, user } = useAuth();
  const { enabled: liveOn } = useLiveTiming();
  const year = new Date().getFullYear();

  const [drivers, setDrivers] = useState<DriverStanding[]>([]);
  const [teams, setTeams] = useState<ConstructorStanding[]>([]);
  const [races, setRaces] = useState<RaceEvent[]>([]);
  const [outlook, setOutlook] = useState<ChampionshipOutlook | null>(null);
  const [loading, setLoading] = useState(true);

  // The season at a glance; any part may fail and the page still works. The title chances come
  // after (they can take a while on a freshly woken server).
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
    backendApi.getChampionshipOutlook('drivers', year).then((o) => { if (!cancelled) setOutlook(o); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [year]);

  const nextRace = races.find((r) => !isPastDate(r.date));
  const nextIn = nextRace ? daysUntil(nextRace.date) : null;
  const leader = drivers[0];
  const second = drivers[1];
  const teamLeader = teams[0];
  const [leaderFirst, leaderLast] = splitName(leader?.driver_name ?? '');
  const gpName = nextRace ? nextRace.race_name.replace(/\s*Grand Prix$/i, '') : '';

  return (
    <div className="-mt-px">
      {/* ---------------------------------------------------------------- hero */}
      <section className="grid gap-2 bg-black p-2 lg:h-[calc(100vh-4rem)] lg:min-h-[620px] lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="relative isolate flex min-h-[560px] flex-col justify-end overflow-hidden bg-[#0a0a0a] p-6 sm:p-10 lg:p-14">
          <div aria-hidden="true" className="absolute inset-0 -z-10"
            style={{ background: 'radial-gradient(ellipse at 15% 95%, rgba(228,35,32,0.45), transparent 55%), radial-gradient(ellipse at 85% 10%, rgba(255,255,255,0.06), transparent 50%)' }} />
          <div aria-hidden="true" className="absolute inset-0 -z-10 opacity-[0.05]"
            style={{ backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)', backgroundSize: '64px 64px' }} />
          <CircuitArt className="absolute -right-10 top-4 -z-10 w-[85%] max-w-[900px] text-white sm:top-0" />

          {isAuthenticated && user && <p className="label mb-4 text-muted">Welcome back, {user.username}</p>}
          <p className="label text-racing-red">Formula 1 · {year} season</p>
          <h1 className="display mt-4 min-h-[2.1em] text-[clamp(3rem,7.4vw,7rem)] uppercase text-white sm:min-h-[1.05em]">
            <span className="sr-only">Shif1 UP — Formula 1 standings, results and predictions</span>
            <Typewriter phrases={PHRASES} />
          </h1>
          <p className="mt-4 text-lg italic text-muted sm:text-2xl">Shift·up — ‘to change into a higher gear’.</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/predictions" className="btn-primary">See predictions</Link>
            <Link to="/dashboard" className="btn-secondary">Open dashboard</Link>
          </div>
        </div>

        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1 lg:grid-rows-2">
          <Link to="/predictions" className="group relative flex min-h-[260px] flex-col overflow-hidden bg-[#121212] p-6 focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red">
            {nextRace && (
              <span aria-hidden="true" className="display absolute -right-4 -top-6 select-none text-[11rem] text-transparent transition-colors group-hover:text-white/[0.04]"
                style={{ WebkitTextStroke: '1.5px rgba(255,255,255,0.18)' }}>{nextRace.round}</span>
            )}
            <p className="label text-muted">Next race{nextRace ? ` · Round ${nextRace.round}` : ''}</p>
            {loading ? (
              <div className="mt-4 h-10 w-48 animate-pulse bg-ink-700" />
            ) : nextRace ? (
              <>
                <p className="display mt-4 text-4xl uppercase text-white">{gpName}</p>
                <p className="label mt-1 text-white/70">Grand Prix{nextRace.is_sprint ? ' · Sprint weekend' : ''}</p>
                <p className="mt-auto pr-28 text-sm text-gray-300">{formatDate(nextRace.date)} · {describeDaysUntil(nextIn)}</p>
              </>
            ) : (
              <p className="display mt-4 text-3xl uppercase text-white">Season complete</p>
            )}
            <TileTag>Predict it</TileTag>
          </Link>

          <Link to="/predictions?tab=title" className="group relative flex min-h-[260px] flex-col overflow-hidden p-6 focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red"
            style={{ background: leader ? `linear-gradient(160deg, ${teamColor(leader.constructor)}55 0%, #121212 60%)` : '#121212' }}>
            <p className="label text-muted">Drivers' championship</p>
            {loading ? (
              <div className="mt-4 h-10 w-48 animate-pulse bg-ink-700" />
            ) : leader ? (
              <>
                <p className="display mt-4 text-4xl text-white">
                  {leaderFirst && <span className="font-light">{leaderFirst} </span>}
                  <span className="uppercase">{leaderLast}</span>
                </p>
                <p className="label mt-1 text-white/70">{leader.constructor}</p>
                <p className="mt-auto pr-28 text-sm text-gray-300">
                  {leader.points} pts{second ? ` · ${Math.round((leader.points - second.points) * 10) / 10} ahead of ${splitName(second.driver_name)[1]}` : ''}
                </p>
              </>
            ) : (
              <p className="mt-4 text-gray-400">Standings appear after the first race.</p>
            )}
            <TileTag>Title race</TileTag>
          </Link>
        </div>
      </section>

      {/* ---------------------------------------------------------------- statement */}
      <ScrollStatement text="Standings, results and predictions — proven against every race." highlight={['proven']} />

      {/* ---------------------------------------------------------------- the title fight */}
      {drivers.length > 0 && (
        <div className="pb-28">
          <div className="mx-auto mb-12 max-w-[1600px] px-4 sm:px-6 lg:px-10">
            <SectionTitle red="Title" white="Fight" />
            <p className="mt-3 text-lg italic text-muted">The top five, as the {year} championship stands.</p>
          </div>
          <ContendersCarousel drivers={drivers} outlook={outlook} />
        </div>
      )}

      {/* ---------------------------------------------------------------- predict the next race */}
      <section className="relative isolate overflow-hidden border-y border-white/5 bg-[#070707] py-28">
        <div aria-hidden="true" className="absolute inset-0 -z-10 flex -rotate-12 scale-125 flex-col justify-center gap-6 opacity-[0.11]">
          {Array.from({ length: 7 }, (_, row) => (
            <p key={row} className="display whitespace-nowrap text-7xl text-racing-red" style={{ marginLeft: `${(row % 2) * -6}rem` }}>
              {'SHIF1+ '.repeat(14)}
            </p>
          ))}
        </div>
        <div className="mx-auto grid max-w-[1600px] items-center gap-12 px-4 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:px-10">
          <div>
            <h2 className="display text-[clamp(2.4rem,5vw,4.5rem)] uppercase text-white">
              Predict the <span className="text-racing-red">{nextRace ? gpName : 'next race'}</span>
            </h2>
            <ul className="mt-8 space-y-3">
              {['Qualifying order, pole and top-3 chances', 'Win and podium chances from 20,000 simulated races',
                'The title race, played out 10,000 times', 'Every prediction checked against the result'].map((t) => (
                <li key={t} className="label text-[13px] text-white"><span className="mr-2 text-white/60">|</span>{t}</li>
              ))}
            </ul>
            <Link to="/predictions"
              className="label mt-10 inline-flex items-center gap-2 border border-racing-red px-5 py-3 text-[13px] text-racing-red transition-colors hover:bg-racing-red hover:text-white">
              Open predictions <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
          <CircuitArt className="w-full text-white/80" lapSeconds={8} />
        </div>
      </section>

      {/* ---------------------------------------------------------------- explore */}
      <section className="mx-auto max-w-[1600px] px-4 py-28 sm:px-6 lg:px-10" aria-labelledby="explore">
        <SectionTitle id="explore" red="Shif1" white="Explore" />
        <div className="mt-14 grid gap-12 md:grid-cols-2">
          {EXPLORE.map((e) => (
            <div key={e.to} className="flex gap-6">
              <span className="w-px flex-shrink-0 bg-white" aria-hidden="true" />
              <div>
                <p className="label text-white">{e.tag}<span className="mx-2">|</span><span className="text-racing-red">Shif1</span></p>
                <h3 className="display mt-2 text-3xl text-white">{e.title}</h3>
                <p className="mt-3 max-w-md leading-relaxed text-gray-300">{e.text}</p>
                <Link to={e.to}
                  className="label mt-5 inline-flex items-center gap-2 border border-white/70 px-4 py-2.5 text-white transition-colors hover:bg-white hover:text-black">
                  Open <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                </Link>
              </div>
            </div>
          ))}
        </div>
        {teamLeader && (
          <p className="mt-14 text-sm italic text-muted">
            Constructors: {teamLeader.constructor_name} lead on {teamLeader.points} points.
            {liveOn ? ' Live timing is on.' : ''}
          </p>
        )}
      </section>

      {/* ---------------------------------------------------------------- faq */}
      <section className="mx-auto max-w-[1600px] px-4 pb-12 sm:px-6 lg:px-10" aria-labelledby="faq">
        <div className="mb-12 text-center"><SectionTitle id="faq" red="Shif1" white="FAQ" /></div>
        <Faq items={FAQ} />
      </section>
    </div>
  );
};

export default MainPage;
