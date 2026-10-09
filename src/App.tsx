import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import MainPage from './components/MainPage';
import LiveAnalytics from './components/LiveAnalytics';
import Dashboard from './components/Dashboard';
import Navigation from './components/Navigation';
import LapData from './components/LapData';
import DataManager from './components/DataManager';
import LiveDataMonitor from './components/LiveDataMonitor';
import Predictions from './components/Predictions';
import LoginPage from './components/LoginPage';
import SignupPage from './components/SignupPage';
import { ServiceStatusBanner, useServiceStatus } from './components/ServiceStatusBanner';
import { ServiceGate } from './components/ServiceGate';
import './App.css';

const AppContent: React.FC = () => {
  // Wakes a sleeping API host on load. The pages mount straight away: an awake server answers
  // within a few seconds and nothing else shows. A sleeping one (Render's free plan sleeps after
  // 15 minutes without visitors) or a database that's down gets the blurred wake-up screen over
  // the pages until it's ready. `epoch` remounts the routes after a recovery so failed loads retry.
  const { status, slow, epoch, gated, elapsed, retry, dismiss } = useServiceStatus();

  return (
    <div className="App">
      <Navigation />
      {gated && <ServiceGate status={status} elapsed={elapsed} onRetry={retry} onContinue={dismiss} />}
      <main className="pt-16">
        {!gated && <ServiceStatusBanner status={status} slow={slow} />}
        <div key={epoch} aria-hidden={gated || undefined}>
        <Routes>
          <Route path="/"             element={<MainPage />} />
          <Route path="/dashboard"    element={<Dashboard />} />
          <Route path="/predictions"  element={<Predictions />} />
          <Route path="/race-results" element={<Navigate to="/dashboard?tab=results" replace />} />
          <Route path="/drivers"      element={<Navigate to="/dashboard?tab=drivers" replace />} />
          <Route path="/tracks"       element={<Navigate to="/dashboard?tab=tracks" replace />} />
          <Route path="/live"         element={<LiveAnalytics />} />
          <Route path="/lap-data"     element={<LapData />} />
          <Route path="/live-monitor" element={<LiveDataMonitor />} />
          <Route path="/data-manager" element={<DataManager />} />
          <Route path="/login"        element={<LoginPage />} />
          <Route path="/signup"       element={<SignupPage />} />
          <Route path="*"             element={<Navigate to="/" replace />} />
        </Routes>
        </div>
      </main>
    </div>
  );
};

const App: React.FC = () => (
  <Router>
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  </Router>
);

export default App;
