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
      <label htmlFor={`signup-${id}`} className="mb-1 flex items-center text-xs uppercase tracking-wide text-gray-400">
        <Icon className="w-4 h-4 mr-2" aria-hidden="true" />
        {label}
      </label>
      <input
        id={`signup-${id}`}
        type={type}
        value={formData[id]}
        onChange={(e) => setFormData({ ...formData, [id]: e.target.value })}
        className="w-full rounded-lg border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-white placeholder-gray-600 transition-colors focus:border-racing-red focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/40"
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
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-8">
          <form onSubmit={handleSubmit} className="space-y-5">
            {field('username',        'Username',         'text',     'Choose your username',  User)}
            {field('email',           'Email',            'email',    'Enter your email',      Mail)}
            {field('password',        'Password',         'password', 'Create a password',     Lock)}
            {field('confirmPassword', 'Confirm Password', 'password', 'Confirm your password', Lock)}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full rounded-lg bg-racing-red px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-racing-red/60 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? 'Creating Account...' : 'Create Account'}
            </button>
          </form>

          {errors.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              role="alert"
              className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-300"
            >
              {errors.map((err, i) => <p key={i} className="text-sm">{err}</p>)}
            </motion.div>
          )}

          <div className="mt-6 text-center">
            <p className="text-sm text-gray-400">
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
