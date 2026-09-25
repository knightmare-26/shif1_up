import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link, NavLink, useLocation } from 'react-router-dom';
import {
  Home, BarChart3, Activity,
  Database, Menu, X, TrendingUp,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { LogoMark, Wordmark } from './ui';

type NavItem = { path: string; label: string; icon: LucideIcon };

const NAV_ITEMS: NavItem[] = [
  { path: '/',             label: 'Home',         icon: Home },
  { path: '/dashboard',    label: 'Dashboard',    icon: BarChart3 },
  { path: '/predictions',  label: 'Predictions',  icon: TrendingUp },
  { path: '/live',         label: 'Live',         icon: Activity },
  { path: '/data-manager', label: 'Data Manager', icon: Database },
];

const Navigation: React.FC = () => {
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const renderItem = (item: NavItem, compact = false) => {
    const Icon = item.icon;
    // Nested routes (e.g. /live-monitor under Live) keep their section highlighted.
    const isActive = item.path === '/'
      ? location.pathname === '/'
      : location.pathname.startsWith(item.path);
    const base = 'flex items-center space-x-2 px-3 py-2 rounded-lg transition-colors duration-200 text-sm font-medium';
    const state = isActive
      ? 'bg-racing-red text-pure-white'
      : 'text-gray-300 hover:bg-gray-800 hover:text-pure-white';

    return (
      <NavLink
        key={item.path}
        to={item.path}
        onClick={() => setMobileOpen(false)}
        className={`${base} ${state} ${compact ? 'w-full justify-start' : ''}`}
      >
        <Icon className="w-4 h-4 flex-shrink-0" />
        <span>{item.label}</span>
      </NavLink>
    );
  };

  return (
    <motion.nav
      initial={{ y: -64 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.4 }}
      className="fixed top-0 left-0 right-0 h-16 bg-carbon-black border-b border-racing-red shadow-lg z-50"
    >
      <div className="max-w-[1600px] mx-auto h-full px-4 sm:px-6 flex items-center justify-between gap-4">
        {/* Logo */}
        <Link to="/" aria-label="Shif1 UP home" className="flex items-center flex-shrink-0 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/60">
          <LogoMark className="h-9 w-9 sm:hidden" />
          <Wordmark className="hidden text-2xl sm:inline-flex" />
        </Link>

        {/* Desktop nav */}
        <div className="hidden lg:flex items-center space-x-1 flex-1 justify-center overflow-x-auto">
          {NAV_ITEMS.map((item) => renderItem(item))}
        </div>

        {/* Mobile toggle */}
        <button
          onClick={() => setMobileOpen((v) => !v)}
          className="lg:hidden p-2 text-gray-300 hover:text-pure-white rounded-lg hover:bg-gray-800 transition-colors"
          aria-label="Toggle menu"
          aria-expanded={mobileOpen}
        >
          {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="lg:hidden absolute left-0 right-0 top-16 bg-carbon-black border-b border-racing-red shadow-xl"
          >
            <div className="max-w-[1600px] mx-auto px-4 sm:px-6 py-3 flex flex-col space-y-1">
              {NAV_ITEMS.map((item) => renderItem(item, true))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.nav>
  );
};

export default Navigation;
