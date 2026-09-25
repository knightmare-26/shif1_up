import React from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import DriverAnalytics, { statsMatcher } from './DriverAnalytics';
import { backendApi, DriverStanding, DriverStatsResponse } from '../services/backendApi';

jest.mock('../services/backendApi', () => ({
  backendApi: { getDriverStandings: jest.fn(), getDriverStats: jest.fn() },
}));
const api = backendApi as jest.Mocked<typeof backendApi>;

// (Omit: every object literal has a `constructor`, which clashes with DriverStanding's string field.)
const standing = (position: number, driver_name: string, extra: Omit<Partial<DriverStanding>, 'constructor'> = {}): DriverStanding => ({
  position, driver_id: driver_name.toLowerCase().replace(/ /g, '_'), driver_name,
  constructor: 'Team', points: 100 - position, wins: 0, nationality: 'X', ...extra,
});

const STANDINGS = [
  standing(1, 'Andrea Kimi Antonelli', { code: 'ANT' }),
  standing(2, 'Nico Hülkenberg'),          // snapshot row: no code, accented name
];
const STATS: DriverStatsResponse = {
  year: 2026, races_counted: 14, sprints_counted: 5,
  drivers: [
    { code: 'ANT', driver_name: 'Kimi Antonelli', race_wins: 8, race_podiums: 12, sprint_wins: 1, sprint_podiums: 2 },
    { code: 'HUL', driver_name: 'Nico Hulkenberg', race_wins: 0, race_podiums: 1, sprint_wins: 0, sprint_podiums: 0 },
  ],
};

let location = '';
const LocationProbe = () => { location = useLocation().search; return null; };

async function renderAt(url = '/dashboard?tab=drivers') {
  await act(async () => {
    render(
      <MemoryRouter initialEntries={[url]}>
        <DriverAnalytics year={2026} />
        <LocationProbe />
      </MemoryRouter>,
    );
  });
}

const headers = () => within(screen.getByRole('table')).getAllByRole('columnheader').map((h) => h.textContent);

beforeEach(() => {
  api.getDriverStandings.mockResolvedValue(STANDINGS);
  api.getDriverStats.mockResolvedValue(STATS);
});
afterEach(() => jest.clearAllMocks());

test('starts with only position, driver, team and points, and fetches no stats', async () => {
  await renderAt();

  expect(headers()).toEqual(['Pos', 'Driver', 'Team', 'Points']);
  expect(api.getDriverStats).not.toHaveBeenCalled();
});

test('each checkbox adds its column, in a fixed order, and the choice goes into the URL', async () => {
  await renderAt();
  fireEvent.click(screen.getByRole('button', { name: /columns/i }));

  await act(async () => { fireEvent.click(screen.getByLabelText('Sprint podiums')); });
  await act(async () => { fireEvent.click(screen.getByLabelText('Race wins')); });

  expect(headers()).toEqual(['Pos', 'Driver', 'Team', 'Wins', 'Sprint podiums', 'Points']);
  expect(location).toContain('cols=race_wins%2Csprint_podiums');
  expect(screen.getByText(/counted from 14 races and 5 sprints/i)).toBeInTheDocument();

  const rows = screen.getAllByRole('row').slice(1).map((r) => within(r).getAllByRole('cell').map((c) => c.textContent));
  expect(rows[0].slice(3)).toEqual(['8', '2', '99']);   // matched by code
  expect(rows[1].slice(3)).toEqual(['0', '0', '98']);   // matched by accent-free name

  await act(async () => { fireEvent.click(screen.getByLabelText('Race wins')); });
  expect(headers()).toEqual(['Pos', 'Driver', 'Team', 'Sprint podiums', 'Points']);
});

test('columns picked earlier come back from the URL after a refresh', async () => {
  await renderAt('/dashboard?tab=drivers&cols=race_podiums,bogus');

  expect(headers()).toEqual(['Pos', 'Driver', 'Team', 'Podiums', 'Points']);
  expect(api.getDriverStats).toHaveBeenCalledWith(2026);
});

test('a season with no stored results says so instead of showing zeros', async () => {
  api.getDriverStats.mockResolvedValue({ year: 2026, races_counted: 0, sprints_counted: 0, drivers: [] });
  await renderAt('/dashboard?tab=drivers&cols=race_wins');

  expect(screen.getByText(/not available for 2026/i)).toBeInTheDocument();
  expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2);
});

test('Escape closes the menu', async () => {
  await renderAt();
  fireEvent.click(screen.getByRole('button', { name: /columns/i }));
  expect(screen.getByRole('group', { name: 'Columns' })).toBeInTheDocument();

  fireEvent.keyDown(document, { key: 'Escape' });
  expect(screen.queryByRole('group', { name: 'Columns' })).not.toBeInTheDocument();
});

test('an ambiguous surname is not guessed', () => {
  const find = statsMatcher([
    { code: 'AAA', driver_name: 'Ann Smith', race_wins: 1, race_podiums: 1, sprint_wins: 0, sprint_podiums: 0 },
    { code: 'BBB', driver_name: 'Bob Smith', race_wins: 2, race_podiums: 2, sprint_wins: 0, sprint_podiums: 0 },
  ]);

  expect(find(standing(1, 'Carl Smith'))).toBeUndefined();
  expect(find(standing(1, 'Bob Smith'))?.code).toBe('BBB');
});
