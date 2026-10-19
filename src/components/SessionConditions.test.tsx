import React from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import SessionConditions from './SessionConditions';
import { backendApi, SessionDataError, SessionWeather } from '../services/backendApi';

jest.mock('../services/backendApi', () => {
  const actual = jest.requireActual('../services/backendApi');
  return { ...actual, backendApi: { getSessionConditions: jest.fn(), getReplayFrame: jest.fn(), getReplayLap: jest.fn() } };
});
const api = backendApi as jest.Mocked<typeof backendApi>;

const reading = { date: 't', air_temperature: 25.3, track_temperature: 42.7, humidity: 67.4, wind_speed_kmh: 0.8,
  wind_direction: 180, pressure: 1010, rain: false };
const INFO: SessionWeather = {
  year: 2026, gp: 'Spanish Grand Prix', session: 'R', session_name: 'Race', meeting_name: 'Spanish Grand Prix',
  start: 's', end: 'e', duration_seconds: 7800,
  weather: { at_start: reading, rain_during: true, air_range: [23, 25.3], track_range: [38, 42.7], readings: 120 },
};

async function renderCard(year = 2026, session = 'R', extra: Partial<React.ComponentProps<typeof SessionConditions>> = {}) {
  let rerender!: (ui: React.ReactElement) => void;
  const ui = (more = {}) => (
    <SessionConditions year={year} raceName="Spanish Grand Prix" session={session} sessionLabel="Race" {...extra} {...more} />
  );
  await act(async () => { ({ rerender } = render(ui())); });
  return (more: Partial<React.ComponentProps<typeof SessionConditions>>) => act(async () => { rerender(ui(more)); });
}

const board = (lap: number) => ({
  session: 'R', session_type: 'classified', replay: true, lap, total_laps: 57, track_status: 'green', session_status: 'live',
  weather: { ...reading, rain: true },
  positions: [{ driver_id: 'ANT', driver_name: 'ANT', team: 'Mercedes', position: 1, gap: null, status: 'Running',
    sectors: [], stints: [], laps_completed: lap } as any],
}) as any;
const lapFrame = (lap: number) => ({ lap, laps: 57, seconds: lap * 90, state: board(lap) });

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

test('the replay and the weather are separate boxes, the weather below', async () => {
  api.getSessionConditions.mockResolvedValue(INFO);
  api.getReplayLap.mockImplementation(async (_y, _g, _s, lap) => lapFrame(lap));
  await renderCard();

  const replay = document.getElementById('session-replay') as HTMLElement;
  const weather = document.getElementById('session-weather') as HTMLElement;
  expect(within(replay).getByText('Replay — Race')).toBeInTheDocument();
  expect(within(weather).getByText('Weather — Race')).toBeInTheDocument();
  expect(replay.compareDocumentPosition(weather) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(within(replay).queryByText(/During it/)).not.toBeInTheDocument();

  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /watch replay/i })); });
  expect(within(replay).getByText('ANT')).toBeInTheDocument();
  expect(within(replay).queryByText('Humidity')).not.toBeInTheDocument();   // no weather strip in the replay
});

test('a race is replayed lap by lap: it starts at the start, steps a lap at a time and plays on', async () => {
  jest.useFakeTimers();
  try {
    api.getSessionConditions.mockResolvedValue(INFO);
    api.getReplayLap.mockImplementation(async (_y, _g, _s, lap) => lapFrame(lap));
    await renderCard();

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /watch replay/i })); });
    expect(api.getReplayLap).toHaveBeenLastCalledWith(2026, 'Spanish Grand Prix', 'R', 0);
    expect(api.getReplayFrame).not.toHaveBeenCalled();
    expect(screen.getByText('Start / 57')).toBeInTheDocument();

    await act(async () => { jest.advanceTimersByTime(1500); });           // the default pace: a lap every 1.5 s
    expect(api.getReplayLap).toHaveBeenLastCalledWith(2026, 'Spanish Grand Prix', 'R', 1);
    expect(screen.getAllByText('Lap 1 / 57')).toHaveLength(2);            // the controls and the board agree

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Next lap' })); });   // pauses
    expect(screen.getAllByText('Lap 2 / 57')).toHaveLength(2);
    expect(screen.getByRole('button', { name: /^play$/i })).toBeInTheDocument();
    await act(async () => { jest.advanceTimersByTime(5000); });
    expect(api.getReplayLap).toHaveBeenLastCalledWith(2026, 'Spanish Grand Prix', 'R', 2);

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Previous lap' })); });
    expect(screen.getAllByText('Lap 1 / 57')).toHaveLength(2);
    await act(async () => { fireEvent.change(screen.getByLabelText('Lap'), { target: { value: '40' } }); });
    expect(api.getReplayLap).toHaveBeenLastCalledWith(2026, 'Spanish Grand Prix', 'R', 40);
  } finally {
    jest.useRealTimers();
  }
});

test('practice and qualifying still play through the session time', async () => {
  api.getSessionConditions.mockResolvedValue(INFO);
  api.getReplayFrame.mockResolvedValue({ seconds: 0, state: { ...board(0), session: 'Q', session_type: 'timed' } });
  await renderCard(2026, 'Q');

  expect(screen.getByText('On the timing board, through the session')).toBeInTheDocument();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /watch replay/i })); });
  expect(api.getReplayFrame).toHaveBeenCalledWith(2026, 'Spanish Grand Prix', 'Q', 0);
  expect(api.getReplayLap).not.toHaveBeenCalled();
  expect(screen.getByLabelText('Session time')).toBeInTheDocument();
});

test("the page is told when there's a replay, and its button opens and starts it", async () => {
  api.getSessionConditions.mockResolvedValue(INFO);
  api.getReplayLap.mockImplementation(async (_y, _g, _s, lap) => lapFrame(lap));
  const onInfo = jest.fn();
  const update = await renderCard(2026, 'R', { onInfo });
  expect(onInfo).toHaveBeenLastCalledWith(INFO);
  expect(api.getReplayLap).not.toHaveBeenCalled();

  await update({ onInfo, replayRequest: 1 });
  expect(api.getReplayLap).toHaveBeenCalledWith(2026, 'Spanish Grand Prix', 'R', 0);
  expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument();
});
