import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate, Link } from 'react-router-dom';

const LoginPage: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [verificationSuccess, setVerificationSuccess] = useState(false);
  const [carPosition, setCarPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [trackError, setTrackError] = useState(false);
  const [showError, setShowError] = useState(false);
  
  const { login } = useAuth();
  const navigate = useNavigate();
  const trackRef = useRef<HTMLDivElement>(null);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!verificationSuccess) {
      setShowError(true);
      return;
    }

    setIsVerifying(true);
    const success = await login(username, password);
    if (success) {
      navigate('/');
    } else {
      setShowError(true);
    }
    setIsVerifying(false);
  };

  const handleCarDrag = (e: React.MouseEvent | React.TouchEvent) => {
    if (!trackRef.current) return;

    const rect = trackRef.current.getBoundingClientRect();
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX;
    const clientY = 'touches' in e ? e.touches[0].clientY : e.clientY;
    
    const x = clientX - rect.left;
    const y = clientY - rect.top;

    // Check if car is within track boundaries (with small margin)
    const margin = 20;
    const trackWidth = rect.width;
    const trackHeight = rect.height;
    
    if (x < margin || x > trackWidth - margin || y < margin || y > trackHeight - margin) {
      setTrackError(true);
      setVerificationSuccess(false);
    } else {
      setTrackError(false);
      setVerificationSuccess(true);
    }

    setCarPosition({ x, y });
  };

  const handleMouseDown = () => setIsDragging(true);
  const handleMouseUp = () => setIsDragging(false);

  useEffect(() => {
    if (trackError) {
      const timer = setTimeout(() => setTrackError(false), 2000);
      return () => clearTimeout(timer);
    }
  }, [trackError]);

  return (
    <div className="min-h-screen bg-carbon-black flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 50 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-2 gap-8"
      >
        {/* Login Form */}
        <div className="flex flex-col justify-center">
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

          <motion.form
            initial={{ opacity: 0, x: -50 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.4 }}
            onSubmit={handleLogin}
            className="space-y-6"
          >
            <div>
              <label className="block text-pure-white text-sm font-bold mb-2">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-4 py-3 bg-track-grey text-carbon-black rounded-lg border-2 border-turbo-teal focus:border-racing-red focus:outline-none transition-colors"
                placeholder="Enter your username"
                required
              />
            </div>

            <div>
              <label className="block text-pure-white text-sm font-bold mb-2">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 bg-track-grey text-carbon-black rounded-lg border-2 border-turbo-teal focus:border-racing-red focus:outline-none transition-colors"
                placeholder="Enter your password"
                required
              />
            </div>

            <button
              type="submit"
              disabled={isVerifying || !verificationSuccess}
              className={`w-full py-3 px-6 rounded-lg font-bold text-lg transition-all duration-300 ${
                verificationSuccess
                  ? 'bg-racing-red hover:bg-red-700 text-pure-white transform hover:scale-105'
                  : 'bg-gray-500 text-gray-300 cursor-not-allowed'
              }`}
            >
              {isVerifying ? 'Verifying...' : 'Login'}
            </button>

            {showError && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="text-pit-stop-yellow text-center"
              >
                {!verificationSuccess ? 'Please complete the verification first!' : 'Login failed. Please try again.'}
              </motion.div>
            )}
          </motion.form>

          {/* Login Link */}
          <div className="mt-6 text-center">
            <p className="text-pure-white text-sm">
              Don't have an account?{' '}
              <Link to="/signup" className="text-racing-red hover:text-red-700 font-bold">
                Sign up here
              </Link>
            </p>
          </div>
        </div>

        {/* Interactive Verification */}
        <div className="flex flex-col justify-center items-center">
          <motion.div
            initial={{ opacity: 0, x: 50 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.6 }}
            className="text-center mb-6"
          >
            <h2 className="text-2xl font-f1 text-pure-white mb-2">
              Are you human?
            </h2>
            <p className="text-sm text-pure-white">
              Click & hold the F1 car and drag it along the track to the finish line
            </p>
          </motion.div>

          <div
            ref={trackRef}
            className="relative w-80 h-60 bg-gradient-to-r from-gray-800 via-gray-600 to-gray-800 rounded-lg border-4 border-racing-red overflow-hidden"
            style={{
              backgroundImage: 'linear-gradient(90deg, #2a2a2a 0%, #4a4a4a 50%, #2a2a2a 100%)',
            }}
          >
            {/* Track markings */}
            <div className="absolute top-1/2 left-0 w-full h-1 bg-white opacity-30"></div>
            <div className="absolute top-1/4 left-0 w-full h-1 bg-white opacity-20"></div>
            <div className="absolute top-3/4 left-0 w-full h-1 bg-white opacity-20"></div>
            
            {/* Start line */}
            <div className="absolute left-4 top-0 bottom-0 w-2 checkered-bg"></div>
            
            {/* Finish line */}
            <div className="absolute right-4 top-0 bottom-0 w-2 checkered-bg"></div>

            {/* F1 Car */}
            <motion.div
              className={`absolute w-8 h-4 cursor-grab active:cursor-grabbing ${
                trackError ? 'text-pit-stop-yellow' : 'text-racing-red'
              }`}
              style={{
                left: carPosition.x - 16,
                top: carPosition.y - 8,
                transform: 'translate(-50%, -50%)',
              }}
              drag
              dragMomentum={false}
              dragConstraints={trackRef}
              onDrag={(e, info) => handleCarDrag(e as any)}
              onDragStart={handleMouseDown}
              onDragEnd={handleMouseUp}
              animate={{
                scale: isDragging ? 1.2 : 1,
                rotate: isDragging ? 5 : 0,
              }}
              transition={{ duration: 0.2 }}
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2L2 7v10c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-10-5z"/>
              </svg>
            </motion.div>

            {/* Error indicator */}
            <AnimatePresence>
              {trackError && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8 }}
                  className="absolute inset-0 bg-red-500 bg-opacity-20 flex items-center justify-center"
                >
                  <span className="text-red-400 font-bold text-lg">TRACK LIMITS!</span>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Success indicator */}
            <AnimatePresence>
              {verificationSuccess && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8 }}
                  className="absolute inset-0 bg-green-500 bg-opacity-20 flex items-center justify-center"
                >
                  <span className="text-green-400 font-bold text-lg">VERIFIED!</span>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 1 }}
            className="mt-4 text-center"
          >
            <p className="text-sm text-pure-white">
              {verificationSuccess ? '✅ Verification complete!' : '🚗 Drag the car to verify'}
            </p>
          </motion.div>
        </div>
      </motion.div>
    </div>
  );
};

export default LoginPage;
