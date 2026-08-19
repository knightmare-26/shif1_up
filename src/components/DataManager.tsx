import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Download,
  Database,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Calendar,
  Users,
  Trophy,
  Lock,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { getStoredToken } from '../services/authApi';
import { triggerIngest, getIngestStatus, getDbStats, clearServerCache, IngestStatus, DbStats } from '../services/adminApi';

const EMPTY_STATS: DbStats = { drivers: 0, constructors: 0, races: 0, race_results: 0, laps: 0, years: [] };

const DataManager: React.FC = () => {
  const { isAuthenticated, user } = useAuth();
  const isAdmin = isAuthenticated && !!user?.is_admin;

  const [yearsInput, setYearsInput] = useState('2022,2023,2024');
  const [includeLaps, setIncludeLaps] = useState(false);
  const [ingestStatus, setIngestStatus] = useState<IngestStatus | null>(null);
  const [dbStats, setDbStats] = useState<DbStats>(EMPTY_STATS);
  const [error, setError] = useState<string | null>(null);

  const refreshStats = useCallback(async () => {
    const token = getStoredToken();
    if (!token) return;
    try {
      const [status, stats] = await Promise.all([getIngestStatus(token), getDbStats(token)]);
      setIngestStatus(status);
      setDbStats(stats);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load admin data');
    }
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    refreshStats();
    const interval = setInterval(refreshStats, 3000);
    return () => clearInterval(interval);
  }, [isAdmin, refreshStats]);

  const startIngest = async () => {
    const token = getStoredToken();
    if (!token) return;
    setError(null);
    const years = yearsInput
      .split(',')
      .map((y) => parseInt(y.trim(), 10))
      .filter((y) => !isNaN(y));
    if (years.length === 0) {
      setError('Enter at least one valid year (e.g. 2022,2023,2024)');
      return;
    }
    try {
      await triggerIngest(token, years, includeLaps);
      await refreshStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start ingest');
    }
  };

  const clearCache = async () => {
    const token = getStoredToken();
    if (!token) return;
    setError(null);
    try {
      await clearServerCache(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear cache');
    }
  };

  const isRunning = ingestStatus?.running ?? false;
  const progress =
    ingestStatus && ingestStatus.races_total > 0
      ? Math.round((ingestStatus.races_done / ingestStatus.races_total) * 100)
      : 0;

  const getStatusColor = () => {
    if (error || ingestStatus?.error) return 'text-red-500';
    if (isRunning) return 'text-yellow-500';
    if (dbStats.races > 0) return 'text-green-500';
    return 'text-gray-500';
  };

  const getStatusIcon = () => {
    if (error || ingestStatus?.error) return <AlertCircle className="w-5 h-5" />;
    if (isRunning) return <RefreshCw className="w-5 h-5 animate-spin" />;
    if (dbStats.races > 0) return <CheckCircle className="w-5 h-5" />;
    return <Database className="w-5 h-5" />;
  };

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-carbon-black text-pure-white p-6 flex items-center justify-center">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-gray-900 rounded-xl p-8 shadow-2xl text-center max-w-md"
        >
          <Lock className="w-10 h-10 text-racing-red mx-auto mb-4" />
          <h1 className="text-2xl font-racing text-racing-red mb-2">Admin Access Required</h1>
          <p className="text-gray-400 mb-6">
            {isAuthenticated
              ? 'This account does not have admin access.'
              : 'Data Manager is an admin-only override for backfilling data that failed to ingest live.'}
          </p>
          {!isAuthenticated && (
            <Link
              to="/login"
              className="inline-block bg-racing-red text-pure-white px-6 py-3 rounded-lg hover:bg-red-700 transition-colors"
            >
              Log In
            </Link>
          )}
        </motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-carbon-black text-pure-white p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <h1 className="text-4xl font-racing text-racing-red mb-2">
            F1 Data Manager
          </h1>
          <p className="text-gray-400">
            Admin override — backfill data that wasn't captured automatically during a live session
          </p>
        </motion.div>

        {/* Status Overview */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8"
        >
          <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
            <div className="flex items-center space-x-3 mb-2">
              {getStatusIcon()}
              <h3 className="text-lg font-semibold text-pure-white">Status</h3>
            </div>
            <p className={`text-2xl font-bold ${getStatusColor()}`}>
              {error || ingestStatus?.error ? 'Error' : isRunning ? 'Ingesting...' : dbStats.races > 0 ? 'Ready' : 'No Data'}
            </p>
            <p className="text-sm text-gray-400">
              {ingestStatus?.message || 'Idle'}
            </p>
          </div>

          <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
            <div className="flex items-center space-x-3 mb-2">
              <Calendar className="w-6 h-6 text-racing-red" />
              <h3 className="text-lg font-semibold text-pure-white">Years</h3>
            </div>
            <p className="text-2xl font-bold text-pure-white">
              {dbStats.years.length}
            </p>
            <p className="text-sm text-gray-400">
              {dbStats.years.length > 0 ? `${dbStats.years[0]}-${dbStats.years[dbStats.years.length - 1]}` : 'No data'}
            </p>
          </div>

          <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
            <div className="flex items-center space-x-3 mb-2">
              <Users className="w-6 h-6 text-turbo-teal" />
              <h3 className="text-lg font-semibold text-pure-white">Drivers</h3>
            </div>
            <p className="text-2xl font-bold text-pure-white">
              {dbStats.drivers.toLocaleString()}
            </p>
            <p className="text-sm text-gray-400">
              Total driver records
            </p>
          </div>

          <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
            <div className="flex items-center space-x-3 mb-2">
              <Trophy className="w-6 h-6 text-pit-stop-yellow" />
              <h3 className="text-lg font-semibold text-pure-white">Races</h3>
            </div>
            <p className="text-2xl font-bold text-pure-white">
              {dbStats.races.toLocaleString()}
            </p>
            <p className="text-sm text-gray-400">
              Total race records
            </p>
          </div>
        </motion.div>

        {/* Ingest Controls */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-gray-900 rounded-xl p-6 shadow-2xl mb-8"
        >
          <h3 className="text-lg font-semibold text-pure-white mb-4">Backfill Ingest</h3>
          <div className="flex flex-wrap items-center gap-4 mb-4">
            <input
              type="text"
              value={yearsInput}
              onChange={(e) => setYearsInput(e.target.value)}
              disabled={isRunning}
              placeholder="2022,2023,2024"
              className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-pure-white disabled:opacity-50"
            />
            <label className="flex items-center space-x-2 text-sm text-gray-400">
              <input
                type="checkbox"
                checked={includeLaps}
                onChange={(e) => setIncludeLaps(e.target.checked)}
                disabled={isRunning}
              />
              <span>Include lap telemetry (slow)</span>
            </label>
          </div>
          <div className="flex flex-wrap gap-4">
            <button
              onClick={startIngest}
              disabled={isRunning}
              className="bg-racing-red text-pure-white px-6 py-3 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
            >
              {isRunning ? (
                <RefreshCw className="w-5 h-5 animate-spin" />
              ) : (
                <Download className="w-5 h-5" />
              )}
              <span>{isRunning ? 'Ingesting...' : 'Run Ingest'}</span>
            </button>

            <button
              onClick={clearCache}
              disabled={isRunning}
              className="bg-gray-700 text-pure-white px-6 py-3 rounded-lg hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
            >
              <Database className="w-5 h-5" />
              <span>Clear Server Cache</span>
            </button>
          </div>
        </motion.div>

        {/* Progress Bar */}
        {isRunning && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-8"
          >
            <div className="bg-gray-900 rounded-xl p-6 shadow-2xl">
              <h3 className="text-lg font-semibold text-pure-white mb-4">Ingest Progress</h3>
              <div className="w-full bg-gray-700 rounded-full h-3 mb-4">
                <motion.div
                  className="bg-racing-red h-3 rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${progress}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>
              <p className="text-sm text-gray-400">
                {ingestStatus?.races_done ?? 0} / {ingestStatus?.races_total ?? 0} races ({progress}%)
              </p>
            </div>
          </motion.div>
        )}

        {/* Error Display */}
        {(error || ingestStatus?.error) && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-8"
          >
            <div className="bg-red-900/20 border border-red-500 rounded-xl p-6">
              <div className="flex items-center space-x-3 mb-2">
                <AlertCircle className="w-6 h-6 text-red-500" />
                <h3 className="text-lg font-semibold text-red-500">Error</h3>
              </div>
              <p className="text-red-300">{error || ingestStatus?.error}</p>
            </div>
          </motion.div>
        )}

        {/* Available Years List */}
        {dbStats.years.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="bg-gray-900 rounded-xl p-6 shadow-2xl"
          >
            <h3 className="text-xl font-bold text-racing-red mb-4">Available Years</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
              {dbStats.years.map((year) => (
                <div
                  key={year}
                  className="bg-gray-800 rounded-lg p-3 text-center hover:bg-gray-700 transition-colors"
                >
                  <div className="text-lg font-bold text-pure-white">{year}</div>
                  <div className="text-xs text-gray-400">In database</div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
};

export default DataManager;
