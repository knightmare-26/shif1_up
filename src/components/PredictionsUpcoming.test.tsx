import React from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Predictions from './Predictions';
import { backendApi } from '../services/backendApi';

jest.mock('../services/backendApi', () => ({
  backendApi: {
    getPredictionStatus: jest.fn(),
    getPredictionCircuits: jest.fn(),
    getPredictionBacktest: jest.fn(),
    predictQualifying: jest.fn(),
    predictRace: jest.fn(),
    predictSprint: jest.fn(),
  },
}));
const api = backendApi as jest.Mocked<typeof backendApi>;

const result = (driver: string) => ({
  success: true, circuit: 'Marina Bay', grid_data_available: true, field_source: 'the last race’s line-up',
  predictions: [{ predicted_rank: 1, driver_id: driver, driver_name: driver, constructor_id: 't', constructor_name: 'Team',
    predicted_position: 1, predicted_grid: 1 }],
});

function weekend(sprint: boolean, completed: string[] = []) {
  api.getPredictionStatus.mockResolvedValue({ trained: true, race_model_ready: true, quali_model_ready: true,
    sprint_model_ready: true, grid_data_available: true });
  api.getPredictionCircuits.mockResolvedValue([{ round: 17, race_name: 'Singapore Grand Prix', circuit_name: 'Marina Bay',
    date: '2026-10-11', is_sprint: sprint, completed_sessions: completed }]);
  api.getPredictionBacktest.mockResolvedValue({ races: [] });
  api.predictQualifying.mockResolvedValue(result('Quali Driver'));
  api.predictRace.mockResolvedValue(result('Race Driver'));
  api.predictSprint.mockResolvedValue(result('Sprint Driver'));
}

async function open(url = '/predictions') {
  await act(async () => {
    render(<MemoryRouter initialEntries={[url]}><Predictions /></MemoryRouter>);
  });
}

const sessionSelect = () => screen.getByText('Session').parentElement!.querySelector('select') as HTMLSelectElement;

afterEach(() => jest.clearAllMocks());

test('one session at a time — the race by default, the others from the dropdown in weekend order', async () => {
  weekend(true);
  await open();

  expect(screen.getByText('Race Prediction')).toBeInTheDocument();
  expect(screen.queryByText('Qualifying Prediction')).not.toBeInTheDocument();
  expect(screen.queryByText('Sprint Prediction')).not.toBeInTheDocument();
  expect(Array.from(sessionSelect().options, (o) => o.text)).toEqual(['Sprint Qualifying', 'Sprint', 'Qualifying', 'Race']);

  await act(async () => { fireEvent.change(sessionSelect(), { target: { value: 'qualifying' } }); });
  expect(screen.getByText('Qualifying Prediction')).toBeInTheDocument();
  expect(screen.queryByText('Race Prediction')).not.toBeInTheDocument();
  expect(within(screen.getByRole('table')).getByText('Quali Driver')).toBeInTheDocument();
});

test('the session in the link is the one shown', async () => {
  weekend(true);
  await open('/predictions?session=sprint');
  expect(screen.getByText('Sprint Prediction')).toBeInTheDocument();
  expect(sessionSelect().value).toBe('sprint');
});

test('a weekend without a sprint has no sprint option, and a sprint link falls back to the race', async () => {
  weekend(false);
  await open('/predictions?session=sprint');

  expect(Array.from(sessionSelect().options, (o) => o.text)).toEqual(['Qualifying', 'Race']);
  expect(screen.getByText('Race Prediction')).toBeInTheDocument();
  expect(api.predictSprint).not.toHaveBeenCalled();
});

test('a finished session leaves the dropdown and points to Predicted vs Actual', async () => {
  weekend(true, ['sprint_qualifying', 'sprint', 'qualifying']);
  await open('/predictions?session=qualifying');

  expect(Array.from(sessionSelect().options, (o) => o.text)).toEqual(['Race']);
  expect(screen.getByText('Race Prediction')).toBeInTheDocument();       // the link's session is done: the race
  expect(api.predictQualifying).not.toHaveBeenCalled();
  expect(api.predictSprint).not.toHaveBeenCalled();
  expect(screen.getByText(/Sprint Qualifying, Sprint and Qualifying are done/)).toBeInTheDocument();

  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Predicted vs Actual' })); });
  expect(api.getPredictionBacktest).toHaveBeenCalled();
});

const withOdds = (driver: string, oddsAvailable = true) => ({
  ...result(driver), odds_available: oddsAvailable,
  predictions: [{ ...result(driver).predictions[0], ...(oddsAvailable ? { win_probability: 0.42, podium_probability: 0.81 } : {}) }],
});

test("sprint qualifying is the qualifying model's prediction, under its own name", async () => {
  weekend(true);
  await open('/predictions?session=sprint_qualifying');

  expect(screen.getByText('Sprint Qualifying Prediction')).toBeInTheDocument();
  expect(within(screen.getByRole('table')).getByText('Quali Driver')).toBeInTheDocument();
  expect(screen.getByText(/the qualifying model, so the same order as qualifying/)).toBeInTheDocument();
  expect(api.predictQualifying).toHaveBeenCalledTimes(1);           // one prediction serves both
});

test('the chances have a column each: pole and top 3 in qualifying, win and podium in the race', async () => {
  weekend(false);
  api.predictQualifying.mockResolvedValue(withOdds('Quali Driver'));
  api.predictRace.mockResolvedValue(withOdds('Race Driver'));
  await open();

  for (const header of ['Win chance', 'Podium chance']) expect(screen.getByText(header)).toBeInTheDocument();
  expect(screen.getByText('42%')).toBeInTheDocument();
  expect(screen.getByText('81%')).toBeInTheDocument();

  await act(async () => { fireEvent.change(sessionSelect(), { target: { value: 'qualifying' } }); });
  for (const header of ['Pole chance', 'Top 3 chance']) expect(screen.getByText(header)).toBeInTheDocument();
});

test('chances still being worked out arrive by themselves', async () => {
  jest.useFakeTimers();
  try {
    weekend(false);
    api.predictRace.mockResolvedValueOnce(withOdds('Race Driver', false)).mockResolvedValue(withOdds('Race Driver'));
    await open();

    expect(screen.getByText(/The chances are still being worked out/)).toBeInTheDocument();
    expect(screen.queryByText('Win chance')).not.toBeInTheDocument();

    await act(async () => { jest.advanceTimersByTime(20000); });
    expect(screen.getByText('Win chance')).toBeInTheDocument();
    expect(screen.queryByText(/The chances are still being worked out/)).not.toBeInTheDocument();
    expect(screen.getByText('Race Prediction')).toBeInTheDocument();          // never cleared while it re-checked
  } finally {
    jest.useRealTimers();
  }
});
