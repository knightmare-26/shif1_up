import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { ServiceStatusBanner, useServiceStatus } from './ServiceStatusBanner';
import { probeService, ServiceStatus } from '../services/serviceStatus';

jest.mock('../services/serviceStatus', () => {
  const actual = jest.requireActual('../services/serviceStatus');
  return { ...actual, probeService: jest.fn() };
});
const probe = probeService as jest.MockedFunction<typeof probeService>;

const SERVER_WAKING: ServiceStatus = { state: 'server-waking', message: 'Waking up the server', detail: '', serverUp: false };
const DB_PAUSED: ServiceStatus = { state: 'database-waking', message: 'Waking up the database', detail: '', serverUp: true };
const READY: ServiceStatus = { state: 'ready', message: '', detail: '', serverUp: true };

const Harness: React.FC = () => {
  const { status, slow, gated } = useServiceStatus();
  return (
    <>
      {gated ? <p>wait screen</p> : <p>pages</p>}
      {!gated && <ServiceStatusBanner status={status} slow={slow} />}
    </>
  );
};

beforeEach(() => jest.useFakeTimers());
afterEach(() => { jest.useRealTimers(); jest.clearAllMocks(); });

const flush = () => act(async () => { await Promise.resolve(); });

test('a sleeping server shows the pages at once, and a banner only if it takes a while', async () => {
  probe.mockResolvedValue(SERVER_WAKING);
  render(<Harness />);
  await flush();

  expect(screen.getByText('pages')).toBeInTheDocument();
  expect(screen.queryByRole('status')).not.toBeInTheDocument();

  await act(async () => { jest.advanceTimersByTime(8000); });
  expect(screen.getByRole('status')).toHaveTextContent('Waking up the server');
  expect(screen.queryByText('wait screen')).not.toBeInTheDocument();
});

test('a paused database gets the wait screen until it is back', async () => {
  probe.mockResolvedValue(DB_PAUSED);
  render(<Harness />);
  await flush();
  expect(screen.getByText('wait screen')).toBeInTheDocument();

  probe.mockResolvedValue(READY);
  await act(async () => { jest.advanceTimersByTime(4000); });
  await flush();
  expect(screen.getByText('pages')).toBeInTheDocument();
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

test('a quick answer shows nothing extra', async () => {
  probe.mockResolvedValue(READY);
  render(<Harness />);
  await flush();
  await act(async () => { jest.advanceTimersByTime(10000); });

  expect(screen.getByText('pages')).toBeInTheDocument();
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});
