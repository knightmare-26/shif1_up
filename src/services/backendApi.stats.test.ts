import { backendApi, STORED_RESULTS_FROM } from './backendApi';

// The Drivers/Teams result columns: seasons before the API's database come from committed snapshots.
const SNAPSHOT = { year: 2005, races_counted: 19, sprints_counted: 0, poles_from_grid: [], drivers: [] };
const fetchMock = jest.fn();

beforeEach(() => {
  jest.spyOn(console, 'log').mockImplementation(() => undefined);   // the client's cache chatter
  fetchMock.mockReset();
  global.fetch = fetchMock as unknown as typeof fetch;
});

test('a season before the database is read from its snapshot, without the API', async () => {
  fetchMock.mockResolvedValue({ ok: true, json: async () => SNAPSHOT });

  await expect(backendApi.getDriverStats(2005)).resolves.toEqual(SNAPSHOT);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][0]).toBe('/data/stats/2005_drivers.json');

  fetchMock.mockClear();
  await backendApi.getConstructorStats(2005);
  expect(fetchMock.mock.calls[0][0]).toBe('/data/stats/2005_constructors.json');
});

test('a season in the database goes to the API', async () => {
  fetchMock.mockResolvedValue({ ok: true, status: 200, headers: new Headers(), json: async () => ({ year: STORED_RESULTS_FROM, drivers: [] }) });

  await backendApi.getDriverStats(STORED_RESULTS_FROM);
  expect(fetchMock.mock.calls.map((c) => String(c[0]))).toEqual([expect.stringContaining('/api/driver-stats?year=2022')]);
});
