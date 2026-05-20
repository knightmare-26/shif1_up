import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import MainPage from './components/MainPage';
import TrackAnalytics from './components/TrackAnalytics';
import DriverAnalytics from './components/DriverAnalytics';
import LiveAnalytics from './components/LiveAnalytics';
import Dashboard from './components/Dashboard';
import Navigation from './components/Navigation';
import RaceResults from './components/RaceResults';
import LapData from './components/LapData';
import DataManager from './components/DataManager';
import LiveDataMonitor from './components/LiveDataMonitor';
import Predictions from './components/Predictions';
import './App.css';

const AppContent: React.FC = () => {
  return (
    <div className="App">
      <Navigation />
      <main className="pt-16">
        <Routes>
          <Route path="/"             element={<MainPage />} />
          <Route path="/dashboard"    element={<Dashboard />} />
          <Route path="/predictions"  element={<Predictions />} />
          <Route path="/race-results" element={<RaceResults />} />
          <Route path="/drivers"      element={<DriverAnalytics />} />
          <Route path="/tracks"       element={<TrackAnalytics />} />
          <Route path="/live"         element={<LiveAnalytics />} />
          <Route path="/lap-data"     element={<LapData />} />
          <Route path="/live-monitor" element={<LiveDataMonitor />} />
          <Route path="/data-manager" element={<DataManager />} />
          <Route path="*"             element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
};

const App: React.FC = () => (
  <Router>
    <AppContent />
  </Router>
);

export default App;
