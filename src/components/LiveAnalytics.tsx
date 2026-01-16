import React from 'react';
import { motion } from 'framer-motion';
import { Activity, Clock, TrendingUp, Zap } from 'lucide-react';

const LiveAnalytics: React.FC = () => {
  const liveData = [
    { driver: 'Max Verstappen', position: 1, lastLap: '1:12.456', gap: 'Leader', status: 'Racing' },
    { driver: 'Lewis Hamilton', position: 2, lastLap: '1:12.789', gap: '+0.333', status: 'Racing' },
    { driver: 'Charles Leclerc', position: 3, lastLap: '1:12.901', gap: '+0.445', status: 'Racing' },
    { driver: 'Lando Norris', position: 4, lastLap: '1:13.123', gap: '+0.667', status: 'Racing' },
    { driver: 'Carlos Sainz', position: 5, lastLap: '1:13.234', gap: '+0.778', status: 'Racing' },
  ];

  return (
    <div className="min-h-screen bg-carbon-black p-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="mb-8"
      >
        <h1 className="text-4xl font-racing text-racing-red mb-2">
          Live Analytics
        </h1>
        <p className="text-pure-white text-lg">
          Real-time Formula 1 data and live race information
        </p>
      </motion.div>

      {/* Live Race Status */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="bg-gradient-to-r from-racing-red to-red-700 rounded-xl p-6 text-pure-white shadow-lg mb-8"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold flex items-center">
            <Activity className="w-6 h-6 mr-3" />
            Live Race Status
          </h2>
          <div className="text-right">
            <p className="text-sm opacity-80">Current Session</p>
            <p className="text-xl font-bold">Race</p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="text-center">
            <p className="text-sm opacity-80">Lap</p>
            <p className="text-3xl font-bold">23 / 78</p>
          </div>
          <div className="text-center">
            <p className="text-sm opacity-80">Time Remaining</p>
            <p className="text-3xl font-bold">45:23</p>
          </div>
          <div className="text-center">
            <p className="text-sm opacity-80">Weather</p>
            <p className="text-3xl font-bold">22°C</p>
          </div>
        </div>
      </motion.div>

      {/* Live Driver Positions */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.4 }}
        className="bg-track-grey rounded-xl p-6 shadow-lg mb-8"
      >
        <h2 className="text-2xl font-bold text-carbon-black mb-6 flex items-center">
          <TrendingUp className="w-6 h-6 text-racing-red mr-3" />
          Live Driver Positions
        </h2>
        <div className="space-y-3">
          {liveData.map((driver, index) => (
            <div key={driver.driver} className="flex items-center justify-between p-4 bg-pure-white rounded-lg">
              <div className="flex items-center space-x-4">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center text-lg font-bold text-pure-white ${
                  index === 0 ? 'bg-yellow-500' :
                  index === 1 ? 'bg-gray-400' :
                  index === 2 ? 'bg-orange-600' : 'bg-gray-600'
                }`}>
                  {driver.position}
                </div>
                <div>
                  <p className="font-bold text-carbon-black text-lg">{driver.driver}</p>
                  <p className="text-sm text-gray-600">Last Lap: {driver.lastLap}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-lg font-bold text-racing-red">{driver.gap}</p>
                <p className="text-sm text-gray-600">{driver.status}</p>
              </div>
            </div>
          ))}
        </div>
      </motion.div>

      {/* Real-time Metrics */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.6 }}
        className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8"
      >
        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center mb-4">
            <Clock className="w-8 h-8 text-racing-red mr-3" />
            <h3 className="text-xl font-bold text-carbon-black">Best Lap</h3>
          </div>
          <p className="text-3xl font-racing text-racing-red mb-2">1:12.456</p>
          <p className="text-sm text-gray-600">Max Verstappen • Lap 18</p>
        </div>

        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center mb-4">
            <Zap className="w-8 h-8 text-turbo-teal mr-3" />
            <h3 className="text-xl font-bold text-carbon-black">Average Lap</h3>
          </div>
          <p className="text-3xl font-racing text-turbo-teal mb-2">1:13.2</p>
          <p className="text-sm text-gray-600">Race pace average</p>
        </div>

        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center mb-4">
            <Activity className="w-8 h-8 text-pit-stop-yellow mr-3" />
            <h3 className="text-xl font-bold text-carbon-black">DNFs</h3>
          </div>
          <p className="text-3xl font-racing text-pit-stop-yellow mb-2">0</p>
          <p className="text-sm text-gray-600">All cars running</p>
        </div>
      </motion.div>

      {/* Coming Soon */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.8 }}
        className="bg-gradient-to-r from-pit-stop-yellow to-yellow-600 rounded-xl p-8 text-center text-pure-white shadow-lg"
      >
        <h3 className="text-2xl font-bold mb-4">Advanced Live Features Coming Soon</h3>
        <p className="text-lg opacity-90 mb-6">
          Real-time telemetry, predictive analytics, and live commentary
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div>
            <p className="font-bold">Live Telemetry</p>
            <p className="opacity-80">Real-time throttle, brake, and steering data</p>
          </div>
          <div>
            <p className="font-bold">Predictive Analytics</p>
            <p className="opacity-80">AI-powered race outcome predictions</p>
          </div>
          <div>
            <p className="font-bold">Live Commentary</p>
            <p className="opacity-80">Expert analysis and race insights</p>
          </div>
        </div>
      </motion.div>
    </div>
  );
};

export default LiveAnalytics;
