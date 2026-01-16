import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import LoginPage from './components/LoginPage';
import SignupPage from './components/SignupPage';
import MainPage from './components/MainPage';
import TrackAnalytics from './components/TrackAnalytics';
import DriverAnalytics from './components/DriverAnalytics';
import LiveAnalytics from './components/LiveAnalytics';
import Dashboard from './components/Dashboard';
import Navigation from './components/Navigation';
import PublicHeader from './components/PublicHeader';
import RaceResults from './components/RaceResults';
import LapData from './components/LapData';
import DataManager from './components/DataManager';
import LiveDataMonitor from './components/LiveDataMonitor';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import './App.css';

const AppContent: React.FC = () => {
  const { isAuthenticated } = useAuth();

  return (
    <div className="App">
      <AnimatePresence mode="wait">
        {isAuthenticated ? (
          <>
            <Navigation />
            <div className="pt-20"> {/* Offset for top navigation */}
              <Routes>
                <Route path="/" element={<MainPage />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/drivers" element={<DriverAnalytics />} />
                <Route path="/tracks" element={<TrackAnalytics />} />
                <Route path="/live" element={<LiveAnalytics />} />
                <Route path="/race-results" element={<RaceResults />} />
                <Route path="/lap-data" element={<LapData />} />
                <Route path="/data-manager" element={<DataManager />} />
                <Route path="/live-monitor" element={<LiveDataMonitor />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </div>
          </>
        ) : (
          <>
            <PublicHeader />
            <div className="pt-16"> {/* Offset for header */}
              <Routes>
                <Route path="/" element={<MainPage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/signup" element={<SignupPage />} />
                <Route path="/tracks" element={<TrackAnalytics />} />
                <Route path="/drivers" element={<DriverAnalytics />} />
                <Route path="/live" element={<LiveAnalytics />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};

const App: React.FC = () => {
  return (
    <Router>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </Router>
  );
};

export default App;
