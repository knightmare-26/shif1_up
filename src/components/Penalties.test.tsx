import React from 'react';
import { act, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import RaceResults from './RaceResults';
import { penaltyBadges, StewardsCard } from './Penalties';
import { backendApi, SessionPenalties, StewardsDecision } from '../services/backendApi';

jest.mock('../services/backendApi', () => ({
  ...jest.requireActual('../services/backendApi'),
  backendApi: { getRaceSchedule: jest.fn(), getRaceResults: jest.fn(), getSessionPenalties: jest.fn() },
}));
jest.mock('./SessionConditions', () => () => null);
const api = backendApi as jest.Mocked<typeof backendApi>;

const decision = (driver: string, kind: StewardsDecision['kind'], extra: Partial<StewardsDecision> = {}): StewardsDecision => ({
  driver, number: 1, kind, seconds: null, places: null, reason: 'Speeding in the pit lane', lap: 10, served: false, message: '', ...extra,
});
const summary = (extra = {}) => ({ time_penalty_seconds: 0, penalties: [], warnings: 0, reprimands: 0, black_and_white: false,
  disqualified: false, deleted_laps: 0, ...extra });

const DATA: SessionPenalties = {
  year: 2026, gp: 'Monaco Grand Prix', session: 'R', stewards: 'ok',
  decisions: [
    decision('HAM', 'time', { seconds: 5, served: true, lap: 34 }),
    decision('GAS', 'time', { seconds: 5, lap: 52 }),
    decision('GAS', 'time', { seconds: 5, lap: 68 }),
    decision('PER', 'drive_through', { reason: 'False start', lap: 9, served: true }),
    decision('LEC', 'disqualified', { reason: 'Plank wear', lap: null }),
    decision('SAI', 'warning', { reason: 'Moving under braking' }),
  ],
  deleted_laps: [{ driver: 'STR', number: 18, time: '1:14.225', lap: 7, reason: 'Track limits at turn 13' }],
  drivers: {
    HAM: summary({ time_penalty_seconds: 5, penalties: ['time'] }),
    GAS: summary({ time_penalty_seconds: 10, penalties: ['time', 'time'] }),
    PER: summary({ penalties: ['drive_through'] }),
    LEC: summary({ penalties: ['disqualified'], disqualified: true }),
    SAI: summary({ warnings: 1 }),
    STR: summary({ deleted_laps: 1 }),
  },
  grid: { HAD: { qualified: 3, started: 8, pit_lane: false }, COL: { qualified: 15, started: null, pit_lane: true } },
};

const labels = (code: string, session = 'R') => penaltyBadges(code, DATA, session).map((b) => b.label);

test('badges: time added after the race, time served in the pits, and the rest', () => {
  expect(labels('GAS')).toEqual(['+10s']);
  expect(labels('HAM')).toEqual(['5s served']);
  expect(labels('PER')).toEqual(['Drive-through']);
  expect(labels('LEC')).toEqual(['DSQ']);
  expect(labels('HAD')).toEqual(['Grid ↓5']);
  expect(labels('COL')).toEqual(['Pit-lane start']);
  expect(labels('SAI')).toEqual([]);                       // a warning is listed, not badged
  expect(labels('STR')).toEqual([]);                       // a deleted lap only matters in qualifying...
  expect(labels('STR', 'Q')).toEqual(['1 lap deleted']);  // ...where it decides the result
  expect(penaltyBadges('GAS', DATA, 'R')[0].title).toMatch(/Lap 52 · 5s time penalty: Speeding in the pit lane/);
});

test("the stewards' card lists every decision with its lap, and who started behind where they qualified", () => {
  render(<StewardsCard data={DATA} sessionLabel="Race" names={{ GAS: 'Pierre Gasly', HAD: 'Isack Hadjar', HAM: 'Lewis Hamilton' }} />);

  const rows = within(screen.getByRole('table')).getAllByRole('row').slice(1).map((r) => r.textContent);
  expect(rows).toHaveLength(6);
  expect(rows[0]).toMatch(/34Lewis Hamilton5s time penaltyservedSpeeding in the pit lane/);
  expect(screen.getByText(/Started behind where they qualified/).parentElement).toHaveTextContent('Isack Hadjar P8 (qualified P3)');
  expect(screen.getByText(/Lap times deleted/)).toHaveTextContent('STR ×1');
});

test('while a session is live the card says why the decisions are missing', () => {
  render(<StewardsCard data={{ ...DATA, stewards: 'locked', decisions: [], deleted_laps: [], drivers: {} }} sessionLabel="Race" names={{}} />);
  expect(screen.getByText(/paused while an F1 session is live/)).toBeInTheDocument();
  expect(screen.getByText(/Started behind where they qualified/)).toBeInTheDocument();   // from the stored results
});

test('the results page shows the badges next to the drivers and the card under the results', async () => {
  api.getRaceSchedule.mockResolvedValue([{ round: 8, race_name: 'Monaco Grand Prix', circuit_name: 'Monaco', date: '2026-06-07' } as any]);
  api.getRaceResults.mockResolvedValue([
    { DriverNumber: '10', Abbreviation: 'GAS', DriverId: 'gas', FullName: 'Pierre Gasly', TeamName: 'Alpine', TeamColor: '', TeamId: 'alpine',
      Position: '7', ClassifiedPosition: '7', GridPosition: '7', Time: 0, Status: 'Finished', Points: '6', Laps: '78',
      BroadcastName: '', FirstName: '', LastName: '', HeadshotUrl: '', CountryCode: 'FRA' },
  ]);
  api.getSessionPenalties.mockResolvedValue(DATA);
  await act(async () => {
    render(<MemoryRouter><RaceResults year={2026} initialGp="Monaco" /></MemoryRouter>);
  });

  expect(api.getSessionPenalties).toHaveBeenCalledWith(2026, 'Monaco Grand Prix', 'R');
  expect(screen.getByText('+10s')).toBeInTheDocument();
  expect(screen.getByText("Stewards' decisions")).toBeInTheDocument();
});
