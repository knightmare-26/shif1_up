import React from 'react';
import { Link } from 'react-router-dom';
import { Wordmark } from './ui';

const LINKS = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/dashboard?tab=results', label: 'Race Results' },
  { to: '/predictions', label: 'Predictions' },
  { to: '/predictions?tab=title', label: 'Title Race' },
];

/** The slim footer on every page: links in small capitals on the left, the badge on the right. */
const SiteFooter: React.FC = () => (
  <footer className="mt-16 border-t border-white/10 bg-[#0c0c0c]">
    <div className="mx-auto flex max-w-[1600px] flex-col gap-6 px-4 py-8 sm:flex-row sm:items-end sm:justify-between sm:px-6 lg:px-10">
      <div>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-2">
          {LINKS.map((l) => (
            <Link key={l.to} to={l.to} className="label text-gray-300 transition-colors hover:text-racing-red">{l.label}</Link>
          ))}
        </nav>
        <p className="label mt-4 text-muted">
          © {new Date().getFullYear()} Shif1 | Up · Not affiliated with Formula 1
        </p>
      </div>
      <Wordmark className="text-sm" />
    </div>
  </footer>
);

export default SiteFooter;
