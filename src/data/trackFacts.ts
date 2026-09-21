// Static circuit facts, keyed by FastF1's event Location field ("Sakhir",
// "Zandvoort", ...) — that's what circuit_name holds throughout this app.

export interface TrackFacts {
  length: string;
  corners: number;
  record?: { time: string; holder: string; year: number };
}

// Different schedule sources spell the same location differently (the static
// public/data/schedule files use "Montreal"/"Monte Carlo"/"Spa"/"Abu Dhabi";
// FastF1's live Location field uses "Montréal"/"Monaco"/"Spa-Francorchamps"/
// "Yas Island"). Normalise to the latter before looking anything up.
const LOCATION_ALIASES: Record<string, string> = {
  'Montreal': 'Montréal',
  'Monte Carlo': 'Monaco',
  'Spa': 'Spa-Francorchamps',
  'Abu Dhabi': 'Yas Island',
  'Yas Marina': 'Yas Island',
  'Miami Gardens': 'Miami',
  'Sao Paulo': 'São Paulo',
};

const TRACKS: Record<string, TrackFacts> = {
  // Madring — new for 2026, no race run yet so no lap record
  'Madrid':            { length: '5.474 km', corners: 20 },
  'Sakhir':            { length: '5.412 km', corners: 15, record: { time: '1:31.447', holder: 'Max Verstappen', year: 2024 } },
  'Jeddah':            { length: '6.174 km', corners: 27, record: { time: '1:27.791', holder: 'Lewis Hamilton', year: 2021 } },
  'Melbourne':         { length: '5.278 km', corners: 16, record: { time: '1:17.706', holder: 'Charles Leclerc', year: 2022 } },
  'Monaco':            { length: '3.337 km', corners: 19, record: { time: '1:12.909', holder: 'Lewis Hamilton', year: 2019 } },
  'Barcelona':         { length: '4.675 km', corners: 16, record: { time: '1:16.330', holder: 'Max Verstappen', year: 2023 } },
  'Montréal':          { length: '4.361 km', corners: 14, record: { time: '1:13.078', holder: 'Valtteri Bottas', year: 2019 } },
  'Spielberg':         { length: '4.318 km', corners: 10, record: { time: '1:05.619', holder: 'Carlos Sainz', year: 2020 } },
  'Silverstone':       { length: '5.891 km', corners: 18, record: { time: '1:26.720', holder: 'Max Verstappen', year: 2023 } },
  'Budapest':          { length: '4.381 km', corners: 14, record: { time: '1:16.627', holder: 'Lewis Hamilton', year: 2020 } },
  'Spa-Francorchamps': { length: '7.004 km', corners: 20, record: { time: '1:41.252', holder: 'Valtteri Bottas', year: 2018 } },
  'Zandvoort':         { length: '4.259 km', corners: 14, record: { time: '1:10.567', holder: 'Max Verstappen', year: 2021 } },
  'Monza':             { length: '5.793 km', corners: 11, record: { time: '1:18.887', holder: 'Carlos Sainz', year: 2023 } },
  'Marina Bay':        { length: '5.063 km', corners: 23, record: { time: '1:35.867', holder: 'Lewis Hamilton', year: 2018 } },
  'Suzuka':            { length: '5.807 km', corners: 18, record: { time: '1:30.983', holder: 'Max Verstappen', year: 2019 } },
  'Austin':            { length: '5.513 km', corners: 20, record: { time: '1:34.356', holder: 'Charles Leclerc', year: 2019 } },
  'Mexico City':       { length: '4.304 km', corners: 17, record: { time: '1:14.759', holder: 'Valtteri Bottas', year: 2021 } },
  'São Paulo':         { length: '4.309 km', corners: 15, record: { time: '1:10.540', holder: 'Valtteri Bottas', year: 2018 } },
  'Yas Island':        { length: '5.281 km', corners: 16, record: { time: '1:26.103', holder: 'Max Verstappen', year: 2021 } },
  'Miami':             { length: '5.412 km', corners: 19, record: { time: '1:29.708', holder: 'Max Verstappen', year: 2023 } },
  'Imola':             { length: '4.909 km', corners: 19, record: { time: '1:15.484', holder: 'Lewis Hamilton', year: 2020 } },
  'Lusail':            { length: '5.380 km', corners: 16, record: { time: '1:24.319', holder: 'Max Verstappen', year: 2021 } },
  'Las Vegas':         { length: '6.201 km', corners: 17, record: { time: '1:35.776', holder: 'Oscar Piastri', year: 2023 } },
  'Shanghai':          { length: '5.451 km', corners: 16, record: { time: '1:32.238', holder: 'Michael Schumacher', year: 2004 } },
  'Baku':              { length: '6.003 km', corners: 20, record: { time: '1:43.009', holder: 'Charles Leclerc', year: 2019 } },
  'Le Castellet':      { length: '5.842 km', corners: 15, record: { time: '1:32.740', holder: 'Sebastian Vettel', year: 2019 } },
  // 'Kuala Lumpur' (2026's "Bahrain Grand Prix in Malaysia") is deliberately absent:
  // new venue for this calendar, so its layout and record haven't been verified.
};

export const getTrackFacts = (location?: string | null): TrackFacts | null => {
  if (!location || location === 'Unavailable') return null;
  return TRACKS[LOCATION_ALIASES[location] ?? location] ?? null;
};
