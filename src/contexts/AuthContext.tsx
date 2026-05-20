import React, { createContext, useContext, useState, ReactNode, useEffect } from 'react';
import { User, UserDisplay, UserPreferences } from '../types';
import {
  authLogin,
  authSignup,
  authGetMe,
  authUpdatePreferences,
  getStoredToken,
  storeToken,
  clearToken,
} from '../services/authApi';

interface AuthContextType {
  isAuthenticated: boolean;
  user: User | null;
  login: (username: string, password: string) => Promise<boolean>;
  signup: (userData: {
    username: string;
    email: string;
    password: string;
  }) => Promise<boolean>;
  logout: () => void;
  updatePreferences: (preferences: Partial<UserPreferences>) => void;
  getPublicUserData: () => UserDisplay | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [user, setUser] = useState<User | null>(null);

  // On mount: validate stored JWT with the backend
  useEffect(() => {
    const restoreSession = async () => {
      const token = getStoredToken();
      if (!token) return;
      try {
        const me = await authGetMe(token);
        setUser({ ...me, createdAt: new Date() });
        setIsAuthenticated(true);
      } catch {
        clearToken();
      }
    };
    restoreSession();
  }, []);

  const login = async (username: string, password: string): Promise<boolean> => {
    try {
      const { access_token, user: me } = await authLogin(username, password);
      storeToken(access_token);
      setUser({ ...me, createdAt: new Date() });
      setIsAuthenticated(true);
      return true;
    } catch {
      return false;
    }
  };

  const signup = async (userData: {
    username: string;
    email: string;
    password: string;
  }): Promise<boolean> => {
    try {
      const { access_token, user: me } = await authSignup(userData);
      storeToken(access_token);
      setUser({ ...me, createdAt: new Date() });
      setIsAuthenticated(true);
      return true;
    } catch {
      return false;
    }
  };

  const logout = () => {
    clearToken();
    setIsAuthenticated(false);
    setUser(null);
  };

  const updatePreferences = async (newPreferences: Partial<UserPreferences>) => {
    if (!user) return;
    const merged: UserPreferences = { ...user.preferences, ...newPreferences };
    const token = getStoredToken();
    if (token) {
      try {
        await authUpdatePreferences(token, merged);
      } catch {
        // best-effort — update UI state regardless
      }
    }
    setUser({ ...user, preferences: merged });
  };

  const getPublicUserData = (): UserDisplay | null => {
    if (!user) return null;
    return { id: user.id, username: user.username, preferences: user.preferences, createdAt: user.createdAt };
  };

  const value: AuthContextType = {
    isAuthenticated,
    user,
    login,
    signup,
    logout,
    updatePreferences,
    getPublicUserData,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
