import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import LiveAnalytics from './LiveAnalytics';
import { backendApi, LiveFeedStatus } from '../services/backendApi';

jest.mock('../services/backendApi', () => ({
  backendApi: {
    getLiveStatus: jest.fn(),
    getRaceSchedule: jest.fn(),
    getLiveSessions: jest.fn(),
    getLiveRaceState: jest.fn(),
    getDriverStandings: jest.fn(),
  },
}));
const api = backendApi as jest.Mocked<typeof backendApi>;

const status = (extra: Partial<LiveFeedStatus>): LiveFeedStatus => ({
  live_available: false, enabled: false, source: 'openf1', relays: [], ...extra,
});

async function renderLive() {
  await act(async () => {
    render(<MemoryRouter initialEntries={['/live']}><LiveAnalytics /></MemoryRouter>);
  });
}

beforeEach(() => {
  api.getRaceSchedule.mockResolvedValue([]);
  api.getLiveSessions.mockResolvedValue({ race_id: 'x', sessions: [] });
  api.getDriverStandings.mockResolvedValue([]);
});
afterEach(() => jest.clearAllMocks());

test('with no live feed and nothing running, the page says live timing is coming', async () => {
  api.getLiveStatus.mockResolvedValue(status({}));
  await renderLive();

  expect(screen.getByRole('heading', { name: 'Coming soon' })).toBeInTheDocument();
});

test('a running replay turns the page on and links to it', async () => {
  api.getLiveStatus.mockResolvedValue(status({
    enabled: true,
    relays: [{ race_id: '2026_Spanish_Grand_Prix', year: 2026, gp: 'Spanish Grand Prix', session: 'R', replay: true,
      replay_speed: 60, status: 'running', detail: null, clock: null, started_at: 't' }],
  }));
  await renderLive();

  expect(screen.queryByRole('heading', { name: 'Coming soon' })).not.toBeInTheDocument();
  const link = screen.getByRole('link', { name: /2026 Spanish Grand Prix — Race/ });
  expect(link).toHaveAttribute('href', '/live-monitor?year=2026&gp=Spanish_Grand_Prix&session=R');
  expect(screen.getByText('Replay')).toBeInTheDocument();
});

test('if the status check fails, the page stays off rather than showing an empty board', async () => {
  api.getLiveStatus.mockRejectedValue(new Error('down'));
  await renderLive();

  expect(screen.getByRole('heading', { name: 'Coming soon' })).toBeInTheDocument();
});
