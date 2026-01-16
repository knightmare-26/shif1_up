import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate, Link } from 'react-router-dom';
import { User, Lock, Mail, Flag, Car, MapPin } from 'lucide-react';

interface UserPreferences {
  favoriteDriver: string;
  favoriteTrack: string;
  favoriteTeam: string;
  experienceLevel: 'beginner' | 'intermediate' | 'expert';
  notifications: boolean;
}

const SignupPage: React.FC = () => {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
  });
  const [preferences, setPreferences] = useState<UserPreferences>({
    favoriteDriver: '',
    favoriteTrack: '',
    favoriteTeam: '',
    experienceLevel: 'beginner',
    notifications: true,
  });
  const [currentStep, setCurrentStep] = useState(1);
  const [errors, setErrors] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const { signup } = useAuth();
  const navigate = useNavigate();

  const drivers = [
    'Max Verstappen', 'Lewis Hamilton', 'Charles Leclerc', 'Lando Norris',
    'Carlos Sainz', 'George Russell', 'Fernando Alonso', 'Oscar Piastri',
    'Sergio Pérez', 'Lance Stroll', 'Pierre Gasly', 'Esteban Ocon',
    'Alexander Albon', 'Yuki Tsunoda', 'Valtteri Bottas', 'Zhou Guanyu',
    'Nico Hulkenberg', 'Kevin Magnussen', 'Daniel Ricciardo', 'Logan Sargeant'
  ];

  const tracks = [
    'Monaco', 'Silverstone', 'Monza', 'Spa-Francorchamps', 'Suzuka',
    'Interlagos', 'Red Bull Ring', 'Hungaroring', 'Zandvoort', 'Marina Bay',
    'Yas Marina', 'Albert Park', 'Circuit of the Americas', 'Montreal',
    'Baku', 'Sochi', 'Jeddah', 'Losail', 'Miami', 'Las Vegas'
  ];

  const teams = [
    'Red Bull Racing', 'Mercedes', 'Ferrari', 'McLaren', 'Aston Martin',
    'Alpine', 'Williams', 'Visa Cash App RB', 'Stake F1 Team', 'Haas F1 Team'
  ];

  const validateForm = (): boolean => {
    const newErrors: string[] = [];

    if (formData.username.length < 3) {
      newErrors.push('Username must be at least 3 characters long');
    }

    if (!formData.email.includes('@')) {
      newErrors.push('Please enter a valid email address');
    }

    if (formData.password.length < 6) {
      newErrors.push('Password must be at least 6 characters long');
    }

    if (formData.password !== formData.confirmPassword) {
      newErrors.push('Passwords do not match');
    }

    if (currentStep === 2) {
      if (!preferences.favoriteDriver) {
        newErrors.push('Please select your favorite driver');
      }
      if (!preferences.favoriteTrack) {
        newErrors.push('Please select your favorite track');
      }
      if (!preferences.favoriteTeam) {
        newErrors.push('Please select your favorite team');
      }
    }

    setErrors(newErrors);
    return newErrors.length === 0;
  };

  const handleNext = () => {
    if (validateForm()) {
      setCurrentStep(2);
      setErrors([]);
    }
  };

  const handleBack = () => {
    setCurrentStep(1);
    setErrors([]);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateForm()) return;

    setIsLoading(true);
    try {
      const success = await signup({
        ...formData,
        preferences,
      });

      if (success) {
        navigate('/');
      } else {
        setErrors(['Signup failed. Please try again.']);
      }
    } catch (error) {
      setErrors(['An error occurred during signup.']);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-carbon-black flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 50 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="w-full max-w-4xl"
      >
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
          className="text-center mb-8"
        >
          <h1 className="text-6xl font-racing text-racing-red mb-4">
            Shif1 UP
          </h1>
          <p className="text-xl text-pure-white font-f1 mb-2">
            Join the Ultimate F1 Community
          </p>
          <p className="text-sm text-pure-white opacity-80">
            Create your account and personalize your F1 experience
          </p>
        </motion.div>

        {/* Progress Bar */}
        <div className="mb-8">
          <div className="flex items-center justify-center space-x-4 mb-4">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
              currentStep >= 1 ? 'bg-racing-red text-pure-white' : 'bg-track-grey text-carbon-black'
            }`}>
              1
            </div>
            <div className={`w-16 h-1 ${
              currentStep >= 2 ? 'bg-racing-red' : 'bg-track-grey'
            }`}></div>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
              currentStep >= 2 ? 'bg-racing-red text-pure-white' : 'bg-track-grey text-carbon-black'
            }`}>
              2
            </div>
          </div>
          <p className="text-center text-pure-white text-sm">
            {currentStep === 1 ? 'Account Details' : 'F1 Preferences'}
          </p>
        </div>

        {/* Form */}
        <motion.div
          initial={{ opacity: 0, x: currentStep === 1 ? -50 : 50 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6 }}
          className="bg-track-grey rounded-xl p-8 shadow-2xl"
        >
          {currentStep === 1 ? (
            /* Step 1: Account Details */
            <form onSubmit={(e) => { e.preventDefault(); handleNext(); }} className="space-y-6">
              <div>
                <label className="block text-carbon-black text-sm font-bold mb-2 flex items-center">
                  <User className="w-4 h-4 mr-2" />
                  Username
                </label>
                <input
                  type="text"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  className="w-full px-4 py-3 bg-pure-white text-carbon-black rounded-lg border-2 border-turbo-teal focus:border-racing-red focus:outline-none transition-colors"
                  placeholder="Choose your username"
                  required
                />
              </div>

              <div>
                <label className="block text-carbon-black text-sm font-bold mb-2 flex items-center">
                  <Mail className="w-4 h-4 mr-2" />
                  Email
                </label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full px-4 py-3 bg-pure-white text-carbon-black rounded-lg border-2 border-turbo-teal focus:border-racing-red focus:outline-none transition-colors"
                  placeholder="Enter your email"
                  required
                />
              </div>

              <div>
                <label className="block text-carbon-black text-sm font-bold mb-2 flex items-center">
                  <Lock className="w-4 h-4 mr-2" />
                  Password
                </label>
                <input
                  type="password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="w-full px-4 py-3 bg-pure-white text-carbon-black rounded-lg border-2 border-turbo-teal focus:border-racing-red focus:outline-none transition-colors"
                  placeholder="Create a password"
                  required
                />
              </div>

              <div>
                <label className="block text-carbon-black text-sm font-bold mb-2 flex items-center">
                  <Lock className="w-4 h-4 mr-2" />
                  Confirm Password
                </label>
                <input
                  type="password"
                  value={formData.confirmPassword}
                  onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                  className="w-full px-4 py-3 bg-pure-white text-carbon-black rounded-lg border-2 border-turbo-teal focus:border-racing-red focus:outline-none transition-colors"
                  placeholder="Confirm your password"
                  required
                />
              </div>

              <button
                type="submit"
                className="w-full py-3 px-6 bg-racing-red hover:bg-red-700 text-pure-white font-bold text-lg rounded-lg transition-all duration-300 transform hover:scale-105"
              >
                Next: F1 Preferences
              </button>
            </form>
          ) : (
            /* Step 2: F1 Preferences */
            <form onSubmit={handleSubmit} className="space-y-6">
              <div>
                <label className="block text-carbon-black text-sm font-bold mb-2 flex items-center">
                  <Car className="w-4 h-4 mr-2" />
                  Favorite Driver
                </label>
                <select
                  value={preferences.favoriteDriver}
                  onChange={(e) => setPreferences({ ...preferences, favoriteDriver: e.target.value })}
                  className="w-full px-4 py-3 bg-pure-white text-carbon-black rounded-lg border-2 border-turbo-teal focus:border-racing-red focus:outline-none transition-colors"
                  required
                >
                  <option value="">Select your favorite driver</option>
                  {drivers.map((driver) => (
                    <option key={driver} value={driver}>{driver}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-carbon-black text-sm font-bold mb-2 flex items-center">
                  <MapPin className="w-4 h-4 mr-2" />
                  Favorite Track
                </label>
                <select
                  value={preferences.favoriteTrack}
                  onChange={(e) => setPreferences({ ...preferences, favoriteTrack: e.target.value })}
                  className="w-full px-4 py-3 bg-pure-white text-carbon-black rounded-lg border-2 border-turbo-teal focus:border-racing-red focus:outline-none transition-colors"
                  required
                >
                  <option value="">Select your favorite track</option>
                  {tracks.map((track) => (
                    <option key={track} value={track}>{track}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-carbon-black text-sm font-bold mb-2 flex items-center">
                  <Flag className="w-4 h-4 mr-2" />
                  Favorite Team
                </label>
                <select
                  value={preferences.favoriteTeam}
                  onChange={(e) => setPreferences({ ...preferences, favoriteTeam: e.target.value })}
                  className="w-full px-4 py-3 bg-pure-white text-carbon-black rounded-lg border-2 border-turbo-teal focus:border-racing-red focus:outline-none transition-colors"
                  required
                >
                  <option value="">Select your favorite team</option>
                  {teams.map((team) => (
                    <option key={team} value={team}>{team}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-carbon-black text-sm font-bold mb-2">
                  Experience Level
                </label>
                <div className="grid grid-cols-3 gap-3">
                  {(['beginner', 'intermediate', 'expert'] as const).map((level) => (
                    <button
                      key={level}
                      type="button"
                      onClick={() => setPreferences({ ...preferences, experienceLevel: level })}
                      className={`py-2 px-4 rounded-lg border-2 transition-all duration-300 ${
                        preferences.experienceLevel === level
                          ? 'border-racing-red bg-racing-red text-pure-white'
                          : 'border-turbo-teal bg-pure-white text-carbon-black hover:border-racing-red'
                      }`}
                    >
                      {level.charAt(0).toUpperCase() + level.slice(1)}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="notifications"
                  checked={preferences.notifications}
                  onChange={(e) => setPreferences({ ...preferences, notifications: e.target.checked })}
                  className="w-4 h-4 text-racing-red bg-pure-white border-turbo-teal rounded focus:ring-racing-red focus:ring-2"
                />
                <label htmlFor="notifications" className="ml-2 text-carbon-black text-sm">
                  Receive notifications about my favorite driver and team
                </label>
              </div>

              <div className="flex space-x-4">
                <button
                  type="button"
                  onClick={handleBack}
                  className="flex-1 py-3 px-6 bg-track-grey hover:bg-gray-300 text-carbon-black font-bold text-lg rounded-lg transition-all duration-300 border-2 border-turbo-teal"
                >
                  Back
                </button>
                <button
                  type="submit"
                  disabled={isLoading}
                  className="flex-1 py-3 px-6 bg-racing-red hover:bg-red-700 text-pure-white font-bold text-lg rounded-lg transition-all duration-300 transform hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isLoading ? 'Creating Account...' : 'Create Account'}
                </button>
              </div>
            </form>
          )}

          {/* Error Messages */}
          {errors.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded-lg"
            >
              {errors.map((error, index) => (
                <p key={index} className="text-sm">{error}</p>
              ))}
            </motion.div>
          )}

          {/* Login Link */}
          <div className="mt-6 text-center">
            <p className="text-carbon-black text-sm">
              Already have an account?{' '}
              <Link to="/login" className="text-racing-red hover:text-red-700 font-bold">
                Sign in here
              </Link>
            </p>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
};

export default SignupPage;
