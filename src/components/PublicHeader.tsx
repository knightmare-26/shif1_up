import React from 'react';
import { motion } from 'framer-motion';
import { Link, useLocation } from 'react-router-dom';
import { Home, Users, MapPin, Activity, LogIn, UserPlus } from 'lucide-react';

const PublicHeader: React.FC = () => {
  const location = useLocation();

  const navItems = [
    { path: '/', label: 'Home', icon: Home },
    { path: '/drivers', label: 'Drivers', icon: Users },
    { path: '/tracks', label: 'Tracks', icon: MapPin },
    { path: '/live', label: 'Live Data', icon: Activity },
  ];

  return (
    <motion.header
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.6 }}
      className="bg-carbon-black border-b border-racing-red shadow-lg"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center">
            <Link to="/" className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-racing-red rounded-full flex items-center justify-center">
                <span className="text-pure-white font-bold text-lg">S</span>
              </div>
              <span className="text-2xl font-racing text-racing-red">Shif1 UP</span>
            </Link>
          </div>

          {/* Navigation */}
          <nav className="hidden md:flex items-center space-x-8">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname === item.path;
              
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center space-x-2 px-3 py-2 rounded-lg transition-all duration-300 ${
                    isActive
                      ? 'text-racing-red bg-racing-red bg-opacity-10'
                      : 'text-gray-300 hover:text-pure-white hover:bg-gray-800'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span className="font-medium">{item.label}</span>
                </Link>
              );
            })}
          </nav>

          {/* Auth Buttons */}
          <div className="flex items-center space-x-4">
            <Link
              to="/login"
              className="flex items-center space-x-2 px-4 py-2 text-gray-300 hover:text-pure-white transition-colors"
            >
              <LogIn className="w-4 h-4" />
              <span className="font-medium">Sign In</span>
            </Link>
            <Link
              to="/signup"
              className="flex items-center space-x-2 px-4 py-2 bg-racing-red text-pure-white rounded-lg hover:bg-red-700 transition-colors"
            >
              <UserPlus className="w-4 h-4" />
              <span className="font-medium">Sign Up</span>
            </Link>
          </div>
        </div>
      </div>
    </motion.header>
  );
};

export default PublicHeader;
