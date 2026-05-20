import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { User, Lock, Mail } from 'lucide-react';

interface LocationState { from?: string; fromLabel?: string; }

const SignupPage: React.FC = () => {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
  });
  const [errors, setErrors]     = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const { signup }  = useAuth();
  const navigate    = useNavigate();
  const location    = useLocation();
  const { from, fromLabel } = (location.state as LocationState) ?? {};

  const validate = (): boolean => {
    const errs: string[] = [];
    if (formData.username.length < 3)            errs.push('Username must be at least 3 characters');
    if (!formData.email.includes('@'))            errs.push('Please enter a valid email address');
    if (formData.password.length < 6)            errs.push('Password must be at least 6 characters');
    if (formData.password !== formData.confirmPassword) errs.push('Passwords do not match');
    setErrors(errs);
    return errs.length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setIsLoading(true);
    try {
      const success = await signup(formData);
      if (success) {
        navigate(from || '/', { replace: true });
      } else {
        setErrors(['Signup failed. Please try again.']);
      }
    } catch {
      setErrors(['An error occurred during signup.']);
    } finally {
      setIsLoading(false);
    }
  };

  const field = (
    id: keyof typeof formData,
    label: string,
    type: string,
    placeholder: string,
    Icon: React.ElementType,
  ) => (
    <div>
      <label className="block text-carbon-black text-sm font-bold mb-2 flex items-center">
        <Icon className="w-4 h-4 mr-2" />
        {label}
      </label>
      <input
        type={type}
        value={formData[id]}
        onChange={(e) => setFormData({ ...formData, [id]: e.target.value })}
        className="w-full px-4 py-3 bg-pure-white text-carbon-black rounded-lg border-2 border-turbo-teal focus:border-racing-red focus:outline-none transition-colors"
        placeholder={placeholder}
        required
      />
    </div>
  );

  return (
    <div className="min-h-screen bg-carbon-black flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 50 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="w-full max-w-md"
      >
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-6xl font-racing text-racing-red mb-4">Shif1 UP</h1>
          <p className="text-xl text-pure-white font-f1 mb-1">Create your account</p>
          {fromLabel && (
            <p className="text-sm text-turbo-teal mt-2">
              Sign up to access <span className="font-bold">{fromLabel}</span>
            </p>
          )}
        </div>

        {/* Form */}
        <div className="bg-track-grey rounded-xl p-8 shadow-2xl">
          <form onSubmit={handleSubmit} className="space-y-5">
            {field('username',        'Username',         'text',     'Choose your username',  User)}
            {field('email',           'Email',            'email',    'Enter your email',      Mail)}
            {field('password',        'Password',         'password', 'Create a password',     Lock)}
            {field('confirmPassword', 'Confirm Password', 'password', 'Confirm your password', Lock)}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 px-6 bg-racing-red hover:bg-red-700 text-pure-white font-bold text-lg rounded-lg transition-all duration-300 transform hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? 'Creating Account...' : 'Create Account'}
            </button>
          </form>

          {errors.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded-lg"
            >
              {errors.map((err, i) => <p key={i} className="text-sm">{err}</p>)}
            </motion.div>
          )}

          <div className="mt-6 text-center">
            <p className="text-carbon-black text-sm">
              Already have an account?{' '}
              <Link to="/login" state={location.state} className="text-racing-red hover:text-red-700 font-bold">
                Sign in here
              </Link>
            </p>
          </div>
        </div>
      </motion.div>
    </div>
  );
};

export default SignupPage;
