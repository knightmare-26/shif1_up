import React from 'react';
import { Check, RefreshCw } from 'lucide-react';
import { ServiceStatus, SERVER_WAKING_MESSAGE } from '../services/serviceStatus';
import { Button } from './ui';

// Longer than a normal cold start, so the wait screen never reads as broken too early.
const HINT_AFTER_S = 60;
const ESCALATE_AFTER_S = 120;

type StepState = 'done' | 'active' | 'pending';

const Step: React.FC<{ label: string; state: StepState }> = ({ label, state }) => (
  <li className="flex items-center gap-3 text-sm">
    <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center" aria-hidden="true">
      {state === 'done' ? (
        <Check className="h-4 w-4 text-green-400" />
      ) : state === 'active' ? (
        <RefreshCw className="h-4 w-4 text-racing-red motion-safe:animate-spin" />
      ) : (
        <span className="h-2 w-2 rounded-full bg-gray-700" />
      )}
    </span>
    <span className={state === 'pending' ? 'text-gray-500' : state === 'done' ? 'text-gray-300' : 'text-white'}>
      {label}
      <span className="sr-only"> — {state === 'done' ? 'done' : state === 'active' ? 'in progress' : 'waiting'}</span>
    </span>
  </li>
);

const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;

/**
 * Full-screen blurred wait screen shown instead of the pages until the API and its
 * database are both ready. It never traps the visitor: after a couple of minutes it
 * offers to retry or to open the site anyway.
 */
export const ServiceGate: React.FC<{
  status: ServiceStatus;
  visible: boolean;
  elapsed: number;
  onRetry: () => void;
  onContinue: () => void;
}> = ({ status, visible, elapsed, onRetry, onContinue }) => {
  if (!visible) return <div className="fixed inset-0 z-[60] bg-carbon-black" aria-hidden="true" />;

  const databaseWaking = status.state === 'database-waking';
  const stuck = elapsed >= ESCALATE_AFTER_S;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="gate-title"
      aria-describedby="gate-message"
      className="fixed inset-0 z-[60] flex items-center justify-center overflow-hidden bg-carbon-black/70 p-4 backdrop-blur-xl"
    >
      {/* soft glows behind the card — the "blur screen" */}
      <div className="pointer-events-none absolute -top-24 left-1/4 h-72 w-72 rounded-full bg-racing-red/25 blur-3xl" aria-hidden="true" />
      <div className="pointer-events-none absolute -bottom-20 right-1/4 h-80 w-80 rounded-full bg-turbo-teal/20 blur-3xl" aria-hidden="true" />

      <div className="relative w-full max-w-md rounded-2xl border border-gray-800 bg-gray-900/80 p-8 shadow-2xl backdrop-blur">
        <h2 id="gate-title" className="font-racing text-3xl text-racing-red">Shif1 UP</h2>
        <p className="mt-1 text-sm text-gray-400">Getting things ready</p>

        <ul className="mt-6 space-y-3" aria-label="Progress">
          <Step label="Waking the server" state={status.serverUp ? 'done' : 'active'} />
          <Step label="Waking the database" state={!status.serverUp ? 'pending' : databaseWaking ? 'active' : 'done'} />
          <Step label="Loading the site" state="pending" />
        </ul>

        <div aria-live="polite">
          <p id="gate-message" className="mt-6 text-sm leading-relaxed text-gray-300">
            {status.state === 'database-waking' ? status.message : SERVER_WAKING_MESSAGE}
          </p>
          <p className="mt-2 text-xs tabular-nums text-gray-500">Waiting {clock(elapsed)}</p>
          {elapsed >= HINT_AFTER_S && !stuck && (
            <p className="mt-3 text-sm text-gray-400">
              Still working — a paused database can take a few minutes to restore. This page opens by itself when it's ready.
            </p>
          )}
        </div>

        {stuck && (
          <div className="mt-5 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-4 text-sm text-yellow-200">
            <p className="font-medium">This is taking longer than expected.</p>
            <p className="mt-1 text-yellow-200/80">
              Pages that don't need the database can still be opened; the rest will load once it's back.
            </p>
            <div className="mt-3 flex flex-wrap gap-3">
              <Button variant="secondary" onClick={onRetry}>Try again now</Button>
              <Button onClick={onContinue}>Open the site anyway</Button>
            </div>
          </div>
        )}

        {status.detail && (
          <p className="mt-5 break-words border-t border-gray-800 pt-3 text-xs text-gray-500">
            Last check: {status.detail}
          </p>
        )}
      </div>
    </div>
  );
};
