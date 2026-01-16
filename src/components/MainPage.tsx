import React from 'react';
import { motion } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import { Link } from 'react-router-dom';
import { Car, MapPin, Flag, TrendingUp, Calendar, Users, LogIn, UserPlus } from 'lucide-react';

const MainPage: React.FC = () => {
  const { isAuthenticated, user } = useAuth();

  if (isAuthenticated && user) {
    return (
      <div className="min-h-screen bg-carbon-black p-8">
        {/* Welcome Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="mb-8"
        >
          <h1 className="text-4xl font-racing text-racing-red mb-2">
            Welcome back, {user.username}! 🏎️
          </h1>
          <p className="text-pure-white text-lg">
            Here's your personalized F1 experience
          </p>
        </motion.div>

        {/* User Preferences Summary */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8"
        >
          <div className="bg-track-grey rounded-xl p-6 shadow-lg">
            <div className="flex items-center mb-4">
              <Car className="w-6 h-6 text-racing-red mr-3" />
              <h3 className="text-lg font-bold text-carbon-black">Favorite Driver</h3>
            </div>
            <p className="text-2xl font-racing text-racing-red">{user.preferences.favoriteDriver}</p>
          </div>

          <div className="bg-track-grey rounded-xl p-6 shadow-lg">
            <div className="flex items-center mb-4">
              <MapPin className="w-6 h-6 text-turbo-teal mr-3" />
              <h3 className="text-lg font-bold text-carbon-black">Favorite Track</h3>
            </div>
            <p className="text-2xl font-racing text-turbo-teal">{user.preferences.favoriteTrack}</p>
          </div>

          <div className="bg-track-grey rounded-xl p-6 shadow-lg">
            <div className="flex items-center mb-4">
              <Flag className="w-6 h-6 text-pit-stop-yellow mr-3" />
              <h3 className="text-lg font-bold text-carbon-black">Favorite Team</h3>
            </div>
            <p className="text-2xl font-racing text-pit-stop-yellow">{user.preferences.favoriteTeam}</p>
          </div>

          <div className="bg-track-grey rounded-xl p-6 shadow-lg">
            <div className="flex items-center mb-4">
              <TrendingUp className="w-6 h-6 text-racing-red mr-3" />
              <h3 className="text-lg font-bold text-carbon-black">Experience</h3>
            </div>
            <p className="text-2xl font-racing text-racing-red capitalize">{user.preferences.experienceLevel}</p>
          </div>
        </motion.div>

        {/* Quick Actions */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8"
        >
          <Link to="/race-results" className="bg-gradient-to-br from-racing-red to-red-700 rounded-xl p-6 text-pure-white shadow-lg hover:shadow-xl transition-all duration-300 transform hover:scale-105">
            <Calendar className="w-8 h-8 mb-4" />
            <h3 className="text-xl font-bold mb-2">Race Results</h3>
            <p className="text-sm opacity-90">View detailed race classifications and results</p>
          </Link>

          <Link to="/lap-data" className="bg-gradient-to-br from-turbo-teal to-blue-700 rounded-xl p-6 text-pure-white shadow-lg hover:shadow-xl transition-all duration-300 transform hover:scale-105">
            <Users className="w-8 h-8 mb-4" />
            <h3 className="text-xl font-bold mb-2">Lap Analysis</h3>
            <p className="text-sm opacity-90">Detailed lap times and sector analysis</p>
          </Link>

          <Link to="/drivers" className="bg-gradient-to-br from-pit-stop-yellow to-yellow-600 rounded-xl p-6 text-pure-white shadow-lg hover:shadow-xl transition-all duration-300 transform hover:scale-105">
            <MapPin className="w-8 h-8 mb-4" />
            <h3 className="text-xl font-bold mb-2">Driver Stats</h3>
            <p className="text-sm opacity-90">View detailed statistics for {user.preferences.favoriteDriver}</p>
          </Link>

          <Link to="/tracks" className="bg-gradient-to-br from-purple-600 to-purple-800 rounded-xl p-6 text-pure-white shadow-lg hover:shadow-xl transition-all duration-300 transform hover:scale-105">
            <Flag className="w-8 h-8 mb-4" />
            <h3 className="text-xl font-bold mb-2">Track Analysis</h3>
            <p className="text-sm opacity-90">Explore insights about {user.preferences.favoriteTrack}</p>
          </Link>
        </motion.div>

        {/* Recent Activity */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.6 }}
          className="bg-track-grey rounded-xl p-6 shadow-lg"
        >
          <h3 className="text-2xl font-bold text-carbon-black mb-4">Recent Activity</h3>
          <div className="space-y-4">
            <div className="flex items-center p-4 bg-pure-white rounded-lg">
              <div className="w-3 h-3 bg-racing-red rounded-full mr-4"></div>
              <div>
                <p className="text-carbon-black font-medium">Welcome to Shif1 UP!</p>
                <p className="text-sm text-gray-600">Your account was created successfully</p>
              </div>
              <span className="ml-auto text-sm text-gray-500">Just now</span>
            </div>
            
            <div className="flex items-center p-4 bg-pure-white rounded-lg">
              <div className="w-3 h-3 bg-turbo-teal rounded-full mr-4"></div>
              <div>
                <p className="text-carbon-black font-medium">Preferences Set</p>
                <p className="text-sm text-gray-600">Your F1 preferences have been saved</p>
              </div>
              <span className="ml-auto text-sm text-gray-500">Just now</span>
            </div>
          </div>
        </motion.div>
      </div>
    );
  }

  // Non-authenticated user view
  return (
    <div className="min-h-screen bg-carbon-black p-8">
      {/* Welcome Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="text-center mb-12"
      >
        <h1 className="text-6xl font-racing text-racing-red mb-4">
          Shif1 UP
        </h1>
        <h2 className="text-3xl font-f1 text-pure-white mb-6">
          Your F1 Insights Hub
        </h2>
        <p className="text-xl text-gray-300 max-w-4xl mx-auto leading-relaxed">
          Experience the thrill of Formula 1 with cutting-edge analytics, real-time telemetry, 
          and AI-powered predictions. Get insights into driver performance, track analysis, 
          and live race data all in one comprehensive platform.
        </p>
      </motion.div>

      {/* Call to Action */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="bg-gradient-to-r from-racing-red to-red-700 rounded-2xl p-8 text-center text-pure-white shadow-2xl mb-12"
      >
        <h3 className="text-3xl font-bold mb-4">Unlock Your Personalized F1 Experience</h3>
        <p className="text-lg opacity-90 mb-6">
          Sign up to get personalized insights based on your favorite driver, track, and team preferences
        </p>
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            to="/signup"
            className="inline-flex items-center px-8 py-4 bg-pure-white text-racing-red font-bold text-lg rounded-lg hover:bg-gray-100 transition-all duration-300 transform hover:scale-105"
          >
            <UserPlus className="w-5 h-5 mr-2" />
            Get Started
          </Link>
          <Link
            to="/login"
            className="inline-flex items-center px-8 py-4 bg-transparent border-2 border-pure-white text-pure-white font-bold text-lg rounded-lg hover:bg-pure-white hover:text-racing-red transition-all duration-300 transform hover:scale-105"
          >
            <LogIn className="w-5 h-5 mr-2" />
            Sign In
          </Link>
        </div>
      </motion.div>

      {/* Features Grid */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.4 }}
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-12"
      >
        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="text-center">
            <div className="w-16 h-16 bg-racing-red rounded-full flex items-center justify-center mx-auto mb-4">
              <Users className="w-8 h-8 text-pure-white" />
            </div>
            <h3 className="text-xl font-bold text-carbon-black mb-2">Driver Analytics</h3>
            <p className="text-gray-600">Comprehensive driver performance analysis and statistics</p>
          </div>
        </div>

        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="text-center">
            <div className="w-16 h-16 bg-turbo-teal rounded-full flex items-center justify-center mx-auto mb-4">
              <MapPin className="w-8 h-8 text-pure-white" />
            </div>
            <h3 className="text-xl font-bold text-carbon-black mb-2">Track Analysis</h3>
            <p className="text-gray-600">Detailed circuit information and performance insights</p>
          </div>
        </div>

        <div className="bg-track-grey rounded-xl p-6 shadow-lg">
          <div className="text-center">
            <div className="w-16 h-16 bg-pit-stop-yellow rounded-full flex items-center justify-center mx-auto mb-4">
              <TrendingUp className="w-8 h-8 text-pure-white" />
            </div>
            <h3 className="text-xl font-bold text-carbon-black mb-2">Live Data</h3>
            <p className="text-gray-600">Real-time race information and live analytics</p>
          </div>
        </div>
      </motion.div>

      {/* Public Access Info */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.6 }}
        className="bg-track-grey rounded-xl p-6 shadow-lg text-center"
      >
        <h3 className="text-2xl font-bold text-carbon-black mb-4">Explore F1 Analytics</h3>
        <p className="text-gray-600 mb-6">
          You can browse our F1 analytics and insights without an account. 
          Sign up to unlock personalized features and predictions!
        </p>
        <div className="flex flex-wrap justify-center gap-4">
          <Link
            to="/drivers"
            className="px-6 py-3 bg-racing-red text-pure-white font-bold rounded-lg hover:bg-red-700 transition-colors"
          >
            View Drivers
          </Link>
          <Link
            to="/tracks"
            className="px-6 py-3 bg-turbo-teal text-pure-white font-bold rounded-lg hover:bg-blue-700 transition-colors"
          >
            Explore Tracks
          </Link>
          <Link
            to="/live"
            className="px-6 py-3 bg-pit-stop-yellow text-carbon-black font-bold rounded-lg hover:bg-yellow-500 transition-colors"
          >
            Live Data
          </Link>
        </div>
      </motion.div>
    </div>
  );
};

export default MainPage;
