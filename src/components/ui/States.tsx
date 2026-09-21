import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from './Fields';

/** Inline loading indicator — sits inside a card so the page frame never jumps. */
export const LoadingState: React.FC<{ label?: string; className?: string }> = ({
  label = 'Loading…',
  className = 'py-16',
}) => (
  <div role="status" className={`flex items-center justify-center gap-2 text-sm text-gray-400 ${className}`}>
    <RefreshCw className="h-4 w-4 animate-spin text-racing-red" aria-hidden="true" />
    {label}
  </div>
);

export const ErrorState: React.FC<{
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}> = ({ title = "Couldn't load this", message, onRetry, className = 'py-14' }) => (
  <div role="alert" className={`flex flex-col items-center px-4 text-center ${className}`}>
    <AlertTriangle className="mb-3 h-8 w-8 text-racing-red" aria-hidden="true" />
    <p className="font-semibold text-white">{title}</p>
    {message && <p className="mt-1 max-w-md text-sm text-gray-400">{message}</p>}
    {onRetry && (
      <Button variant="secondary" className="mt-4" onClick={onRetry}>
        Try again
      </Button>
    )}
  </div>
);

export const EmptyState: React.FC<{
  icon?: React.ReactNode;
  title: string;
  message?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}> = ({ icon, title, message, action, className = 'py-14' }) => (
  <div className={`flex flex-col items-center px-4 text-center ${className}`}>
    {icon && <span className="mb-3 text-gray-700" aria-hidden="true">{icon}</span>}
    <p className="font-medium text-gray-300">{title}</p>
    {message && <p className="mt-1 max-w-md text-sm text-gray-500">{message}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
);

const NOTICE_TONES = {
  warning: 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300',
  error: 'border-red-500/30 bg-red-500/10 text-red-300',
  info: 'border-gray-700 bg-gray-800/60 text-gray-300',
};

export const Notice: React.FC<{
  tone?: keyof typeof NOTICE_TONES;
  children: React.ReactNode;
  className?: string;
}> = ({ tone = 'info', children, className = 'mb-6' }) => (
  <div
    role={tone === 'error' ? 'alert' : undefined}
    className={`flex items-start gap-3 rounded-lg border px-4 py-3 text-sm ${NOTICE_TONES[tone]} ${className}`}
  >
    <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
    <div>{children}</div>
  </div>
);
