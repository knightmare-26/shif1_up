import React, { useState } from 'react';
import { qualifyingZone } from '../utils/races';
import { Card, Pill, TabPanel, Tabs, TableWrap, Th } from './ui';
import { teamColor } from './ui/teamColors';

export type SectorStatus = 'purple' | 'green' | 'yellow' | 'none';

export interface LiveSector { time: string | null; status: SectorStatus }
export interface LiveStint { compound: string | null; laps: number }

export interface LivePosition {
  position: number;
  driver_id: string;
  driver_name?: string;
  team?: string | null;
  gap?: string | null;
  interval?: string | null;
  last_lap_time?: string | null;
  best_lap_time?: string | null;
  best_lap_status?: 'purple' | 'green' | null;
  laps_completed?: number;
  tyre?: string | null;
  tyre_age?: number | null;
  stints?: LiveStint[];
  sectors?: LiveSector[];
  in_pit?: boolean;
  status: string;
}

export interface LiveState {
  // 'timed' sessions (practice, qualifying) are ordered by best lap and have no lap counter
  session?: string;
  session_type?: 'timed' | 'classified';
  positions?: LivePosition[];
  lap?: number;
  total_laps?: number;
  track_status?: string;
  session_status?: string;
  timestamp?: string;
}

type BoardTab = 'laps' | 'sectors' | 'tyres';
const BOARD_TABS: { id: BoardTab; label: string }[] = [
  { id: 'laps', label: 'Laps' },
  { id: 'sectors', label: 'Sectors' },
  { id: 'tyres', label: 'Tyres' },
];

const SECTOR_BAR: Record<SectorStatus, string> = {
  purple: 'bg-fuchsia-500',
  green: 'bg-green-500',
  yellow: 'bg-yellow-400',
  none: 'bg-gray-300',
};
const SECTOR_TEXT: Record<SectorStatus, string> = {
  purple: 'text-fuchsia-400',
  green: 'text-green-400',
  yellow: 'text-yellow-300',
  none: 'text-gray-500',
};
const SECTOR_WORD: Record<SectorStatus, string> = {
  purple: 'fastest of the session', green: 'personal best', yellow: 'slower', none: 'no time',
};

const COMPOUNDS: Record<string, { letter: string; color: string }> = {
  SOFT: { letter: 'S', color: 'text-red-500 border-red-500' },
  MEDIUM: { letter: 'M', color: 'text-yellow-400 border-yellow-400' },
  HARD: { letter: 'H', color: 'text-gray-100 border-gray-100' },
  INTERMEDIATE: { letter: 'I', color: 'text-green-500 border-green-500' },
  WET: { letter: 'W', color: 'text-blue-400 border-blue-400' },
};

const TyreBadge: React.FC<{ compound?: string | null; age?: number | null; laps?: number | null }> = ({ compound, age, laps }) => {
  const c = COMPOUNDS[(compound ?? '').toUpperCase()];
  const count = laps ?? age;
  return (
    <span className="inline-flex items-center gap-2" title={compound ? `${compound.toLowerCase()} tyre${age != null ? `, ${age} laps old` : ''}` : 'unknown tyre'}>
      {count != null && <span className={`text-xs tabular-nums ${c ? c.color.split(' ')[0] : 'text-gray-400'}`}>{count}</span>}
      <span className={`flex h-6 w-6 items-center justify-center rounded-full border-2 text-[11px] font-bold ${c ? c.color : 'border-gray-500 text-gray-400'}`}>
        {c?.letter ?? '?'}
      </span>
    </span>
  );
};

const SectorBar: React.FC<{ sector?: LiveSector; label: string }> = ({ sector, label }) => {
  const status = sector?.status ?? 'none';
  return (
    <span className="inline-block" title={`${label}: ${sector?.time ?? '—'} (${SECTOR_WORD[status]})`}>
      <span className={`block h-1.5 w-9 rounded-sm ${SECTOR_BAR[status]}`} />
      <span className="sr-only">{`${label} ${sector?.time ?? 'no time'}, ${SECTOR_WORD[status]}`}</span>
    </span>
  );
};

const surname = (p: LivePosition) => {
  const name = p.driver_name ?? p.driver_id;
  return (name.includes(' ') ? name.split(' ').slice(-1)[0] : name).toUpperCase();
};

const Driver: React.FC<{ p: LivePosition }> = ({ p }) => (
  <div className="flex items-center gap-3">
    <span className="w-6 text-right text-sm font-bold text-gray-300">{p.position}</span>
    <span className="h-5 w-1 rounded-full" style={{ backgroundColor: teamColor(p.team) }} aria-hidden="true" />
    <span className="font-semibold tracking-wide text-white">{surname(p)}</span>
  </div>
);

const ZoneRow: React.FC<{ label: string; cols: number }> = ({ label, cols }) => (
  <tr aria-hidden="true">
    <td colSpan={cols} className="border-b border-gray-800/60 bg-gray-800/40 px-4 py-1.5 text-xs font-medium uppercase tracking-wide text-gray-400">
      {label}
    </td>
  </tr>
);

const BestLap: React.FC<{ p: LivePosition }> = ({ p }) => (
  p.best_lap_time
    ? <span className={`rounded px-2 py-0.5 font-medium tabular-nums ${p.best_lap_status === 'purple' ? 'bg-fuchsia-500/15 text-fuchsia-400' : 'bg-green-500/10 text-green-400'}`}>{p.best_lap_time}</span>
    : <span className="text-gray-600">—</span>
);

/** The knockout zones drawn above a row, for qualifying and sprint qualifying only. */
const zoneLabel = (zone: 'Q3' | 'Q2' | 'Q1', total: number): string => {
  const out = Math.floor((total - 10) / 2);
  if (zone === 'Q3') return 'Through to Q3 · top 10';
  if (zone === 'Q2') return `Out in Q2 · positions 11–${10 + out}`;
  return `Out in Q1 · positions ${11 + out}–${total}`;
};

const rowClass = (p: LivePosition) => `border-b border-gray-800/60 transition-colors ${p.in_pit ? 'opacity-50' : ''}`;

const LiveTimingBoard: React.FC<{
  state: LiveState;
  sessionLabel: string;
  lastUpdate: Date | null;
}> = ({ state, sessionLabel, lastUpdate }) => {
  const [tab, setTab] = useState<BoardTab>('laps');
  const positions = state.positions ?? [];
  const isTimed = state.session_type === 'timed';
  const isQualifying = isTimed && (state.session === 'Q' || state.session === 'SQ');

  const rows = (columns: number, cells: (p: LivePosition) => React.ReactNode) =>
    positions.map((p, i) => {
      const zone = isQualifying ? qualifyingZone(p.position, positions.length) : null;
      const previous = i > 0 && isQualifying ? qualifyingZone(positions[i - 1].position, positions.length) : null;
      return (
        <React.Fragment key={p.driver_id}>
          {zone && zone !== previous && <ZoneRow label={zoneLabel(zone, positions.length)} cols={columns} />}
          <tr className={rowClass(p)}>{cells(p)}</tr>
        </React.Fragment>
      );
    });

  const cell = 'px-4 py-2 tabular-nums';

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-800 px-5 py-3">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-red-500">
            <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" aria-hidden="true" />
            Live
          </span>
          <span className="text-sm text-gray-300">{sessionLabel}</span>
          <span className="text-xs text-gray-500">
            {isTimed ? 'Best lap order' : state.lap ? `Lap ${state.lap}${state.total_laps ? ` / ${state.total_laps}` : ''}` : ''}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {state.session_status && <Pill tone="good">{state.session_status}</Pill>}
          {state.track_status && <Pill>Track {state.track_status}</Pill>}
          {lastUpdate && <Pill>Updated {lastUpdate.toLocaleTimeString()}</Pill>}
        </div>
      </div>

      <div className="px-2">
        <Tabs tabs={BOARD_TABS} active={tab} onChange={setTab} label="Timing views" idPrefix="board" />
      </div>

      {tab === 'laps' && (
        <TabPanel id="laps" idPrefix="board">
          <TableWrap>
            <thead>
              <tr className="border-b border-gray-800">
                <Th>Position</Th><Th align="center">Best lap</Th><Th align="right">Gap</Th>
                <Th align="center">S1</Th><Th align="center">S2</Th><Th align="center">S3</Th>
                <Th align="center">Tyre</Th><Th align="right">Laps</Th>
              </tr>
            </thead>
            <tbody>
              {rows(8, (p) => (
                <>
                  <td className={cell}><Driver p={p} /></td>
                  <td className={`${cell} text-center`}><BestLap p={p} /></td>
                  <td className={`${cell} text-right text-gray-300`}>{p.gap ?? ''}</td>
                  {[0, 1, 2].map((s) => (
                    <td key={s} className={`${cell} text-center`}><SectorBar sector={p.sectors?.[s]} label={`S${s + 1}`} /></td>
                  ))}
                  <td className={`${cell} text-center`}><TyreBadge compound={p.tyre} age={p.tyre_age} /></td>
                  <td className={`${cell} text-right text-gray-300`}>{p.laps_completed ?? ''}</td>
                </>
              ))}
            </tbody>
          </TableWrap>
        </TabPanel>
      )}

      {tab === 'sectors' && (
        <TabPanel id="sectors" idPrefix="board">
          <TableWrap>
            <thead>
              <tr className="border-b border-gray-800">
                <Th>Position</Th>
                <Th align="right">S1</Th><Th align="right">S2</Th><Th align="right">S3</Th>
                <Th align="center">Best lap</Th><Th align="right">Last lap</Th>
              </tr>
            </thead>
            <tbody>
              {rows(6, (p) => (
                <>
                  <td className={cell}><Driver p={p} /></td>
                  {[0, 1, 2].map((s) => {
                    const sector = p.sectors?.[s];
                    return (
                      <td key={s} className={`${cell} text-right font-medium ${SECTOR_TEXT[sector?.status ?? 'none']}`}>
                        {sector?.time ?? '—'}
                        <span className="sr-only"> {SECTOR_WORD[sector?.status ?? 'none']}</span>
                      </td>
                    );
                  })}
                  <td className={`${cell} text-center`}><BestLap p={p} /></td>
                  <td className={`${cell} text-right text-gray-300`}>{p.last_lap_time ?? '—'}</td>
                </>
              ))}
            </tbody>
          </TableWrap>
        </TabPanel>
      )}

      {tab === 'tyres' && (
        <TabPanel id="tyres" idPrefix="board">
          <TableWrap>
            <thead>
              <tr className="border-b border-gray-800">
                <Th>Position</Th><Th align="center">Current</Th><Th>Stints</Th><Th align="right">Laps</Th>
              </tr>
            </thead>
            <tbody>
              {rows(4, (p) => (
                <>
                  <td className={cell}><Driver p={p} /></td>
                  <td className={`${cell} text-center`}><TyreBadge compound={p.tyre} age={p.tyre_age} /></td>
                  <td className={cell}>
                    <span className="flex flex-wrap items-center gap-3">
                      {(p.stints ?? []).length === 0 && <span className="text-gray-600">—</span>}
                      {(p.stints ?? []).map((s, i) => <TyreBadge key={i} compound={s.compound} laps={s.laps} />)}
                    </span>
                  </td>
                  <td className={`${cell} text-right text-gray-300`}>{p.laps_completed ?? ''}</td>
                </>
              ))}
            </tbody>
          </TableWrap>
        </TabPanel>
      )}
    </Card>
  );
};

export default LiveTimingBoard;
