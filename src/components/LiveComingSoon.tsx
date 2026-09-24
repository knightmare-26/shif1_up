import React from 'react';
import { Link } from 'react-router-dom';
import { Radio } from 'lucide-react';
import { Card, EmptyState, FadeIn, PageHeader, PageShell, Pill } from './ui';

const LINK = 'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/60';

/** Shown on both Live pages while LIVE_TIMING_ENABLED is off. */
const LiveComingSoon: React.FC = () => (
  <PageShell>
    <PageHeader title="Live" subtitle="Real-time timing during F1 sessions" actions={<Pill tone="warn">Coming soon</Pill>} />
    <FadeIn>
      <Card>
        <EmptyState
          icon={<Radio className="h-10 w-10" />}
          title="Live timing is coming soon"
          message="We're working on real-time positions, best laps, sectors and tyres for practice, qualifying, sprint and race sessions. Check back soon."
          action={
            <span className="flex flex-wrap justify-center gap-3">
              <Link to="/dashboard" className={`${LINK} bg-racing-red text-white hover:bg-red-700`}>Standings &amp; results</Link>
              <Link to="/predictions" className={`${LINK} border border-gray-700 bg-gray-800 text-gray-200 hover:bg-gray-700`}>Predictions</Link>
            </span>
          }
        />
      </Card>
    </FadeIn>
  </PageShell>
);

export default LiveComingSoon;
