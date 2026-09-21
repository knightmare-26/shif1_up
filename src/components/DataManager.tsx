import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Download, Database, RefreshCw, CheckCircle, AlertCircle, Calendar, Users, Trophy, Lock, BrainCircuit } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { getStoredToken } from '../services/authApi';
import { triggerIngest, getIngestStatus, getDbStats, clearServerCache, triggerModelTraining, IngestStatus, DbStats } from '../services/adminApi';
import { backendApi } from '../services/backendApi';
import {
  Button, Card, CardBody, CardHeader, EmptyState, FadeIn, Notice, PageHeader, PageShell, Pill,
  StatCard, TextField,
} from './ui';

const EMPTY_STATS: DbStats = { drivers: 0, constructors: 0, races: 0, race_results: 0, laps: 0, years: [] };
const CURRENT_YEAR = new Date().getFullYear();

const DataManager: React.FC = () => {
  const { isAuthenticated, user } = useAuth();
  const isAdmin = isAuthenticated && !!user?.is_admin;

  const [yearsInput, setYearsInput] = useState(String(CURRENT_YEAR));
  const [includeLaps, setIncludeLaps] = useState(false);
  const [ingestStatus, setIngestStatus] = useState<IngestStatus | null>(null);
  const [dbStats, setDbStats] = useState<DbStats>(EMPTY_STATS);
  const [error, setError] = useState<string | null>(null);
  const [predictStatus, setPredictStatus] = useState<any>(null);
  const [training, setTraining] = useState(false);

  const refreshStats = useCallback(async () => {
    const token = getStoredToken();
    if (!token) return;
    try {
      const [status, stats, predict] = await Promise.all([
        getIngestStatus(token),
        getDbStats(token),
        backendApi.getPredictionStatus(),
      ]);
      setIngestStatus(status);
      setDbStats(stats);
      setPredictStatus(predict);
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
      setError(`Enter at least one valid year (e.g. ${CURRENT_YEAR - 1},${CURRENT_YEAR})`);
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

  const retrain = async () => {
    const token = getStoredToken();
    if (!token) return;
    setError(null);
    setTraining(true);
    try {
      await triggerModelTraining(token);
      setTimeout(async () => {
        setPredictStatus(await backendApi.getPredictionStatus().catch(() => null));
        setTraining(false);
      }, 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start training');
      setTraining(false);
    }
  };

  const isRunning = ingestStatus?.running ?? false;
  const failure = error || ingestStatus?.error;
  const progress =
    ingestStatus && ingestStatus.races_total > 0
      ? Math.round((ingestStatus.races_done / ingestStatus.races_total) * 100)
      : 0;

  const status = failure
    ? { label: 'Error', accent: 'text-red-500', icon: <AlertCircle className="h-6 w-6" /> }
    : isRunning
    ? { label: 'Ingesting…', accent: 'text-yellow-500', icon: <RefreshCw className="h-6 w-6 animate-spin" /> }
    : dbStats.races > 0
    ? { label: 'Ready', accent: 'text-green-500', icon: <CheckCircle className="h-6 w-6" /> }
    : { label: 'No data', accent: 'text-gray-500', icon: <Database className="h-6 w-6" /> };

  if (!isAdmin) {
    return (
      <PageShell>
        <Card className="mx-auto mt-10 max-w-md">
          <EmptyState
            className="py-12"
            icon={<Lock className="h-10 w-10 text-racing-red" />}
            title="Admin access required"
            message={isAuthenticated
              ? 'This account does not have admin access.'
              : 'Data Manager is an admin-only override for backfilling data that failed to ingest live.'}
            action={!isAuthenticated ? <Link to="/login"><Button>Log in</Button></Link> : undefined}
          />
        </Card>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        title="Data Manager"
        subtitle="Admin override — backfill data that wasn't captured automatically during a live session"
      />

      <FadeIn className="space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Status" value={status.label} sub={ingestStatus?.message || 'Idle'} icon={status.icon} accent={status.accent} />
          <StatCard label="Years" icon={<Calendar className="h-6 w-6" />}
            value={dbStats.years.length}
            sub={dbStats.years.length > 0 ? `${dbStats.years[0]}–${dbStats.years[dbStats.years.length - 1]}` : 'No data'} />
          <StatCard label="Drivers" icon={<Users className="h-6 w-6" />} accent="text-turbo-teal"
            value={dbStats.drivers.toLocaleString()} sub="Driver records" />
          <StatCard label="Races" icon={<Trophy className="h-6 w-6" />} accent="text-pit-stop-yellow"
            value={dbStats.races.toLocaleString()} sub="Race records" />
        </div>

        {failure && <Notice tone="error" className=""><strong>Error:</strong> {failure}</Notice>}

        <Card>
          <CardHeader title="Backfill Ingest" icon={<Download className="h-4 w-4" />}
            subtitle="Comma-separated seasons to (re)load results for" />
          <CardBody className="space-y-4">
            <div className="flex flex-wrap items-end gap-4">
              <TextField label="Years" value={yearsInput} onChange={setYearsInput} disabled={isRunning}
                placeholder={`${CURRENT_YEAR - 1},${CURRENT_YEAR}`} />
              <label className="flex items-center gap-2 pb-2 text-sm text-gray-400">
                <input type="checkbox" checked={includeLaps} disabled={isRunning}
                  onChange={(e) => setIncludeLaps(e.target.checked)} />
                Include lap telemetry (slow)
              </label>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button onClick={startIngest} disabled={isRunning} loading={isRunning} icon={<Download className="h-4 w-4" />}>
                {isRunning ? 'Ingesting…' : 'Run Ingest'}
              </Button>
              <Button variant="secondary" onClick={clearCache} disabled={isRunning} icon={<Database className="h-4 w-4" />}>
                Clear Server Cache
              </Button>
            </div>

            {isRunning && (
              <div>
                <div className="h-2 overflow-hidden rounded-full bg-gray-800" role="progressbar"
                  aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} aria-label="Ingest progress">
                  <div className="h-full rounded-full bg-racing-red transition-[width] duration-500" style={{ width: `${progress}%` }} />
                </div>
                <p className="mt-2 text-sm text-gray-400">
                  {ingestStatus?.races_done ?? 0} / {ingestStatus?.races_total ?? 0} races ({progress}%)
                </p>
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Prediction Models" icon={<BrainCircuit className="h-4 w-4" />}
            subtitle="Models retrain automatically once a race finishes ingesting. Use this only to force a retrain." />
          <CardBody className="flex flex-wrap items-center gap-3">
            <Button onClick={retrain} loading={training} icon={<BrainCircuit className="h-4 w-4" />}>
              {training ? 'Retraining…' : 'Retrain Models'}
            </Button>
            {predictStatus && (
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone={predictStatus.race_model_ready ? 'good' : 'bad'}>Race: {predictStatus.race_model_ready ? 'ready' : 'not trained'}</Pill>
                <Pill tone={predictStatus.quali_model_ready ? 'good' : 'warn'}>Quali: {predictStatus.quali_model_ready ? 'ready' : 'needs grid data'}</Pill>
                {predictStatus.training_rows > 0 && <Pill>{predictStatus.training_rows} rows · {predictStatus.circuits} circuits</Pill>}
              </div>
            )}
          </CardBody>
        </Card>

        {dbStats.years.length > 0 && (
          <Card>
            <CardHeader title="Seasons in the database" icon={<Calendar className="h-4 w-4" />} />
            <CardBody className="grid grid-cols-2 gap-2 md:grid-cols-4 lg:grid-cols-6">
              {dbStats.years.map((year) => (
                <div key={year} className="rounded-lg bg-gray-800/50 p-3 text-center">
                  <div className="text-lg font-bold tabular-nums text-white">{year}</div>
                  <div className="text-xs text-gray-500">Loaded</div>
                </div>
              ))}
            </CardBody>
          </Card>
        )}
      </FadeIn>
    </PageShell>
  );
};

export default DataManager;
