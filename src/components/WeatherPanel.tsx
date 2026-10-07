import React from 'react';
import { ArrowUp, CloudRain, Droplets, Sun, Thermometer, Wind } from 'lucide-react';
import type { WeatherReading } from '../services/backendApi';

const fmt = (value: number | null | undefined, unit: string, digits = 1) =>
  value == null ? '—' : `${value.toFixed(digits)}${unit}`;

/** The timing-screen weather strip: Air, Track, Humidity, Wind (with direction) and Rain. */
const WeatherPanel: React.FC<{ weather: WeatherReading | null | undefined; className?: string }> = ({ weather, className = '' }) => {
  const w = weather;
  // Wind direction is where it blows *from*; the arrow shows where it's going.
  const windArrow = w?.wind_direction != null ? (w.wind_direction + 180) % 360 : null;
  const items: { label: string; value: React.ReactNode; icon: React.ReactNode }[] = [
    { label: 'Air', value: fmt(w?.air_temperature, '°C'), icon: <Thermometer className="h-4 w-4" /> },
    { label: 'Track', value: fmt(w?.track_temperature, '°C'), icon: <Sun className="h-4 w-4" /> },
    { label: 'Humidity', value: fmt(w?.humidity, '%'), icon: <Droplets className="h-4 w-4" /> },
    {
      label: 'Wind',
      icon: <Wind className="h-4 w-4" />,
      value: (
        <span className="inline-flex items-center gap-1">
          {fmt(w?.wind_speed_kmh, ' km/h')}
          {windArrow != null && (
            <ArrowUp className="h-4 w-4 text-gray-400" style={{ transform: `rotate(${windArrow}deg)` }}
              aria-label={`from ${Math.round(w!.wind_direction!)}°`} />
          )}
        </span>
      ),
    },
    {
      label: 'Rain',
      icon: <CloudRain className="h-4 w-4" />,
      value: w ? <span className={w.rain ? 'text-sky-400' : undefined}>{w.rain ? 'Yes' : 'No'}</span> : '—',
    },
  ];
  return (
    <dl className={`grid grid-cols-2 gap-3 sm:grid-cols-5 ${className}`}>
      {items.map(({ label, value, icon }) => (
        <div key={label} className="rounded-lg border border-gray-800 bg-gray-800/40 px-4 py-3">
          <dt className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-gray-500">
            <span className="text-racing-red" aria-hidden="true">{icon}</span>{label}
          </dt>
          <dd className="mt-1 text-lg font-semibold tabular-nums text-white">{value}</dd>
        </div>
      ))}
    </dl>
  );
};

export default WeatherPanel;
