import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import SessionConditions from './SessionConditions';
import { backendApi, SessionDataError, SessionWeather } from '../services/backendApi';

jest.mock('../services/backendApi', () => {
  const actual = jest.requireActual('../services/backendApi');
  return { ...actual, backendApi: { getSessionConditions: jest.fn(), getReplayFrame: jest.fn() } };
});
const api = backendApi as jest.Mocked<typeof backendApi>;

const reading = { date: 't', air_temperature: 25.3, track_temperature: 42.7, humidity: 67.4, wind_speed_kmh: 0.8,
  wind_direction: 180, pressure: 1010, rain: false };
const INFO: SessionWeather = {
  year: 2026, gp: 'Spanish Grand Prix', session: 'R', session_name: 'Race', meeting_name: 'Spanish Grand Prix',
  start: 's', end: 'e', duration_seconds: 7800,
  weather: { at_start: reading, rain_during: true, air_range: [23, 25.3], track_range: [38, 42.7], readings: 120 },
};

async function renderCard(year = 2026) {
  await act(async () => {
    render(<SessionConditions year={year} raceName="Spanish Grand Prix" session="R" sessionLabel="Race" />);
  });
}

afterEach(() => jest.clearAllMocks());

test('shows the weather at the start and how the session went', async () => {
  api.getSessionConditions.mockResolvedValue(INFO);
  await renderCard();

  expect(api.getSessionConditions).toHaveBeenCalledWith(2026, 'Spanish Grand Prix', 'R');
  for (const text of ['25.3°C', '42.7°C', '67.4%', '0.8 km/h', 'No']) expect(screen.getByText(text)).toBeInTheDocument();
  expect(screen.getByText(/During it: air 23–25°C, track 38–43°C, rain fell/)).toBeInTheDocument();
});

test('says plainly when the data provider is locked during a live session', async () => {
  api.getSessionConditions.mockRejectedValue(new SessionDataError('locked', 'Paused while an F1 session is live'));
  await renderCard();

  expect(screen.getByText(/Paused while an F1 session is live/)).toBeInTheDocument();
});

test('seasons before 2023 say where the data starts, without asking the server', async () => {
  await renderCard(2021);

  expect(screen.getByText('Weather and replays are available from 2023.')).toBeInTheDocument();
  expect(api.getSessionConditions).not.toHaveBeenCalled();
});

test('watching the replay loads the board and its weather from the start', async () => {
  api.getSessionConditions.mockResolvedValue(INFO);
  api.getReplayFrame.mockResolvedValue({
    seconds: 0,
    state: {
      session: 'R', session_type: 'classified', replay: true, lap: 3, track_status: 'green', session_status: 'live',
      weather: { ...reading, rain: true },
      positions: [{ driver_id: 'ANT', driver_name: 'ANT', team: 'Mercedes', position: 1, gap: null, status: 'Running',
        sectors: [], stints: [], laps_completed: 3 } as any],
    },
  });
  await renderCard();

  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /watch replay/i })); });

  expect(api.getReplayFrame).toHaveBeenCalledWith(2026, 'Spanish Grand Prix', 'R', 0);
  expect(screen.getByText('Yes')).toBeInTheDocument();                 // it's raining in this frame
  expect(screen.getByText('ANT')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument();
});
