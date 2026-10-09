import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Predictions from './Predictions';
import { backendApi, BacktestRace, BacktestResult, ProbabilityScore } from '../services/backendApi';

jest.mock('../services/backendApi', () => ({
  backendApi: {
    getPredictionStatus: jest.fn(),
    getPredictionCircuits: jest.fn(),
    getPredictionBacktest: jest.fn(),
  },
}));
const api = backendApi as jest.Mocked<typeof backendApi>;

const score = (skillUniform: number, skillSlot?: number): ProbabilityScore => ({
  top: 1, n: 100, brier: 0.04, log_loss: 0.14, observed_rate: 0.05,
  uniform: { brier: 0.05, log_loss: 0.2 }, skill_vs_uniform: skillUniform,
  ...(skillSlot != null ? { starting_slot: { brier: 0.03, log_loss: 0.1 }, skill_vs_starting_slot: skillSlot } : {}),
  reliability: [{ from: 0.15, to: 0.3, n: 45, predicted: 0.19, observed: 0.56 }],
});

const rate = (top1: number, mae: number) => ({ top1, top3: 0.62, top5: 0.7, top10: 0.78, mae, rmse: 4.8 });

const BAHRAIN: BacktestRace = {
  year: 2026, round: 16, race_id: '2026_Bahrain', race_name: 'Bahrain', circuit_name: 'Kuala Lumpur',
  quali_mae: 3.5, race_mae: 3.3, practice_data: true,
  drivers: [{
    driver_id: 'ver', driver_name: 'Max Verstappen', predicted_grid: 2, actual_grid: 1, predicted_position: 1,
    actual_position: 1, pole_probability: 0.12, win_probability: 0.18, podium_probability: 0.49,
  }],
};

const RESULT: BacktestResult = {
  method: { latest_season: 2026 },
  hit_rates: {
    race: { races: 86, model: rate(0.58, 3.44), grid: rate(0.58, 3.34), standings: rate(0.44, 3.85) },
    qualifying: { races: 86, model: rate(0.35, 3.77), standings: rate(0.31, 3.59) },
  },
  probability_scores: {
    races_scored: 75,
    race: { win: score(0.18, -0.24) },
    qualifying: { pole: score(0.09) },
  },
  races: [BAHRAIN],
};

/** A sprint weekend whose race is still to run: sprint qualifying, the sprint and qualifying are done. */
const SINGAPORE: BacktestRace = {
  year: 2026, round: 17, race_id: '2026_Singapore', race_name: 'Singapore Grand Prix', circuit_name: 'Marina Bay',
  quali_mae: 2.0, race_mae: null, sprint_mae: 1.5, sq_mae: 0.5, in_progress: true,
  sessions_done: ['sprint_qualifying', 'sprint', 'qualifying'],
  drivers: [{
    driver_id: 'nor', driver_name: 'Lando Norris', predicted_sq: 1, actual_sq: 1, sq_pole_probability: 0.31,
    sprint_grid: 1, predicted_sprint: 2, actual_sprint: 1, sprint_win_probability: 0.27, sprint_podium_probability: 0.66,
    predicted_grid: 3, actual_quali: 1,
  }],
};

async function open(result: BacktestResult, url = '/predictions?tab=backtest') {
  api.getPredictionBacktest.mockResolvedValue(result);
  await act(async () => {
    render(<MemoryRouter initialEntries={[url]}><Predictions /></MemoryRouter>);
  });
}

const sessionSelect = () => screen.getByText('Session').parentElement!.querySelector('select') as HTMLSelectElement;
const options = () => Array.from(sessionSelect().options, (o) => o.text);
const pick = async (value: string) => {
  await act(async () => { fireEvent.change(sessionSelect(), { target: { value } }); });
};

beforeEach(() => {
  api.getPredictionStatus.mockResolvedValue({} as any);
  api.getPredictionCircuits.mockResolvedValue([]);
});

test("one session at a time: the race's chances and scores, then qualifying's", async () => {
  await open(RESULT);

  expect(options()).toEqual(['Qualifying', 'Race']);
  expect(screen.getByText('Round 16 — Bahrain: Race')).toBeInTheDocument();
  for (const text of ['18%', '49%']) expect(screen.getByText(text)).toBeInTheDocument();     // win, podium
  expect(screen.queryByText('12%')).not.toBeInTheDocument();                                  // pole: qualifying's
  expect(screen.getByText('How good the chances were')).toBeInTheDocument();
  expect(screen.getByText('18% better')).toBeInTheDocument();
  expect(screen.getByText('24% worse')).toBeInTheDocument();
  expect(screen.getByText(/given 19% to win on average won 56% of the time/)).toBeInTheDocument();
  expect(screen.getByText('Picked the winner')).toBeInTheDocument();
  expect(screen.getByText('3.34')).toHaveClass('font-semibold');          // the grid beat the model here
  expect(screen.getByText(/In 2026 each race is predicted by a model trained on everything up to the race before/))
    .toBeInTheDocument();

  await pick('qualifying');
  expect(screen.getByText('Round 16 — Bahrain: Qualifying')).toBeInTheDocument();
  expect(screen.getByText('12%')).toBeInTheDocument();
  expect(screen.queryByText('18%')).not.toBeInTheDocument();
  expect(screen.getByText('Picked pole')).toBeInTheDocument();
  expect(screen.getByText('9% better')).toBeInTheDocument();                // the pole chances' score
});

test('a weekend whose race is still to run offers the sessions it has, latest first', async () => {
  await open({ ...RESULT, races: [SINGAPORE, BAHRAIN] });

  expect(screen.getByText('Round 17 — Singapore Grand Prix (race to come)')).toBeInTheDocument();
  expect(options()).toEqual(['Sprint Qualifying', 'Sprint', 'Qualifying']);
  expect(screen.getByText('Round 17 — Singapore Grand Prix: Qualifying')).toBeInTheDocument();
  expect(screen.getByText(/race still to run/)).toBeInTheDocument();
  expect(screen.getByText('Off by 2.0')).toBeInTheDocument();

  await pick('sprint');
  expect(screen.getByText('Off by 1.5')).toBeInTheDocument();
  expect(screen.getByText('Grid')).toBeInTheDocument();
  expect(screen.getByText('27%')).toBeInTheDocument();                     // sprint win chance
  expect(screen.getByText(/across 1 races/)).toBeInTheDocument();         // only races that have been run
});

test('sprint qualifying is scored, by the qualifying model', async () => {
  await open({
    ...RESULT, races: [SINGAPORE, BAHRAIN],
    probability_scores: { ...RESULT.probability_scores!, sprint_qualifying: { pole: score(0.11) } },
    hit_rates: { ...RESULT.hit_rates!, sprint_qualifying: { races: 23, model: rate(0.4, 2.8), standings: rate(0.3, 3.4) } },
  }, '/predictions?tab=backtest&session=sprint_qualifying');

  expect(screen.getByText('Round 17 — Singapore Grand Prix: Sprint Qualifying')).toBeInTheDocument();
  expect(screen.getByText('Marina Bay · 2026 · race still to run · predicted by the qualifying model')).toBeInTheDocument();
  expect(screen.getByText('Off by 0.5')).toBeInTheDocument();
  expect(screen.getByText('31%')).toBeInTheDocument();
  expect(screen.getByText('11% better')).toBeInTheDocument();
  expect(screen.getByText('SQ3 (top 10) named')).toBeInTheDocument();
});

test('the race is offered again once the session in the link has no result for the weekend', async () => {
  await open(RESULT, '/predictions?tab=backtest&session=sprint');
  expect(sessionSelect().value).toBe('race');
});
