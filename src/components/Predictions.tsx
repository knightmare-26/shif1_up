import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, AlertTriangle, RefreshCw, ChevronDown } from 'lucide-react';
import { backendApi } from '../services/backendApi';

interface PredictionRow {
  predicted_rank: number;
  driver_id: string;
  driver_name: string;
  constructor_id: string;
  constructor_name: string;
  predicted_position?: number;
  predicted_grid?: number;
  circuit_avg_finish?: number | null;
  circuit_avg_grid?: number | null;
  rolling_avg_finish?: number | null;
  rolling_avg_grid?: number | null;
}

interface PredictionResult {
  success: boolean;
  circuit: string;
  model: string;
  grid_data_available: boolean;
  predictions: PredictionRow[];
  error?: string;
}

const positionColor = (pos: number): string => {
  if (pos <= 3)  return 'text-yellow-400 font-bold';
  if (pos <= 10) return 'text-green-400';
  return 'text-gray-400';
};

const medalEmoji = (rank: number): string => {
  if (rank === 1) return '🥇';
  if (rank === 2) return '🥈';
  if (rank === 3) return '🥉';
  return `${rank}`;
};

const PredictionTable: React.FC<{
  title: string;
  subtitle: string;
  data: PredictionRow[];
  valueKey: 'predicted_grid' | 'predicted_position';
  avgKey: 'circuit_avg_grid' | 'circuit_avg_finish';
  rollingKey: 'rolling_avg_grid' | 'rolling_avg_finish';
  model: string;
  gridMissing: boolean;
}> = ({ title, subtitle, data, valueKey, avgKey, rollingKey, model, gridMissing }) => (
  <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden flex-1 min-w-0">
    <div className="px-5 py-4 border-b border-gray-800 flex items-center justify-between">
      <div>
        <h3 className="text-white font-semibold text-base">{title}</h3>
        <p className="text-gray-400 text-xs mt-0.5">{subtitle} · <span className="text-racing-red">{model}</span></p>
      </div>
      {gridMissing && valueKey === 'predicted_position' && (
        <span className="text-xs text-yellow-400 bg-yellow-400/10 px-2 py-1 rounded flex items-center gap-1">
          <AlertTriangle className="w-3 h-3" /> No grid data
        </span>
      )}
    </div>
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-500 text-xs uppercase border-b border-gray-800">
            <th className="px-4 py-2 text-left w-10">#</th>
            <th className="px-4 py-2 text-left">Driver</th>
            <th className="px-4 py-2 text-left hidden sm:table-cell">Team</th>
            <th className="px-4 py-2 text-right">Predicted</th>
            <th className="px-4 py-2 text-right hidden md:table-cell">Circuit Avg</th>
            <th className="px-4 py-2 text-right hidden md:table-cell">Form (5R)</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.driver_id} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
              <td className="px-4 py-2.5 text-center">
                <span className={`text-sm ${positionColor(row.predicted_rank)}`}>
                  {medalEmoji(row.predicted_rank)}
                </span>
              </td>
              <td className="px-4 py-2.5">
                <span className="text-white font-medium text-sm">{row.driver_name}</span>
              </td>
              <td className="px-4 py-2.5 hidden sm:table-cell text-gray-400 text-xs">{row.constructor_name}</td>
              <td className="px-4 py-2.5 text-right">
                <span className={`font-mono font-semibold ${positionColor(row.predicted_rank)}`}>
                  P{Math.round(row[valueKey] ?? row.predicted_rank)}
                </span>
              </td>
              <td className="px-4 py-2.5 text-right hidden md:table-cell text-gray-400 font-mono text-xs">
                {row[avgKey] != null ? `P${row[avgKey]!.toFixed(1)}` : '—'}
              </td>
              <td className="px-4 py-2.5 text-right hidden md:table-cell text-gray-400 font-mono text-xs">
                {row[rollingKey] != null ? `P${row[rollingKey]!.toFixed(1)}` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);

const Predictions: React.FC = () => {
  const [circuits, setCircuits]       = useState<string[]>([]);
  const [selected, setSelected]       = useState('');
  const [loading, setLoading]         = useState(false);
  const [training, setTraining]       = useState(false);
  const [qualiResult, setQualiResult] = useState<PredictionResult | null>(null);
  const [raceResult, setRaceResult]   = useState<PredictionResult | null>(null);
  const [error, setError]             = useState<string | null>(null);
  const [status, setStatus]           = useState<any>(null);

  useEffect(() => {
    backendApi.getPredictionStatus().then(setStatus).catch(() => {});
    backendApi.getPredictionCircuits().then((c) => {
      setCircuits(c);
      if (c.length) setSelected(c[0]);
    }).catch(() => {});
  }, []);

  const runPredictions = async () => {
    if (!selected) return;
    setLoading(true);
    setError(null);
    setQualiResult(null);
    setRaceResult(null);
    try {
      const [q, r] = await Promise.all([
        backendApi.predictQualifying(selected),
        backendApi.predictRace(selected),
      ]);
      setQualiResult(q);
      setRaceResult(r);
    } catch (e: any) {
      setError(e.message || 'Prediction failed. Make sure data is ingested and backend is running.');
    } finally {
      setLoading(false);
    }
  };

  const retrain = async () => {
    setTraining(true);
    try {
      await backendApi.triggerModelTraining();
      setTimeout(() => {
        backendApi.getPredictionStatus().then(setStatus).catch(() => {});
        setTraining(false);
      }, 3000);
    } catch {
      setTraining(false);
    }
  };

  const gridMissing = !status?.grid_data_available;

  return (
    <div className="min-h-screen bg-carbon-black text-white p-4 sm:p-6 lg:p-8">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 bg-racing-red rounded-lg flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-racing text-white">Race Predictions</h1>
            <p className="text-gray-400 text-sm">XGBoost qualifying · LightGBM race finish</p>
          </div>
        </div>
      </motion.div>

      {/* Warning banner when grid data is missing */}
      {gridMissing && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="mb-6 flex items-start gap-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg px-4 py-3 text-sm text-yellow-300">
          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <div>
            <strong>Grid data missing.</strong> Re-ingest 2022–2024 data via the Data Manager to populate qualifying grid positions.
            Race predictions will still work using rolling form averages, but accuracy improves significantly with grid data.
          </div>
        </motion.div>
      )}

      {/* Controls */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
        className="flex flex-wrap items-end gap-4 mb-8">
        {/* Circuit selector */}
        <div className="flex flex-col gap-1">
          <label className="text-gray-400 text-xs uppercase tracking-wide">Circuit</label>
          <div className="relative">
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="appearance-none bg-gray-900 border border-gray-700 text-white text-sm rounded-lg px-4 py-2.5 pr-9 focus:outline-none focus:border-racing-red transition-colors min-w-[240px]"
            >
              {circuits.length === 0 && <option value="">No circuits — ingest data first</option>}
              {circuits.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>
        </div>

        {/* Predict button */}
        <button
          onClick={runPredictions}
          disabled={loading || !selected}
          className="flex items-center gap-2 px-5 py-2.5 bg-racing-red text-white rounded-lg font-medium text-sm hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <TrendingUp className="w-4 h-4" />}
          {loading ? 'Predicting…' : 'Generate Predictions'}
        </button>

        {/* Retrain button */}
        <button
          onClick={retrain}
          disabled={training}
          className="flex items-center gap-2 px-4 py-2.5 bg-gray-800 text-gray-300 rounded-lg text-sm hover:bg-gray-700 disabled:opacity-50 transition-colors"
          title="Retrain models on latest DuckDB data"
        >
          <RefreshCw className={`w-4 h-4 ${training ? 'animate-spin' : ''}`} />
          {training ? 'Retraining…' : 'Retrain Models'}
        </button>

        {/* Status pills */}
        {status && (
          <div className="flex items-center gap-2 ml-auto flex-wrap">
            <span className={`text-xs px-2 py-1 rounded ${status.race_model_ready ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
              Race: {status.race_model_ready ? 'ready' : 'not trained'}
            </span>
            <span className={`text-xs px-2 py-1 rounded ${status.quali_model_ready ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
              Quali: {status.quali_model_ready ? 'ready' : 'needs grid data'}
            </span>
            {status.training_rows > 0 && (
              <span className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-400">
                {status.training_rows} rows · {status.circuits} circuits
              </span>
            )}
          </div>
        )}
      </motion.div>

      {/* Error */}
      {error && (
        <div className="mb-6 flex items-center gap-2 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-sm text-red-400">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Results */}
      {(qualiResult || raceResult) && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          className="flex flex-col lg:flex-row gap-6">
          {qualiResult?.predictions.length ? (
            <PredictionTable
              title="Qualifying Prediction"
              subtitle={qualiResult.circuit}
              data={qualiResult.predictions}
              valueKey="predicted_grid"
              avgKey="circuit_avg_grid"
              rollingKey="rolling_avg_grid"
              model={qualiResult.model}
              gridMissing={gridMissing}
            />
          ) : qualiResult && (
            <div className="flex-1 bg-gray-900 rounded-xl border border-gray-800 px-5 py-8 text-center text-gray-500 text-sm">
              <AlertTriangle className="w-6 h-6 mx-auto mb-2 text-yellow-500" />
              Qualifying prediction unavailable: {qualiResult.error}
            </div>
          )}

          {raceResult?.predictions.length ? (
            <PredictionTable
              title="Race Prediction"
              subtitle={raceResult.circuit}
              data={raceResult.predictions}
              valueKey="predicted_position"
              avgKey="circuit_avg_finish"
              rollingKey="rolling_avg_finish"
              model={raceResult.model}
              gridMissing={gridMissing}
            />
          ) : raceResult && (
            <div className="flex-1 bg-gray-900 rounded-xl border border-gray-800 px-5 py-8 text-center text-gray-500 text-sm">
              <AlertTriangle className="w-6 h-6 mx-auto mb-2 text-red-500" />
              Race prediction unavailable: {raceResult.error}
            </div>
          )}
        </motion.div>
      )}

      {/* Empty state */}
      {!qualiResult && !raceResult && !error && !loading && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}
          className="flex flex-col items-center justify-center py-24 text-center">
          <TrendingUp className="w-12 h-12 text-gray-700 mb-4" />
          <p className="text-gray-500 text-sm">Select a circuit and click <strong className="text-gray-400">Generate Predictions</strong></p>
          <p className="text-gray-600 text-xs mt-1">Models auto-train on first run using ingested DuckDB data</p>
        </motion.div>
      )}
    </div>
  );
};

export default Predictions;
