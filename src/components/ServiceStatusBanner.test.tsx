import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { GATE_AFTER_MS, ServiceStatusBanner, useServiceStatus } from './ServiceStatusBanner';
import { ServiceGate } from './ServiceGate';
import { probeService, ServiceStatus } from '../services/serviceStatus';
import { SERVICE_WAKING_EVENT } from '../services/backendApi';

jest.mock('../services/serviceStatus', () => {
  const actual = jest.requireActual('../services/serviceStatus');
  return { ...actual, probeService: jest.fn() };
});
const probe = probeService as jest.MockedFunction<typeof probeService>;

const SERVER_WAKING: ServiceStatus = { state: 'server-waking', message: 'Waking up the server', detail: '', serverUp: false };
const DB_CONNECTING: ServiceStatus = { state: 'server-waking', message: 'Waking up the server', detail: 'connecting', serverUp: true };
const DB_PAUSED: ServiceStatus = { state: 'database-waking', message: 'Waking up the database', detail: '', serverUp: true };
const READY: ServiceStatus = { state: 'ready', message: '', detail: '', serverUp: true };

/** The app shell in miniature: the pages are always there, the wake-up screen over them. */
const Harness: React.FC = () => {
  const { status, slow, gated, elapsed, retry, dismiss } = useServiceStatus();
  return (
    <>
      <p>pages</p>
      {gated && <ServiceGate status={status} elapsed={elapsed} onRetry={retry} onContinue={dismiss} />}
      {!gated && <ServiceStatusBanner status={status} slow={slow} />}
    </>
  );
};

beforeEach(() => jest.useFakeTimers());
afterEach(() => { jest.useRealTimers(); jest.clearAllMocks(); });

const flush = () => act(async () => { await Promise.resolve(); });
const advance = (ms: number) => act(async () => { jest.advanceTimersByTime(ms); });
const screenShown = () => screen.queryByRole('dialog');

test('an awake server loads directly: nothing over the pages', async () => {
  probe.mockResolvedValue(READY);
  render(<Harness />);
  await flush();
  await advance(10_000);

  expect(screen.getByText('pages')).toBeInTheDocument();
  expect(screenShown()).not.toBeInTheDocument();
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

test('a check that answers within the grace period shows nothing either', async () => {
  probe.mockImplementation(() => new Promise((resolve) => setTimeout(() => resolve(READY), GATE_AFTER_MS - 1000)));
  render(<Harness />);
  await advance(GATE_AFTER_MS - 1000);
  await flush();
  await advance(5_000);

  expect(screenShown()).not.toBeInTheDocument();
});

test('a sleeping server gets the wake-up screen after a moment, until it is up', async () => {
  probe.mockImplementation(() => new Promise(() => {}));        // a sleeping host holds the request
  render(<Harness />);
  await flush();
  expect(screenShown()).not.toBeInTheDocument();                  // not before the grace period

  await advance(GATE_AFTER_MS);
  expect(screenShown()).toHaveTextContent('The server is waking up');
  expect(screenShown()).toHaveTextContent('Waking the server');
  expect(screenShown()).toHaveTextContent(/sleeps after 15 minutes/);
});

test('the steps move on as the server comes up, and the screen lifts when it is ready', async () => {
  probe.mockResolvedValue(SERVER_WAKING);
  render(<Harness />);
  await flush();
  await advance(GATE_AFTER_MS);
  expect(screenShown()).toBeInTheDocument();

  probe.mockResolvedValue(DB_CONNECTING);                         // booted, opening its database connection
  await advance(4_000);
  await flush();
  expect(screen.getByText('Connecting to the database')).toBeInTheDocument();
  expect(screenShown()).toHaveTextContent(/Waking the server — done/);

  probe.mockResolvedValue(READY);
  await advance(4_000);
  await flush();
  expect(screenShown()).not.toBeInTheDocument();
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

test('a paused database gets the screen at once', async () => {
  probe.mockResolvedValue(DB_PAUSED);
  render(<Harness />);
  await flush();

  expect(screenShown()).toHaveTextContent('The database is waking up');
  expect(screenShown()).toHaveTextContent('Restoring the database');
});

test('a server that fell asleep while the tab sat idle gets the screen again', async () => {
  probe.mockResolvedValue(READY);
  render(<Harness />);
  await flush();
  expect(screenShown()).not.toBeInTheDocument();

  probe.mockImplementation(() => new Promise(() => {}));
  await act(async () => { window.dispatchEvent(new Event(SERVICE_WAKING_EVENT)); });
  await advance(GATE_AFTER_MS);
  expect(screenShown()).toBeInTheDocument();
});

test('after two minutes the visitor can open the site anyway, with a banner saying why', async () => {
  probe.mockResolvedValue(SERVER_WAKING);
  render(<Harness />);
  await flush();
  await advance(120_000);
  await flush();

  await act(async () => { screen.getByRole('button', { name: 'Open the site anyway' }).click(); });
  expect(screenShown()).not.toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Waking up the server');
});
