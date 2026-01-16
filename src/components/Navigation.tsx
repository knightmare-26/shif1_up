import React from 'react';
import { motion } from 'framer-motion';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { 
  Home, 
  BarChart3, 
  Users, 
  MapPin, 
  Activity, 
  Settings, 
  LogOut,
  Car,
  Flag,
  Database,
  Radio,
  Trophy,
  Clock,
  Download
} from 'lucide-react';

const Navigation: React.FC = () => {
  const { user, logout } = useAuth();
  const location = useLocation();

  const navItems = [
    { path: '/', label: 'Home', icon: Home },
    { path: '/dashboard', label: 'Dashboard', icon: BarChart3 },
    { path: '/drivers', label: 'Drivers', icon: Users },
    { path: '/tracks', label: 'Tracks', icon: MapPin },
    { path: '/live', label: 'Live Data', icon: Activity },
    { path: '/race-results', label: 'Race Results', icon: Trophy },
    { path: '/lap-data', label: 'Lap Data', icon: Clock },
    { path: '/data-manager', label: 'Data Manager', icon: Download },
    { path: '/live-monitor', label: 'Live Monitor', icon: Radio },
  ];

  const handleLogout = () => {
    logout();
  };

  if (!user) return null;

  return (
    <motion.nav
      initial={{ y: -80 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.5 }}
      className="fixed top-0 left-0 right-0 h-20 bg-carbon-black border-b border-racing-red shadow-2xl z-50 flex items-center justify-between px-6"
    >
      {/* Logo Section */}
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="flex items-center space-x-4"
      >
        <h1 className="text-2xl font-racing text-racing-red">
          Shif1 UP
        </h1>
        <p className="text-pure-white text-sm font-f1 hidden md:block">
          F1 Analytics Hub
        </p>
      </motion.div>

      {/* Navigation Menu */}
      <div className="flex items-center space-x-1">
        {navItems.map((item, index) => {
          const Icon = item.icon;
          const isActive = location.pathname === item.path;
          
          return (
            <motion.div
              key={item.path}
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.1 * index }}
            >
              <Link
                to={item.path}
                className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-all duration-300 ${
                  isActive
                    ? 'bg-racing-red text-pure-white shadow-lg'
                    : 'text-gray-300 hover:bg-gray-800 hover:text-pure-white'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span className="font-medium text-sm">{item.label}</span>
              </Link>
            </motion.div>
          );
        })}
      </div>

      {/* User Section */}
      <motion.div
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.6, delay: 0.3 }}
        className="flex items-center space-x-4"
      >
        {/* User Info */}
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 bg-racing-red rounded-full flex items-center justify-center">
            <span className="text-pure-white font-bold text-sm">
              {user.username.charAt(0).toUpperCase()}
            </span>
          </div>
          <div className="hidden md:block">
            <p className="text-pure-white font-medium text-sm">{user.username}</p>
            <p className="text-gray-400 text-xs capitalize">{user.preferences.experienceLevel}</p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center space-x-2">
          <Link
            to="/settings"
            className="p-2 text-gray-300 hover:bg-gray-800 hover:text-pure-white rounded-lg transition-all duration-300"
            title="Settings"
          >
            <Settings className="w-4 h-4" />
          </Link>
          
          <button
            onClick={handleLogout}
            className="p-2 text-gray-300 hover:bg-red-900 hover:text-pure-white rounded-lg transition-all duration-300"
            title="Logout"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </motion.div>
    </motion.nav>
  );
};

export default Navigation;
