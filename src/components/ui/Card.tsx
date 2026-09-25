import React from 'react';
import { Info } from 'lucide-react';

export const Card: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => <section className={`rounded-xl border border-gray-800 bg-gray-900 ${className}`}>{children}</section>;

export const CardHeader: React.FC<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  icon?: React.ReactNode;
  action?: React.ReactNode;
}> = ({ title, subtitle, icon, action }) => (
  <div className="flex items-center justify-between gap-3 border-b border-gray-800 px-5 py-4">
    <div className="min-w-0">
      <h2 className="flex items-center gap-2 text-base font-semibold text-white">
        {icon && <span className="text-racing-red" aria-hidden="true">{icon}</span>}
        <span className="truncate">{title}</span>
      </h2>
      {subtitle && <p className="mt-0.5 text-xs text-gray-400">{subtitle}</p>}
    </div>
    {action && <div className="flex-shrink-0">{action}</div>}
  </div>
);

export const CardBody: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => <div className={`p-5 ${className}`}>{children}</div>;

/** The "How this works" card at the foot of a data view: method, caveats and track record, in
 *  the same place and style on every tab. Children are paragraphs. */
export const HowItWorksCard: React.FC<{ children: React.ReactNode; title?: string }> = ({
  children,
  title = 'How this works',
}) => (
  <Card>
    <CardHeader title={title} icon={<Info className="h-4 w-4" />} />
    <CardBody className="space-y-3 text-sm leading-relaxed text-gray-400">{children}</CardBody>
  </Card>
);

/** Label / value rows inside a card (race details, session info, ...). */
export const DetailList: React.FC<{ rows: (string | number)[][] }> = ({ rows }) => (
  <dl className="divide-y divide-gray-800/60">
    {rows.map(([label, value]) => (
      <div key={label} className="flex items-center justify-between gap-4 px-5 py-3">
        <dt className="text-sm text-gray-400">{label}</dt>
        <dd className="text-right text-sm font-medium text-white">{value}</dd>
      </div>
    ))}
  </dl>
);

/** Headline number with a label — the summary row at the top of every page. */
export const StatCard: React.FC<{
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  icon?: React.ReactNode;
  /** Tailwind text colour for the icon. */
  accent?: string;
  loading?: boolean;
}> = ({ label, value, sub, icon, accent = 'text-racing-red', loading }) => (
  <Card className="flex items-start justify-between gap-3 p-5">
    <div className="min-w-0">
      <p className="text-xs uppercase tracking-wide text-gray-500">{label}</p>
      {loading ? (
        <div className="mt-2 h-6 w-28 animate-pulse rounded bg-gray-800" aria-hidden="true" />
      ) : (
        <>
          <p className="mt-1 line-clamp-2 break-words text-xl font-bold leading-tight tabular-nums text-white sm:text-2xl">{value}</p>
          {sub && <p className="mt-1 text-xs text-gray-500">{sub}</p>}
        </>
      )}
    </div>
    {icon && <span className={`flex-shrink-0 ${accent}`} aria-hidden="true">{icon}</span>}
  </Card>
);
