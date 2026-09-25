import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Clock, Flag, Gauge, Radio, Timer } from 'lucide-react';
import { FadeIn, PageShell } from './ui';

const LINK = 'inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/60';

const COMING = [
  { icon: Timer, text: 'Positions, gaps and intervals' },
  { icon: Clock, text: 'Best laps and sector times' },
  { icon: Gauge, text: 'Tyres and pit stops' },
  { icon: Flag, text: 'Flags and safety cars' },
];

/** Shown on both Live pages while the API has no live feed connected and no replay running. */
const LiveComingSoon: React.FC = () => (
  <PageShell>
    <FadeIn>
      <section
        aria-labelledby="live-soon-title"
        className="relative mx-auto mt-6 max-w-3xl overflow-hidden rounded-2xl border border-racing-red/40 bg-gray-900 px-6 py-12 text-center sm:px-12"
      >
        <div className="absolute inset-x-0 top-0 h-1 bg-racing-red" aria-hidden="true" />

        <div className="relative mx-auto mb-6 flex h-20 w-20 items-center justify-center" aria-hidden="true">
          <span className="absolute inset-0 animate-ping rounded-full bg-racing-red/20" />
          <span className="relative flex h-20 w-20 items-center justify-center rounded-full bg-racing-red/15 ring-2 ring-racing-red/50">
            <Radio className="h-9 w-9 text-racing-red" />
          </span>
        </div>

        <p className="text-sm font-semibold uppercase tracking-[0.3em] text-gray-400">Live timing</p>
        <h1 id="live-soon-title" className="mt-2 font-racing text-5xl text-racing-red sm:text-6xl">Coming soon</h1>
        <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-gray-300">
          Follow practice, qualifying, sprints and races as they happen, on a live timing board built for this site.
          It switches on once the live data feed is connected.
        </p>

        <ul className="mx-auto mt-8 grid max-w-xl grid-cols-1 gap-3 text-left sm:grid-cols-2">
          {COMING.map(({ icon: Icon, text }) => (
            <li key={text} className="flex items-center gap-3 rounded-lg border border-gray-800 bg-gray-800/40 px-4 py-3 text-sm text-gray-200">
              <Icon className="h-4 w-4 flex-shrink-0 text-racing-red" aria-hidden="true" />
              {text}
            </li>
          ))}
        </ul>

        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link to="/predictions" className={`${LINK} bg-racing-red text-white hover:bg-red-700`}>
            See this weekend's predictions <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
          <Link to="/dashboard" className={`${LINK} border border-gray-700 bg-gray-800 text-gray-200 hover:bg-gray-700`}>
            Standings &amp; results
          </Link>
        </div>
      </section>
    </FadeIn>
  </PageShell>
);

export default LiveComingSoon;
