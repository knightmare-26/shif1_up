import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { Lock } from 'lucide-react';

type LoginRedirectState = { from?: string; fromLabel?: string };

const LoginPage: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [showError, setShowError] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const redirectState = (location.state as LoginRedirectState | null) ?? {};
  const fromPath = redirectState.from;
  const fromLabel = redirectState.fromLabel;

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setShowError(false);
    setIsVerifying(true);
    const success = await login(username, password);
    if (success) {
      navigate(fromPath || '/', { replace: true });
    } else {
      setShowError(true);
    }
    setIsVerifying(false);
  };

  return (
    <div className="min-h-screen bg-carbon-black flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 50 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="w-full max-w-md"
      >
        <motion.div
          initial={{ opacity: 0, x: -50 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
          className="text-center mb-8"
        >
          <h1 className="text-6xl font-racing text-racing-red mb-4">
            Shif1 UP
          </h1>
          <p className="text-xl text-pure-white font-f1">
            Your F1 Insights Hub
          </p>
        </motion.div>

        {fromPath && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            role="alert"
            className="mb-6 flex items-start space-x-3 bg-racing-red/10 border border-racing-red rounded-lg px-4 py-3"
          >
            <Lock className="w-5 h-5 text-racing-red flex-shrink-0 mt-0.5" />
            <div className="text-pure-white text-sm">
              <p className="font-bold">Sign in required</p>
              <p className="opacity-80">
                Please sign in to access{' '}
                <span className="text-racing-red font-semibold">
                  {fromLabel ?? 'this page'}
                </span>
                . New here?{' '}
                <Link to="/signup" state={{ from: fromPath, fromLabel }} className="underline hover:text-racing-red">
                  Create an account
                </Link>.
              </p>
            </div>
          </motion.div>
        )}

        <motion.form
          initial={{ opacity: 0, x: -50 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.8, delay: 0.4 }}
          onSubmit={handleLogin}
          className="space-y-5 rounded-xl border border-gray-800 bg-gray-900 p-8"
        >
          <div>
            <label htmlFor="login-username" className="mb-1 block text-xs uppercase tracking-wide text-gray-400">
              Username
            </label>
            <input
              id="login-username"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-white placeholder-gray-600 transition-colors focus:border-racing-red focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/40"
              placeholder="Enter your username"
              required
            />
          </div>

          <div>
            <label htmlFor="login-password" className="mb-1 block text-xs uppercase tracking-wide text-gray-400">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-white placeholder-gray-600 transition-colors focus:border-racing-red focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/40"
              placeholder="Enter your password"
              required
            />
          </div>

          <button
            type="submit"
            disabled={isVerifying}
            className="w-full rounded-lg bg-racing-red px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/60 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isVerifying ? 'Logging in...' : 'Log in'}
          </button>

          {showError && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              role="alert"
              className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-center text-sm text-red-300"
            >
              Login failed. Check your username and password and try again.
            </motion.div>
          )}
        </motion.form>

        <div className="mt-6 text-center">
          <p className="text-pure-white text-sm">
            Don't have an account?{' '}
            <Link to="/signup" className="text-racing-red hover:text-red-700 font-bold">
              Sign up here
            </Link>
          </p>
        </div>
      </motion.div>
    </div>
  );
};

export default LoginPage;
