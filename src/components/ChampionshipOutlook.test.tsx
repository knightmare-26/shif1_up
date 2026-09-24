import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ChampionshipOutlook from './ChampionshipOutlook';
import { formatChance } from '../utils/probability';
import { backendApi, ChampionshipOutlook as Outlook, ChampionshipRow } from '../services/backendApi';

jest.mock('../services/backendApi', () => ({
  backendApi: { getChampionshipOutlook: jest.fn(), getChampionshipBacktest: jest.fn() },
}));
const api = backendApi as jest.Mocked<typeof backendApi>;

const row = (position: number, name: string, extra: Partial<ChampionshipRow> = {}): ChampionshipRow => ({
  id: name.toLowerCase(), code: null, name, team: 'Mercedes', position, points: 300 - position * 50, wins: 0,
  alive: true, projected_points: 400 - position * 50, points_p10: 350 - position * 50, points_p90: 450 - position * 50,
  projected_position: position, title_probability: position === 1 ? 0.86 : 0.07,
  position_probabilities: [0.5, 0.3, 0.2], ...extra,
});

const outlook = (extra: Partial<Outlook> = {}): Outlook => ({
  year: 2026, status: 'in_progress', rounds_completed: 14, rounds_total: 23,
  remaining: Array.from({ length: 9 }, (_, i) => ({ round: 15 + i, name: `GP${i}`, sprint: false })),
  sprint_calendar_known: true, clinched: false, champion: null, max_points_remaining: 233,
  next_race_clinch: null,
  standings: [
    row(1, 'Antonelli'), row(2, 'Russell'),
    row(3, 'Hadjar', { racing: false, title_probability: 0 }),        // injured: still mathematically alive
    row(4, 'Stroll', { alive: false, title_probability: 0 }),
  ],
  method: { simulations: 10000, beta: 0.18, calibration_races: 84, model_trained_at: null },
  computed_at: 't', ...extra,
});

async function renderAt(url = '/dashboard?tab=title') {
  await act(async () => {
    render(<MemoryRouter initialEntries={[url]}><ChampionshipOutlook year={2026} /></MemoryRouter>);
  });
}

beforeEach(() => {
  api.getChampionshipOutlook.mockResolvedValue(outlook());
  api.getChampionshipBacktest.mockResolvedValue({
    seasons: [{ year: 2023, champion: 'ver', constructors_champion: 'red_bull', rounds: 22 }],
    drivers: { checkpoints: 22, champion_accuracy: 0.8, leader_accuracy: 0.74, mean_p_actual_champion: 0.62, brier: 0.3, log_score: -0.6, final_order_mae: 2 },
    constructors: {}, computed_at: 't',
  });
});
afterEach(() => jest.clearAllMocks());

test('chances are rounded to what a simulation can honestly claim', () => {
  expect([0, 0.004, 0.38, 0.996, 1].map(formatChance)).toEqual(['0%', '<1%', '38%', '>99%', '100%']);
});

test('shows the title race, who is out of contention and the track record', async () => {
  await renderAt();

  expect(api.getChampionshipOutlook).toHaveBeenCalledWith('drivers', 2026);
  expect(screen.getByText(/Antonelli leads after 14 rounds/)).toBeInTheDocument();
  expect(screen.getByText(/up to 233 points/)).toBeInTheDocument();
  expect(screen.getByText('86%')).toBeInTheDocument();
  expect(screen.getAllByText('Out of contention')).toHaveLength(1);
  expect(screen.getAllByText('Missed last race')).toHaveLength(1);   // not the same thing as eliminated
  expect(screen.getByText(/named the eventual champion 80% of the time/)).toBeInTheDocument();
});

test('the next-race clinch scenario is spelled out', async () => {
  api.getChampionshipOutlook.mockResolvedValue(outlook({
    next_race_clinch: { round: 15, race_name: 'Azerbaijan', rival: 'rus', rival_name: 'Russell', margin_needed: 7 },
  }));
  await renderAt();

  expect(screen.getByText(/can clinch it at the Azerbaijan by outscoring Russell by 7 or more points/)).toBeInTheDocument();
});

test('a clinched title is announced with the rounds to spare', async () => {
  api.getChampionshipOutlook.mockResolvedValue(outlook({
    clinched: true, champion: 'Antonelli',
    remaining: [{ round: 22, name: 'Qatar', sprint: false }, { round: 23, name: 'Abu Dhabi', sprint: false }],
  }));
  await renderAt();

  expect(screen.getByText(/clinched with 2 rounds to go/)).toBeInTheDocument();
  expect(screen.getByText('Champion')).toBeInTheDocument();
});

test('switching to constructors loads that view and keeps it in the URL', async () => {
  await renderAt();
  api.getChampionshipOutlook.mockResolvedValue(outlook({ standings: [row(1, 'Mercedes')] }));

  await act(async () => { fireEvent.click(screen.getByRole('tab', { name: /constructors/i })); });

  expect(api.getChampionshipOutlook).toHaveBeenLastCalledWith('constructors', 2026);
  expect(screen.getByText("Constructors' Championship — 2026")).toBeInTheDocument();
});
