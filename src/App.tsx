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
import './App.css';

const AppContent: React.FC = () => {
  // Wakes a sleeping API host on load and explains the wait; when the backend
  // comes back, `epoch` changes and the routes remount so failed loads retry.
  const { status, slow, epoch } = useServiceStatus();

  return (
    <div className="App">
      <Navigation />
      <main className="pt-16">
        <ServiceStatusBanner status={status} slow={slow} />
        <div key={epoch}>
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
