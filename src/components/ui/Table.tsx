import React from 'react';
import { teamColor } from './teamColors';

type Align = 'left' | 'right' | 'center';
const ALIGN: Record<Align, string> = { left: 'text-left', right: 'text-right', center: 'text-center' };

/** Horizontally scrollable table container — the page body never scrolls sideways. */
export const TableWrap: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => (
  <div className={`overflow-x-auto ${className}`}>
    <table className="w-full text-sm">{children}</table>
  </div>
);

export const Th: React.FC<{
  children?: React.ReactNode;
  align?: Align;
  className?: string;
}> = ({ children, align = 'left', className = '' }) => (
  <th
    scope="col"
    className={`whitespace-nowrap px-4 py-3 text-xs font-medium uppercase tracking-wide text-gray-500 ${ALIGN[align]} ${className}`}
  >
    {children}
  </th>
);

export const Td: React.FC<{
  children?: React.ReactNode;
  align?: Align;
  className?: string;
}> = ({ children, align = 'left', className = '' }) => (
  <td className={`px-4 py-3 tabular-nums ${ALIGN[align]} ${className}`}>{children}</td>
);

export const Tr: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = '',
}) => (
  <tr className={`border-b border-gray-800/60 transition-colors last:border-b-0 hover:bg-gray-800/40 ${className}`}>
    {children}
  </tr>
);

/** Gold / silver / bronze for the podium, muted for the rest. */
export const PositionBadge: React.FC<{ position: number | string; label?: string }> = ({
  position,
  label,
}) => {
  const n = Number(position);
  const tone =
    n === 1
      ? 'border-yellow-400/40 bg-yellow-400/10 text-yellow-400'
      : n === 2
      ? 'border-gray-400/40 bg-gray-400/10 text-gray-200'
      : n === 3
      ? 'border-amber-500/40 bg-amber-500/10 text-amber-500'
      : 'border-gray-700 text-gray-400';
  return (
    <span
      className={`inline-flex h-7 min-w-[1.75rem] items-center justify-center rounded-md border px-1.5 text-xs font-bold tabular-nums ${tone}`}
    >
      {label ?? position}
    </span>
  );
};

/** Team name with its livery colour. */
export const TeamChip: React.FC<{ name?: string | null; color?: string; className?: string }> = ({
  name,
  color,
  className = '',
}) => (
  <span className={`inline-flex items-center gap-2 ${className}`}>
    <span
      className="h-4 w-1 flex-shrink-0 rounded-sm"
      style={{ backgroundColor: color ?? teamColor(name) }}
      aria-hidden="true"
    />
    <span className="truncate">{name || '—'}</span>
  </span>
);
