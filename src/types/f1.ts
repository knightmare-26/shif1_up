export interface Driver {
  id: string;
  name: string;
  team: string;
  number: number;
  nationality: string;
  points: number;
  position: number;
  wins: number;
  podiums: number;
  image?: string;
  dateOfBirth?: string;
  placeOfBirth?: string;
  worldChampionships?: number;
  fastestLaps?: number;
  polePositions?: number;
}

export interface Team {
  id: string;
  name: string;
  nationality: string;
  points: number;
  position: number;
  wins: number;
  base?: string;
  teamChief?: string;
  technicalChief?: string;
  powerUnit?: string;
  firstEntry?: number;
  worldChampionships?: number;
  highestRaceFinish?: number;
  polePositions?: number;
  fastestLaps?: number;
}

export interface Track {
  id: string;
  name: string;
  country: string;
  locality: string;
  image?: string;
  length: number;
  corners: number;
  laps: number;
  raceDistance: number;
  recordLap: string;
  recordHolder: string;
  recordYear: number;
  firstGrandPrix: number;
  circuitType: 'Street Circuit' | 'Race Circuit' | 'Hybrid Circuit';
  lapRecordHolder?: Driver;
  weather?: TrackWeather;
}

export interface TrackWeather {
  temperature: number;
  humidity: number;
  windSpeed: number;
  precipitation: number;
  trackTemperature: number;
  conditions: string;
  forecast?: WeatherForecast[];
}

export interface WeatherForecast {
  time: string;
  temperature: number;
  conditions: string;
  precipitation: number;
}

export interface RaceResult {
  id: string;
  raceName: string;
  circuitName: string;
  date: string;
  country: string;
  locality: string;
  season: number;
  round: number;
  results: DriverResult[];
  qualifying?: QualifyingResult[];
  practice?: PracticeResult[];
}

export interface DriverResult {
  position: number;
  driver: Driver;
  team: Team;
  grid: number;
  points: number;
  status: string;
  time?: string;
  fastestLap?: string;
  fastestLapRank?: number;
  fastestLapTime?: string;
  fastestLapDriver?: Driver;
}

export interface QualifyingResult {
  position: number;
  driver: Driver;
  team: Team;
  q1?: string;
  q2?: string;
  q3?: string;
  bestTime?: string;
}

export interface PracticeResult {
  session: 'FP1' | 'FP2' | 'FP3';
  position: number;
  driver: Driver;
  team: Team;
  time: string;
  gap?: string;
  laps: number;
}

export interface LiveData {
  sessionType: 'Practice' | 'Qualifying' | 'Race' | 'Sprint';
  sessionStatus: 'Not Started' | 'In Progress' | 'Finished' | 'Red Flag' | 'Safety Car';
  currentLap: number;
  totalLaps: number;
  timeRemaining?: string;
  weather: TrackWeather;
  positions: LivePosition[];
  lastUpdated: Date;
}

export interface LivePosition {
  position: number;
  driver: Driver;
  team: Team;
  lastLapTime: string;
  bestLapTime: string;
  gap: string;
  sector1?: string;
  sector2?: string;
  sector3?: string;
  tireCompound: 'Soft' | 'Medium' | 'Hard' | 'Intermediate' | 'Wet';
  fuelLoad: number;
  status: 'Racing' | 'Pit' | 'Out' | 'Retired' | 'DNF';
}

export interface Season {
  year: number;
  races: RaceResult[];
  driverStandings: Driver[];
  teamStandings: Team[];
  isCurrent: boolean;
}

export interface Prediction {
  driverId: string;
  predictedPosition: number;
  confidence: number;
  factors: {
    weather: number;
    gridPenalty: number;
    tireDegradation: number;
    trackIncidents: number;
    fuelStrategy: number;
    historicalPerformance: number;
    teamPace: number;
  };
  reasoning: string[];
}

export interface TelemetryData {
  driverId: string;
  lap: number;
  timestamp: Date;
  throttle: number; // 0-100
  brake: number; // 0-100
  steering: number; // -100 to 100
  speed: number; // km/h
  gear: number;
  rpm: number;
  fuelLoad: number;
  tireWear: {
    frontLeft: number;
    frontRight: number;
    rearLeft: number;
    rearRight: number;
  };
  brakeTemperature: {
    frontLeft: number;
    frontRight: number;
    rearLeft: number;
    rearRight: number;
  };
}

export interface LapAnalysis {
  lapNumber: number;
  driver: Driver;
  team: Team;
  lapTime: string;
  sector1: string;
  sector2: string;
  sector3: string;
  averageSpeed: number;
  maxSpeed: number;
  minSpeed: number;
  fuelConsumption: number;
  tireCompound: string;
  weather: TrackWeather;
  telemetry?: TelemetryData[];
}
