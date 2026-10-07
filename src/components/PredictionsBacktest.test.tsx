import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Predictions from './Predictions';
import { backendApi, BacktestResult, ProbabilityScore } from '../services/backendApi';

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

const RESULT: BacktestResult = {
  method: { latest_season: 2026 },
  probability_scores: {
    races_scored: 75,
    race: { win: score(0.18, -0.24) },
    qualifying: { pole: score(0.09) },
  },
  races: [{
    year: 2026, round: 16, race_id: '2026_Bahrain', race_name: 'Bahrain', circuit_name: 'Kuala Lumpur',
    quali_mae: 3.5, race_mae: 3.3, practice_data: true,
    drivers: [{
      driver_id: 'ver', driver_name: 'Max Verstappen', predicted_grid: 2, actual_grid: 1, predicted_position: 1,
      actual_position: 1, pole_probability: 0.12, win_probability: 0.18, podium_probability: 0.49,
    }],
  }],
};

beforeEach(() => {
  api.getPredictionStatus.mockResolvedValue({} as any);
  api.getPredictionCircuits.mockResolvedValue([]);
  api.getPredictionBacktest.mockResolvedValue(RESULT);
});

test("each driver's chances and how good the chances were", async () => {
  await act(async () => {
    render(<MemoryRouter initialEntries={['/predictions?tab=backtest']}><Predictions /></MemoryRouter>);
  });

  for (const text of ['12%', '18%', '49%']) expect(screen.getByText(text)).toBeInTheDocument();
  expect(screen.getByText('How good the chances were')).toBeInTheDocument();
  expect(screen.getByText('18% better')).toBeInTheDocument();
  expect(screen.getByText('24% worse')).toBeInTheDocument();
  expect(screen.getByText(/given 19% to win on average won 56% of the time/)).toBeInTheDocument();
  expect(screen.getByText(/In 2026 each race is predicted by a model trained on everything up to the race before/))
    .toBeInTheDocument();
});
