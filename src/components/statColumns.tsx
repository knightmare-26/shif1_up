import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Columns3 } from 'lucide-react';
import { CheckboxMenu } from './ui';

// Optional win/podium columns shared by the Drivers and Teams tabs. Off by default; the choice is
// kept in the URL (?cols=race_wins,sprint_podiums) and applies to both tabs. The standings feed has
// no podiums and doesn't split sprint from race wins, so these are counted from the stored results
// (2022 onwards) — GET /api/driver-stats and /api/constructor-stats.
export const STAT_COLUMNS = [
  { id: 'race_wins', label: 'Race wins', short: 'Wins' },
  { id: 'race_podiums', label: 'Race podiums', short: 'Podiums' },
  { id: 'sprint_wins', label: 'Sprint wins', short: 'Sprint wins' },
  { id: 'sprint_podiums', label: 'Sprint podiums', short: 'Sprint podiums' },
] as const;
export type StatColumn = typeof STAT_COLUMNS[number]['id'];
const STAT_IDS: string[] = STAT_COLUMNS.map((c) => c.id);

export interface CountedStats {
  races_counted: number;
  sprints_counted: number;
}

/** The chosen columns, read from and written to the URL. */
export function useStatColumns(): [StatColumn[], (next: string[]) => void] {
  const [params, setParams] = useSearchParams();
  const columns = (params.get('cols') ?? '').split(',').filter((c): c is StatColumn => STAT_IDS.includes(c));
  const setColumns = (next: string[]) => {
    const p = new URLSearchParams(params);
    if (next.length) p.set('cols', next.join(','));
    else p.delete('cols');
    setParams(p, { replace: true });
  };
  return [columns, setColumns];
}

/** Fetches the counts only once a column is switched on; stale responses are ignored. */
export function useResultStats<T extends CountedStats>(fetch: (year: number) => Promise<T>, year: number, wanted: boolean) {
  const [stats, setStats] = useState<T | null>(null);
  const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle');
  const request = useRef(0);

  const load = useCallback(async () => {
    const id = ++request.current;
    setState('loading');
    try {
      const data = await fetch(year);
      if (id !== request.current) return;
      setStats(data);
      setState('idle');
    } catch {
      if (id === request.current) setState('error');
    }
  }, [fetch, year]);

  useEffect(() => {
    setStats(null);
    if (wanted) load();
  }, [wanted, load]);

  return { stats, state, reload: load };
}

export const StatColumnsMenu: React.FC<{ columns: StatColumn[]; onChange: (next: string[]) => void }> = ({ columns, onChange }) => (
  <CheckboxMenu
    label="Columns"
    icon={<Columns3 className="h-4 w-4" aria-hidden="true" />}
    options={STAT_COLUMNS.map(({ id, label }) => ({ id, label }))}
    selected={columns}
    onChange={onChange}
  />
);

/** Caption under the table title: what the counts cover, or why they're missing. */
export function statsNote(
  wanted: boolean, stats: CountedStats | null, state: 'idle' | 'loading' | 'error', empty: boolean,
  year: number, reload: () => void, extra = '',
): React.ReactNode {
  if (!wanted) return null;
  if (state === 'error') {
    return <>Couldn't load wins and podiums. <button type="button" onClick={reload} className="text-racing-red underline">Try again</button></>;
  }
  if (stats && empty) {
    return `Wins and podiums are counted from stored race results, which start in 2022 — not available for ${year}.`;
  }
  if (stats) {
    return `Wins and podiums counted from ${stats.races_counted} ${stats.races_counted === 1 ? 'race' : 'races'}`
      + `${stats.sprints_counted ? ` and ${stats.sprints_counted} ${stats.sprints_counted === 1 ? 'sprint' : 'sprints'}` : ''}.${extra}`;
  }
  return null;
}

/** One stat cell: "…" while loading, "—" when there's no count for that row. */
export function statValue(value: number | undefined, loading: boolean): React.ReactNode {
  if (loading) return <span className="text-gray-600">…</span>;
  return value ?? <span className="text-gray-600">—</span>;
}
