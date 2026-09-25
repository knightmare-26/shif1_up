import React from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ConstructorAnalytics from './ConstructorAnalytics';
import { backendApi, ConstructorStanding } from '../services/backendApi';

jest.mock('../services/backendApi', () => ({
  backendApi: { getConstructorStats: jest.fn() },
}));
const api = backendApi as jest.Mocked<typeof backendApi>;

const TEAMS: ConstructorStanding[] = [
  { position: 1, constructor_id: 'mercedes', constructor_name: 'Mercedes', points: 503, wins: 10 } as ConstructorStanding,
  { position: 2, constructor_id: 'cadillac', constructor_name: 'Cadillac F1 Team', points: 0, wins: 0 } as ConstructorStanding,
];

async function renderAt(url: string) {
  await act(async () => {
    render(
      <MemoryRouter initialEntries={[url]}>
        <ConstructorAnalytics year={2026} teams={TEAMS} loading={false} error={null} onRetry={() => undefined} />
      </MemoryRouter>,
    );
  });
}

const headers = () => within(screen.getByRole('table')).getAllByRole('columnheader').map((h) => h.textContent);

beforeEach(() => {
  api.getConstructorStats.mockResolvedValue({
    year: 2026, races_counted: 14, sprints_counted: 5,
    constructors: [{ constructor_id: 'mercedes', constructor_name: 'Mercedes', race_wins: 10, race_podiums: 19, sprint_wins: 4, sprint_podiums: 5 }],
  });
});
afterEach(() => jest.clearAllMocks());

test('starts with constructor and points only', async () => {
  await renderAt('/dashboard?tab=teams');

  expect(headers()).toEqual(['Pos', 'Constructor', 'Points']);
  expect(api.getConstructorStats).not.toHaveBeenCalled();
});

test('the same Columns menu adds team wins and podiums, matched by team id', async () => {
  await renderAt('/dashboard?tab=teams');
  fireEvent.click(screen.getByRole('button', { name: /columns/i }));
  await act(async () => { fireEvent.click(screen.getByLabelText('Race podiums')); });
  await act(async () => { fireEvent.click(screen.getByLabelText('Race wins')); });

  expect(headers()).toEqual(['Pos', 'Constructor', 'Wins', 'Podiums', 'Points']);
  const rows = screen.getAllByRole('row').slice(1).map((r) => within(r).getAllByRole('cell').map((c) => c.textContent));
  expect(rows[0].slice(2, 4)).toEqual(['10', '19']);
  expect(rows[1].slice(2, 4)).toEqual(['—', '—']);           // no stored results for that team
  expect(screen.getByText(/a one-two is two/)).toBeInTheDocument();
});

test('columns chosen on the Drivers tab carry over from the URL', async () => {
  await renderAt('/dashboard?tab=teams&cols=sprint_wins');

  expect(headers()).toEqual(['Pos', 'Constructor', 'Sprint wins', 'Points']);
  expect(screen.queryByText(/a one-two is two/)).not.toBeInTheDocument();
});
