import React from 'react';
import { motion } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import { BarChart3, TrendingUp, Calendar, Users, MapPin, Flag } from 'lucide-react';

const Dashboard: React.FC = () => {
  const { user } = useAuth();

  if (!user) {
    return (
      <div className="min-h-screen bg-carbon-black flex items-center justify-center">
        <div className="text-pure-white">Loading...</div>
      </div>
    );
  }

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
          F1 Dashboard
        </h1>
        <p className="text-pure-white text-lg">
          Your personalized Formula 1 analytics overview
        </p>
      </motion.div>

      {/* Stats Grid */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8"
      >
        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Next Race</p>
              <p className="text-2xl font-bold text-carbon-black">Monaco GP</p>
            </div>
            <Calendar className="w-8 h-8 text-racing-red" />
          </div>
        </div>

        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Driver Points</p>
              <p className="text-2xl font-bold text-carbon-black">1st</p>
            </div>
            <Users className="w-8 h-8 text-turbo-teal" />
          </div>
        </div>

        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Team Points</p>
              <p className="text-2xl font-bold text-carbon-black">1st</p>
            </div>
            <Flag className="w-8 h-8 text-pit-stop-yellow" />
          </div>
        </div>

        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">Season Wins</p>
              <p className="text-2xl font-bold text-carbon-black">8</p>
            </div>
            <TrendingUp className="w-8 h-8 text-racing-red" />
          </div>
        </div>
      </motion.div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Favorite Driver Analysis */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="bg-track-grey rounded-xl p-6 shadow-lg"
        >
          <h3 className="text-xl font-bold text-carbon-black mb-4 flex items-center">
            <Users className="w-5 h-5 text-racing-red mr-2" />
            {user.preferences.favoriteDriver} Analysis
          </h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center p-3 bg-pure-white rounded-lg">
              <span className="text-carbon-black">Current Position</span>
              <span className="font-bold text-racing-red">1st</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-pure-white rounded-lg">
              <span className="text-carbon-black">Points</span>
              <span className="font-bold text-racing-red">170</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-pure-white rounded-lg">
              <span className="text-carbon-black">Wins</span>
              <span className="font-bold text-racing-red">8</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-pure-white rounded-lg">
              <span className="text-carbon-black">Podiums</span>
              <span className="font-bold text-racing-red">10</span>
            </div>
          </div>
        </motion.div>

        {/* Favorite Track Analysis */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, delay: 0.6 }}
          className="bg-track-grey rounded-xl p-6 shadow-lg"
        >
          <h3 className="text-xl font-bold text-carbon-black mb-4 flex items-center">
            <MapPin className="w-5 h-5 text-turbo-teal mr-2" />
            {user.preferences.favoriteTrack} Analysis
          </h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center p-3 bg-pure-white rounded-lg">
              <span className="text-carbon-black">Track Length</span>
              <span className="font-bold text-turbo-teal">3.337 km</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-pure-white rounded-lg">
              <span className="text-carbon-black">Corners</span>
              <span className="font-bold text-turbo-teal">19</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-pure-white rounded-lg">
              <span className="text-carbon-black">Lap Record</span>
              <span className="font-bold text-turbo-teal">1:12.909</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-pure-white rounded-lg">
              <span className="text-carbon-black">Record Holder</span>
              <span className="font-bold text-turbo-teal">Lewis Hamilton</span>
            </div>
          </div>
        </motion.div>
      </div>

      {/* Recent Results */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.8 }}
        className="mt-8 bg-track-grey rounded-xl p-6 shadow-lg"
      >
        <h3 className="text-xl font-bold text-carbon-black mb-4 flex items-center">
          <BarChart3 className="w-5 h-5 text-racing-red mr-2" />
          Recent Race Results
        </h3>
        <div className="space-y-3">
          <div className="flex items-center justify-between p-4 bg-pure-white rounded-lg">
            <div className="flex items-center space-x-4">
              <span className="text-2xl font-bold text-racing-red">1st</span>
              <div>
                <p className="font-medium text-carbon-black">Australian Grand Prix</p>
                <p className="text-sm text-gray-600">Melbourne, Australia</p>
              </div>
            </div>
            <span className="text-sm text-gray-500">March 24, 2024</span>
          </div>
          
          <div className="flex items-center justify-between p-4 bg-pure-white rounded-lg">
            <div className="flex items-center space-x-4">
              <span className="text-2xl font-bold text-racing-red">1st</span>
              <div>
                <p className="font-medium text-carbon-black">Saudi Arabian Grand Prix</p>
                <p className="text-sm text-gray-600">Jeddah, Saudi Arabia</p>
              </div>
            </div>
            <span className="text-sm text-gray-500">March 9, 2024</span>
          </div>
          
          <div className="flex items-center justify-between p-4 bg-pure-white rounded-lg">
            <div className="flex items-center space-x-4">
              <span className="text-2xl font-bold text-racing-red">1st</span>
              <div>
                <p className="font-medium text-carbon-black">Bahrain Grand Prix</p>
                <p className="text-sm text-gray-600">Sakhir, Bahrain</p>
              </div>
            </div>
            <span className="text-sm text-gray-500">March 2, 2024</span>
          </div>
        </div>
      </motion.div>
    </div>
  );
};

export default Dashboard;
